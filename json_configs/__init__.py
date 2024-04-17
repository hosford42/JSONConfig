import abc
import builtins
import datetime
import importlib
import inspect
import os.path
import sys
from abc import abstractmethod, ABC
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar, Iterable, Mapping, Optional, NewType, Sequence

__version__ = '0.0'

_ConfigurableValue = TypeVar('_ConfigurableValue')
Configuration = 'None | bool | int | float | str | list[Configuration] | dict[str, Configuration]'


_GetConfigFunc = Callable[[_ConfigurableValue, Optional[str]], Configuration]
_ConfigureFunc = Callable[[Configuration, Optional[_ConfigurableValue], Optional[str]], _ConfigurableValue]

_Self = TypeVar('_Self')

Module = NewType('Module', type[sys])


class Context:

    def __init__(self, name: str):
        self.name = name
        self.registry: dict[tuple[str, str], type] = {}
        self.registered_from: dict[tuple[str, str], inspect.Traceback] = {}
        self.location_map: dict[type, tuple[str, str]] = {}
        self.all_modules_allowed_by_default = False
        self.imported_modules_allowed_by_default = False
        self.public_classes_allowed_by_default = False
        self.specifically_allowed_modules: set[str] = {'builtins'}
        self.specifically_denied_modules: set[str] = set()
        self.specifically_allowed_classes: set[tuple[str, str]] = {
            ('builtins', name)
            for name in dir(builtins)
            if not name.startswith('_') and isinstance(getattr(builtins, name), type)
        }
        self.specifically_allowed_classes.update([
            ('datetime', name)
            for name in dir(datetime)
            if not name.startswith('_') and isinstance(getattr(datetime, name), type)
        ])
        self.specifically_allowed_classes.add(('abc', 'ABCMeta'))
        self.specifically_denied_classes: set[tuple[str, str]] = set()

    def module_access_is_allowed(self, module_name: str) -> bool:
        if module_name in self.specifically_denied_modules:
            return False
        if module_name in self.specifically_allowed_modules:
            return True
        if self.imported_modules_allowed_by_default:
            return self.all_modules_allowed_by_default or module_name in sys.modules
        return False

    def get_module(self, module_name: str, *, load_module: bool = False) -> Optional[type[sys]]:
        if not self.module_access_is_allowed(module_name):
            return None
        if load_module:
            return importlib.import_module(module_name)
        return sys.modules.get(module_name, None)

    @staticmethod
    def get_public_names(module: Module) -> list[str]:
        if hasattr(module, '__all__'):
            listing = module.__all__
        else:
            listing = dir(module)
        return [name for name in listing if hasattr(module, name) and not name.startswith('_')]

    def class_access_is_allowed(self, module_name: str, class_name: str, load_module: bool = False) -> bool:
        if (module_name, class_name) in self.specifically_denied_classes:
            return False
        if (module_name, class_name) in self.specifically_allowed_classes:
            return True
        if not self.public_classes_allowed_by_default:
            return False
        module = self.get_module(module_name, load_module=load_module)
        if module is None:
            return False
        return class_name in self.get_public_names(module)

    def register(self, type_: type[_ConfigurableValue] | Sequence[type[_ConfigurableValue]], module_name: str = None,
                 class_name: str = None, *, overwrite: bool = False,
                 auto: bool = False) -> type[_ConfigurableValue] | Iterable[type[_ConfigurableValue]]:
        original_type = type_
        if isinstance(type_, type):
            types = (type_,)
            module_names = (module_name,)
            class_names = (class_name,)
        else:
            types = type_
            module_names = ([module_name] * len(types) if module_name is None or isinstance(module_name, str)
                            else module_name)
            class_names = [None] * len(types) if class_name is None else class_name
        assert not isinstance(types, (str, type))
        assert not isinstance(module_names, str) and len(module_names) == len(types)
        assert not isinstance(class_names, str) and len(class_names) == len(types)
        for type_, module_name, class_name in zip(types, module_names, class_names):
            type_: type[_ConfigurableValue]
            if issubclass(type_, WrapAutoConfig):
                assert isinstance(type_.wrapped, type)  # TODO: Support multiple wrapped types
                type_: type = type_.wrapped
            elif auto and not is_configurable(type_):
                auto_config(type_)
            if module_name is None:
                module_name = type_.__module__
            if class_name is None:
                class_name = type_.__name__
            key = (module_name, class_name)
            if not (overwrite or key not in self.registry or self.registry[key] is type_):
                info = self.registered_from[key]
                raise NameError(f"A type has already been registered for class {class_name} in module {module_name} in "
                                f"the {self.name} context. The previous registration was made from file "
                                f"{info.filename}, line {info.lineno}. If you would like to overwrite the previously "
                                f"registered class, set the overwrite flag to True.")
            if overwrite and key in self.registry:
                del self.location_map[self.registry[key]]
            self.registry[key] = type_
            self.registered_from[key] = get_caller_info()
            self.location_map[type_] = key
        return original_type

    def get_type(self, module_name: str, class_name: str, *, load_module: bool = False) -> type:
        key = (module_name, class_name)
        if key in self.registry:
            return self.registry[key]
        if not self.class_access_is_allowed(module_name, class_name, load_module=load_module):
            raise NameError(f"Access denied for class {class_name} in module {module_name} in the {self.name} "
                            f"context. Consider adjusting access control settings and/or registering the class with "
                            f"the {self.name} context.")
        module = importlib.import_module(module_name)
        result = getattr(module, class_name)
        if not isinstance(result, type):
            raise TypeError(result)
        return result

    def locate(self, type_: type) -> tuple[str, str]:
        if type_ in self.location_map:
            return self.location_map[type_]
        if self.get_type(type_.__module__, type_.__name__) is not type_:
            raise ValueError(f"Type {type_.__name__} in module {type_.__module__} is not accessible from the "
                             f"{self.name} context.")
        return type_.__module__, type_.__name__


