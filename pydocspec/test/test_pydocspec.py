import re
from typing import Optional

import pytest
import docspec
from pydocspec import converter, astroidutils, processor
import pydocspec

from .fixtures import mod1, root2, root4
from . import ModFromTextFunction, mod_from_text_param, _default_astbuilder

def test_expand_name(mod1: docspec.Module) -> None:
    root = converter.convert_docspec_modules([mod1])

    saila = root.all_objects['a.saila']
    alias = root.all_objects['a.foo.alias']

    assert isinstance(saila, pydocspec.Data)
    assert isinstance(alias, pydocspec.Data)

    assert processor.data_attr.is_alias(saila)
    assert processor.data_attr.is_alias(alias)
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

def test_expand_name_subclass(root2: pydocspec.TreeRoot) -> None:
    root = root2

    subklass = root.all_objects['a.foosub']
    assert isinstance(subklass, pydocspec.Class)

    subklass.find('alias') == root.all_objects['a.foo.alias']

    klass = root.all_objects['a.foo']
    assert isinstance(klass, pydocspec.Class)
    assert klass.subclasses[0] == subklass

    assert subklass.expand_name('foosub.alias') == 'a.foo.val'
    assert subklass.expand_name('foo.alias') == 'a.foo.val'
    assert subklass.expand_name('saila') == 'a.foo.val'
    assert subklass.expand_name('Union') == 'typing.Union'

def test_signature(root4: pydocspec.TreeRoot) -> None:
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

@mod_from_text_param
def test_node2fullname(mod_from_text:ModFromTextFunction) -> None:
    """The node2fullname() function finds the full (global) name for
    a name expression in the AST.
    """
    # https://github.com/NiklasRosenstein/docspec/issues/34
    # mod = mod_from_text('''
    # class session:
    #     from twisted.conch.interfaces import ISession
    #     ''', modname='test')

    mod = mod_from_text('''
    from twisted.conch.interfaces import ISession
    class session:
        ISession=ISession
        ''', modname='test')

    def lookup(expr: str) -> Optional[str]:
        return astroidutils.node2fullname(astroidutils.extract_expr(expr), mod)

    # None is returned for non-name nodes.
    assert lookup('123') is None
    # Local names are returned with their full name.
    assert lookup('session') == 'test.session'
    # A name that has no match at the top level is returned as-is.
    assert lookup('nosuchname') == 'nosuchname'
    # Unknown names are resolved as far as possible.
    assert lookup('session.nosuchname') == 'test.session.nosuchname'
    # Aliases are resolved on local names.
    assert lookup('session.ISession') == 'twisted.conch.interfaces.ISession'
    # Aliases are resolved on global names.
    assert lookup('test.session.ISession') == 'twisted.conch.interfaces.ISession'

def test_arguments_required_at_init() -> None:
    mod = _default_astbuilder.mod_from_text('')

    with pytest.raises(TypeError, match=re.escape("Class.__init__() missing required keyword argument: 'bases_ast'")):
        mod.root.factory.Class(name='mycls', 
                                location=None, 
                                docstring=None, 
                                metaclass=None,
                                bases=None,
                                decorations=None,
                                members=[])
    
    with pytest.raises(TypeError, match=re.escape("Function.__init__() missing required keyword argument: 'return_type_ast'")):
        mod.root.factory.Function(
                                name='myfunc', 
                                location=None, 
                                docstring=None, 
                                args=[], 
                                modifiers=[], 
                                return_type='str', 
                                decorations=[],)