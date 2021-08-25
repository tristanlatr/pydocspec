import docspec
from pydocspec import converter
import pydocspec

from .fixtures import mod1

def test_converter_object_types(mod1: docspec.Module) -> None:

    root = converter.convert_docspec_modules([mod1])
    assert isinstance(root.all_objects['a'], pydocspec.Module)
    assert isinstance(root.all_objects['a.Union'], pydocspec.Indirection)
    assert isinstance(root.all_objects['a.foo'], pydocspec.Class)
    assert isinstance(root.all_objects['a.foo.val'], pydocspec.Data)
    assert isinstance(root.all_objects['a.foo.alias'], pydocspec.Data)
    assert isinstance(root.all_objects['a.foo.__init__'], pydocspec.Function)
    assert isinstance(root.all_objects['a.saila'], pydocspec.Data)

def test_root_property(mod1: docspec.Module) -> None:
    root = converter.convert_docspec_modules([mod1])

    assert root.all_objects['a'].root is root
    root.all_objects['a'].get_member('foo').root is root
    root.all_objects['a'].get_member('Union').root is root
    assert root.all_objects['a.Union'].root is root
    assert root.all_objects['a.foo'].root is root
    assert root.all_objects['a.foo.val'].root is root
    assert root.all_objects['a.foo.__init__'].root is root

    root_mod = root.root_modules[0]
    assert root_mod == root.all_objects['a']
    assert root.all_objects['a'].root_module is root.all_objects['a'].module is root_mod
    assert root.all_objects['a.Union'].root_module is root.all_objects['a.Union'].module is root_mod
    assert root.all_objects['a.foo'].root_module is root.all_objects['a.foo'].module is root_mod
    assert root.all_objects['a.foo.val'].root_module is root.all_objects['a.foo.val'].module is root_mod
    assert root.all_objects['a.foo.__init__'].root_module is root.all_objects['a.foo.__init__'].module is root_mod


def test_expand_name(mod1: docspec.Module) -> None:
    root = converter.convert_docspec_modules([mod1])

    saila = root.all_objects['a.saila']
    alias = root.all_objects['a.foo.alias']

    assert isinstance(saila, pydocspec.Data)
    assert isinstance(alias, pydocspec.Data)

    assert saila.is_alias
    assert alias.is_alias

    mod = root.all_objects['a']

    assert mod.expand_name('Union') == 'typing.Union'
    assert mod.expand_name('foo.alias') == 'a.foo.val'
    assert mod.expand_name('saila') == 'a.foo.val'

    klass = root.all_objects['a.foo']

    assert klass.expand_name('alias') == 'a.foo.val'
    assert klass.expand_name('saila') == 'a.foo.val'
    assert klass.expand_name('Union') == 'typing.Union'