CONTEXTS: dict[Optional[str], Context] = {None: Context('default')}
GET_CONFIG_REGISTRY: dict[type[_ConfigurableValue], _GetConfigFunc] = {}
CONFIGURE_REGISTRY: dict[type[_ConfigurableValue], _ConfigureFunc] = {}
GET_CONFIG_FROM: dict[type[_ConfigurableValue], inspect.Traceback] = {}
CONFIGURE_FROM: dict[type[_ConfigurableValue], inspect.Traceback] = {}


def is_configurable(type_: type) -> bool:
    return issubclass(type_, Configurable) or (type_ in GET_CONFIG_REGISTRY and type_ in CONFIGURE_REGISTRY)


def get_context(name: str = None, *, add: bool = False) -> Context:
    try:
        return CONTEXTS[name]
    except KeyError:
        if add:
            CONTEXTS[name] = Context(name)
            return CONTEXTS[name]
        raise


def box_type(type_: type, config: Configuration, context: str = None) -> Configuration:
    module_name, class_name = get_context(context).locate(type_)
    if (isinstance(config, dict) and
            config.keys() == {'__module__', '__class__', '__instance__'} and
            config['__module__'] == module_name and
            config['__class__'] == class_name):
        return config
    return dict(
        __module__=module_name,
        __class__=class_name,
        __instance__=config
    )


def unbox_type(config: Configuration, context: str = None) -> tuple[type[_ConfigurableValue], Configuration]:
    if isinstance(config, dict) and config.keys() == {'__module__', '__class__', '__instance__'}:
        type_ = get_context(context).get_type(config['__module__'], config['__class__'])
        config = config['__instance__']
    else:
        type_ = type(config)
    return type_, config


def config_type_boxer(type_: type[_ConfigurableValue], *,
                      func: _GetConfigFunc = None) -> _GetConfigFunc | Callable[[_GetConfigFunc], _GetConfigFunc]:
    if func is None:
        return lambda f, t=type_: config_type_boxer(t, func=f)

    @wraps(func)
    def wrapper(obj, context: str = None) -> Configuration:
        return box_type(type_, func(obj, context), context=context)
    return wrapper


def config_type_unboxer(func: _ConfigureFunc) -> _ConfigureFunc:
    @wraps(func)
    def wrapper(config: Configuration, instance: Any = None, context: str = None) -> Any:
        type_, config = unbox_type(config, context=context)
        if not isinstance(instance, type_):
            instance = None
        result = func(config, instance, context)
        if not isinstance(result, type_):
            result = type_(result)
        return result
    return wrapper


def get_caller_info() -> inspect.Traceback:
    frame = inspect.currentframe()
    info = inspect.getframeinfo(frame)
    while frame.f_back and (info.filename == "<string>" or
                            os.path.basename(os.path.dirname(info.filename)) == 'json_configs'):
        frame = frame.f_back
        info = inspect.getframeinfo(frame)
    return info


