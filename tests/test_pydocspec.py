import docspec
from pydocspec import converter
import pydocspec

from .fixtures import mod1, root2, root4

def test_expand_name(mod1: docspec.Module) -> None:
    root = converter.convert_docspec_modules([mod1])[0].root

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

def test_expand_name_subclass(root2: pydocspec.ApiObjectsRoot) -> None:
    root = root2

    subklass = root.all_objects['a.foosub']
    assert isinstance(subklass, pydocspec.Class)

    subklass.find('alias') == root.all_objects['a.foo.alias']

    klass = root.all_objects['a.foo']
    assert isinstance(klass, pydocspec.Class)
    assert klass.sub_classes[0] == subklass

    assert subklass.expand_name('foosub.alias') == 'a.foo.val'
    assert subklass.expand_name('foo.alias') == 'a.foo.val'
    assert subklass.expand_name('saila') == 'a.foo.val'
    assert subklass.expand_name('Union') == 'typing.Union'

def test_signature(root4: pydocspec.ApiObjectsRoot) -> None:
    root = root4

    func = root.all_objects['a.f']
    assert isinstance(func, pydocspec.Function)
    assert str(func.signature()) == "(a: int, *, c: str, **opts: Any) -> None"
    assert str(func.signature(include_types=False)) == "(a, *, c, **opts) -> None"
    assert str(func.signature(include_types=False, include_return_type=False)) == "(a, *, c, **opts)"

    init_method = root.all_objects['a.foo.__init__']
    assert isinstance(init_method, pydocspec.Function)
    assert init_method.is_method==True
    assert str(init_method.signature()) == "(self, port=8001)"
    assert str(init_method.signature(include_self=False)) == "(port=8001)"
    assert str(init_method.signature(include_self=False, include_defaults=False)) == "(port)"
