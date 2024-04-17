from typing import Any

# JSON Configs

*Configuration of nested Python objects with JSON*

## Links
* [Source](https://github.com/hosford42/json_configs)
* [Distribution](https://pypi.python.org/pypi/json_configs)

## License
The package is available for download under the permissive [Revised BSD License](https://github.com/hosford42/json_configs/blob/master/LICENSE).

## Description
JSON Configs is a standardized interface for configuring nested 
Python objects with JSON.

# Usage

Building your own configurable types:

```python
from json_configs import Configuration, AutoConfigured, configure


class MyConfigurableType(AutoConfigured):

    def __init__(self, a: int):
        self.a = a
        self.b = []

    @classmethod
    def configure(cls, config: Configuration, instance: 'MyConfigurableType' = None,
                  context: str = None) -> 'MyConfigurableType':
        if instance is None:
            a = configure(config['a'], context=context)
            instance = cls(a)
        return super().configure(config, instance, context)

    def get_config(self, context: str = None) -> Configuration:
        return super().get_config(context)
```


Handling third-party types:

```python
from json_configs import config_getter, config_setter, Configuration, get_context


@config_getter(bytes)
def get_bytes_config(b: bytes, context: str = None) -> Configuration:
    context = get_context(context)
    encoding = context.get_global_setting('unicode_encoding', 'utf-8')
    return b.decode(encoding)


@config_setter(bytes)
def configure_bytes(config: Configuration, _instance: bytes = None, 
                    context: str = None) -> bytes:
    assert isinstance(config, str)
    context = get_context(context)
    encoding = context.get_global_setting('unicode_encoding', 'utf-8')
    return config.encode(encoding)
```

JSON (de)serialization:

```python
import json
from json_configs import configure, get_config 

configurable_object = ...
serialized = json.dumps(get_config(configurable_object))
deserialized = configure(json.loads(serialized))
```

Access control:

```python
from json_configs import get_context, AutoConfigured


public_context = get_context('public', add=True)
private_context = get_context('private', add=True)

@private_context.register
class MyType(AutoConfigured):
    ...

instance = MyType()
 
private_config = instance.get_config('private')  # Succeeds
public_config = instance.get_config('public')  # Raises exception

instance.configure(private_config, 'private')  # Succeeds
instance.configure(private_config, 'public')  # Raises exception
```