def config_getter(*types: type[_ConfigurableValue], typed: bool = True,
                  func: _GetConfigFunc = None,
                  overwrite: bool = False) -> _GetConfigFunc | Callable[[_GetConfigFunc], _GetConfigFunc]:
    """Decorator for get_config() hooks for non-Configurable classes.
    A config getter should conform to the protocol:

        def my_config_getter(instance, context: str = None) -> Configuration:
            ...
            return config
    """
    if not overwrite:
        for type_ in types:
            if type_ in GET_CONFIG_REGISTRY:
                info = GET_CONFIG_FROM[type_]
                raise NameError(f"A config getter was already registered for type {type_.__name__}, defined in module "
                                f"{type_.__module__}. The previously registered config getter was registered from "
                                f"file {info.filename}, line {info.lineno}. If you want to overwrite the previously "
                                f"registered config getter, set the overwrite flag to True.")
    if func is None:
        return lambda f, ts=types, td=typed: config_getter(*ts, typed=td, func=f)
    for type_ in types:
        if typed:
            wrapper = config_type_boxer(type_, func=func)
        else:
            wrapper = func
        GET_CONFIG_REGISTRY[type_] = wrapper
        GET_CONFIG_FROM[type_] = get_caller_info()
    return func


def config_setter(*types: type[_ConfigurableValue],
                  func: _ConfigureFunc = None,
                  overwrite: bool = False) -> _ConfigureFunc | Callable[[_ConfigureFunc], _ConfigureFunc]:
    """Decorator for configure() hooks for non-Configurable classes.
    A config setter should conform to the protocol:

        def my_config_setter(config: Configuration, instance: NonConfigurableType = None,
                context: str = None) -> NonConfigurableType:
            if instance is None:
                instance = ...
            else:
                ...
            assert correctly_configured(instance, config)
            return instance
    """
    if not overwrite:
        for type_ in types:
            if type_ in CONFIGURE_REGISTRY:
                info = CONFIGURE_FROM[type_]
                raise NameError(f"A config setter was already registered for type {type_.__name__}, defined in module "
                                f"{type_.__module__}. The previously registered config setter was registered from "
                                f"file {info.filename}, line {info.lineno}. If you want to overwrite the previously "
                                f"registered config setter, set the overwrite flag to True.")
    if func is None:
        return lambda f, t=types: config_setter(*t, func=f)
    for type_ in types:
        CONFIGURE_REGISTRY[type_] = func
        CONFIGURE_FROM[type_] = get_caller_info()
    return func


@config_getter(type(None), bool, int, float, str, typed=False)
def get_simple_config(x, _context: str = None):
    return x


@config_setter(type(None), bool, int, float, str)
def configure_simple(config: Configuration, instance: Optional[_ConfigurableValue] = None,
                     _context: str = None) -> _ConfigurableValue:
    if config == instance:
        return instance
    return config


@config_getter(type, abc.ABCMeta)
def get_python_type_config(type_: type, context: str = None) -> Configuration:
    assert isinstance(type_, type)
    module_name, class_name = get_context(context).locate(type_)
    return dict(module=module_name, name=class_name)


@config_setter(type, abc.ABCMeta)
def configure_python_type(config: Configuration, _instance: type = None, context: str = None) -> type:
    return get_context(context).get_type(config['module'], config['name'])


# TODO: Instead of defining this as a global constant, make it a configurable setting of the context.
DEFAULT_DATETIME_FORMAT = '%Y%m%d%H%M%S.%f'


@config_getter(datetime.datetime)
def get_datetime_config(dt: datetime.datetime, _context: str = None, fmt: str = None) -> Configuration:
    assert isinstance(dt, datetime.datetime)
    fmt = fmt or DEFAULT_DATETIME_FORMAT
    return dict(value=dt.strftime(fmt), format=fmt)


@config_setter(datetime.datetime)
def configure_datetime(config: Configuration, _instance: datetime.datetime = None,
                       _context: str = None) -> datetime.datetime:
    return datetime.datetime.strptime(config['value'], config.get('format', DEFAULT_DATETIME_FORMAT))


@config_getter(list, typed=False)
@config_getter(tuple, set, frozenset)
def get_iterable_config(iterable: Iterable, context: str = None) -> Configuration:
    return [get_config(value, context=context) for value in iterable]


