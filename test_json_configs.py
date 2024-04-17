import unittest

from json_configs import AutoConfigured, configure, get_config, get_context


class TestTypeLookup(unittest.TestCase):

    def test_get_simple(self):
        for value in None, 0, 0.0, "", [], {}:
            assert get_config(value) == value

    def test_config_simple(self):
        for value in None, 0, 0.0, "", [], {}:
            assert configure(value) == value

    def test_get_nested(self):
        value = [dict(a=1, b=[2, 3]), ["4", "5", dict(x='x', y=-10.0, z=None)]]
        assert get_config(value) == value

    def test_config_nested(self):
        value = [dict(a=1, b=[2, 3]), ["4", "5", dict(x='x', y=-10.0, z=None)]]
        assert configure(value) == value

    def test_default_access(self):
        alt = get_context('alt', add=True)

        @alt.register
        class Inaccessible(AutoConfigured):
            pass
        obj = Inaccessible()
        with self.assertRaises(ValueError):
            get_config(obj)
        alt_config = get_config(obj, context='alt')
        with self.assertRaises(ValueError):
            configure(alt_config)

    def test_enabled_access(self):
        default_context = get_context()

        @default_context.register
        class Accessible(AutoConfigured):
            pass
        obj = Accessible()
        config = get_config(obj)
        configure(config)

    def test_3rd_party_type(self):
        assert False  # TODO

    def test_nested_udt(self):
        assert False  # TODO
