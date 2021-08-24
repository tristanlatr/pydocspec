import docspec
from pydocspec import converter
import pydocspec

from .fixtures import mod1

def test_converter_fix(mod1: docspec.Module) -> None:

    root = converter.to_pydocspec([mod1])
    assert isinstance(root.all_objects['a'], pydocspec.Module)
    assert isinstance(root.all_objects['a.Union'], pydocspec.Indirection)
    assert isinstance(root.all_objects['a.foo'], pydocspec.Class)
    assert isinstance(root.all_objects['a.foo.val'], pydocspec.Data)
    assert isinstance(root.all_objects['a.foo.__init__'], pydocspec.Function)

def test_root_property_fix(mod1: docspec.Module) -> None:
    root = converter.to_pydocspec([mod1])
    assert root.all_objects['a'].root is root
    root.all_objects['a'].get_member('foo').root is root
    root.all_objects['a'].get_member('Union').root is root
    assert root.all_objects['a.Union'].root is root
    assert root.all_objects['a.foo'].root is root
    assert root.all_objects['a.foo.val'].root is root
    assert root.all_objects['a.foo.__init__'].root is root

def test_expand_name_fix(mod1: docspec.Module) -> None:
    root = converter.to_pydocspec([mod1])

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