@config_setter(list, tuple, set, frozenset)
def configure_iterable(config: Configuration, _instance: Iterable = None, context: str = None) -> Iterable:
    assert isinstance(config, list)
    return (configure(value_config, context=context) for value_config in config)


@config_getter(dict, typed=False)
def get_mapping_config(mapping: Mapping, context: str = None) -> Configuration:
    if isinstance(mapping, dict) and all(isinstance(key, str) for key in mapping):
        return {key: get_config(value, context=context) for key, value in mapping.items()}
    return box_type(type(mapping), [[get_config(key, context=context), get_config(value, context=context)]
                                    for key, value in mapping.items()])


@config_setter(dict)
def configure_mapping(config: Configuration, _instance: Mapping = None, context: str = None) -> Mapping:
    if isinstance(config, dict):
        return {key: configure(value_config, context=context) for key, value_config in config.items()}
    else:
        assert isinstance(config, list)
        return {configure(key_config, context=context): configure(value_config, context=context)
                for key_config, value_config in config}


@dataclass
class WrapAutoConfig:
    """Wrapper for non-Configurable types to make them configurable."""
    wrapped: type[_ConfigurableValue]
    typed: bool = True
    unconfigured_properties: Iterable[str] = None
    property_types: Mapping[str, type] = None
    init_args: Sequence[str] = None
    init_kwargs: Mapping[str, str] = None
    instance: 'WrapAutoConfig' = None

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        if hasattr(cls, 'wrapped'):
            cls.instance = cls(cls.wrapped)

    def __post_init__(self):
        self.get_config = config_getter(self.wrapped, typed=self.typed, func=self.get_config)
        self.configure = config_setter(self.wrapped, func=self.configure)
        for name in dir(self):
            if name.startswith('_') or not hasattr(type(self), name) or getattr(self, name, None) is not None:
                continue
            setattr(self, name, getattr(type(self), name))

    def is_unconfigured_property(self, name: str) -> bool:
        return name.startswith('_') or (self.unconfigured_properties is not None and
                                        name in self.unconfigured_properties)

    def get_property_type(self, name: str) -> type | None:
        if self.property_types is None:
            return None
        return self.property_types.get(name, None)

    def get_config(self, instance: object, context: str = None) -> Configuration:
        config = {}
        for property_name in dir(instance):
            if self.is_unconfigured_property(property_name):
                continue
            property_value = getattr(instance, property_name, None)
            if callable(property_value) and not isinstance(property_value, type):
                continue
            property_config = get_config(property_value, context=context)
            property_type = self.get_property_type(property_name)
            if property_type is not None:
                property_config = unbox_type(property_config, context=context)
            config[property_name] = property_config
        return config

    def configure(self, config: Configuration, instance: _ConfigurableValue = None,
                  context: str = None) -> _ConfigurableValue:
        type_, config = unbox_type(config, context=context)
        assert type_ is dict or issubclass(type_, self.wrapped), type_
        if type_ is dict:
            type_ = self.wrapped
        assert isinstance(config, dict)
        assert config.keys() != {'__module__', '__class__', '__instance__'}
        if not isinstance(instance, self.wrapped):
            args = tuple(configure(config[name], context=context) for name in self.init_args or ())
            kwargs = {key: configure(config[value_name], context=context)
                      for key, value_name in (self.init_kwargs or {}).items()}
            instance = type_(*args, **kwargs)
        assert isinstance(instance, type_)
        # TODO: Support wrapper inheritance that parallels wrapped class inheritance.
        # instance = super().configure(config, instance, context)
        for property_name, property_config in config.items():
            if self.is_unconfigured_property(property_name):
                continue
            property_type = self.get_property_type(property_name)
            if property_type is not None:
                property_config = box_type(property_type, property_config, context=context)
            old_property_value = getattr(instance, property_name, None)
            if not (property_type is None or isinstance(old_property_value, property_type)):
                old_property_value = None
            property_value = configure(property_config, old_property_value, context=context)
            if old_property_value == property_value:
                continue
            try:
                setattr(instance, property_name, property_value)
            except AttributeError:
                if not isinstance(property_value, Configurable):
                    raise
        return instance


def auto_config(type_: type[_ConfigurableValue], typed: bool = True, unconfigured_properties: Iterable[str] = None,
                property_types: Mapping[str, type] = None) -> type[_ConfigurableValue]:
    WrapAutoConfig(type_, typed=typed, unconfigured_properties=unconfigured_properties, property_types=property_types)
    return type_


def get_config(obj: Any, *, typed: bool = None, context: str = None) -> Configuration:
    if isinstance(obj, Configurable):
        config = obj.get_config(context=context)
    elif type(obj) in GET_CONFIG_REGISTRY:
        config = GET_CONFIG_REGISTRY[type(obj)](obj, context)
    else:
        raise TypeError(f"Type {type(obj).__name__} from module {type(obj).__module__} is not configurable.")
    if typed or (typed is None and isinstance(obj, Configurable)):
        config = box_type(type(obj), config, context=context)
    elif typed is not None:
        _type, config = unbox_type(config, context=context)
    return config


def configure(config: Configuration, instance: Any = None, *, context: str = None) -> Any:
    type_, config = unbox_type(config, context=context)
    if not isinstance(instance, type_):
        instance = None
    if issubclass(type_, Configurable):
        result = type_.configure(config, instance, context=context)
    elif type_ in CONFIGURE_REGISTRY:
        result = CONFIGURE_REGISTRY[type_](config, instance, context)
    else:
        CONFIGURE_REGISTRY.keys()
        raise TypeError(f"Type {type_.__name__} from module {type_.__module__} is not configurable.")
    if not isinstance(result, type_):
        # noinspection PyArgumentList
        result = type_(result)
    return result


class Configurable(ABC):

    @classmethod
    @abstractmethod
    def configure(cls, config: Configuration, instance: 'Configurable' = None, context: str = None) -> 'Configurable':
        assert isinstance(config, dict)
        if not isinstance(instance, cls):
            instance = cls()
        return instance

    @abstractmethod
    def get_config(self, context: str = None) -> Configuration:
        return {}


class AutoConfigured(Configurable):
    # TODO: Automatically handle subclasses that are also dataclasses.

    @classmethod
    def is_unconfigured_property(cls, property_name: str) -> bool:
        return property_name.startswith('_')

    # noinspection PyUnusedLocal
    @classmethod
    def get_property_type(cls, property_name: str) -> Optional[type[_ConfigurableValue]]:
        return None

    @classmethod
    def configure(cls: type[_Self], config: Configuration, instance: _Self = None, context: str = None) -> _Self:
        type_, config = unbox_type(config, context=context)
        assert type_ in (dict, cls), type_
        assert isinstance(config, dict)
        assert config.keys() != {'__module__', '__class__', '__instance__'}
        if not isinstance(instance, cls):
            instance = cls()
        assert isinstance(instance, cls)
        instance = super().configure(config, instance, context)
        for property_name, property_config in config.items():
            if cls.is_unconfigured_property(property_name):
                continue
            property_type = cls.get_property_type(property_name)
            if property_type is not None:
                property_config = box_type(property_type, property_config, context=context)
            old_property_value = getattr(instance, property_name, None)
            if not (property_type is None or isinstance(old_property_value, property_type)):
                old_property_value = None
            property_value = configure(property_config, old_property_value, context=context)
            if old_property_value == property_value:
                continue
            try:
                setattr(instance, property_name, property_value)
            except AttributeError:
                if not isinstance(property_value, Configurable):
                    raise
        return instance

    def get_config(self, context: str = None) -> Configuration:
        config = super().get_config(context)
        for property_name in dir(self):
            if self.is_unconfigured_property(property_name):
                continue
            property_value = getattr(self, property_name, None)
            if callable(property_value) and not isinstance(property_value, type):
                continue
            property_config = get_config(property_value, context=context)
            property_type = self.get_property_type(property_name)
            if property_type is not None:
                property_config = unbox_type(property_config, context=context)
            config[property_name] = property_config
        return config


# def public_config(config_type: type) -> type:
#     assert isinstance(config_type, type)
#     TYPE_LOOKUP.specifically_allowed_modules.add(config_type.__module__)
#     TYPE_LOOKUP.specifically_allowed_classes.add((config_type.__module__, config_type.__name__))
#     try:
#         found_type = TYPE_LOOKUP.get_type(config_type.__module__, config_type.__name__)
#     except AttributeError:
#         found_type = None
#     if found_type is not config_type:
#         raise ValueError("Only classes appearing at the module level can be registered as public.")
#     return config_type
