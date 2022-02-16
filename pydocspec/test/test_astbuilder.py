from typing import Callable, cast
import ast
import sys
import pytest

from pydocspec import astbuilder, visitors
import pydocspec

import astroid.builder
import astroid.nodes

from . import (CapSys, ModFromTextFunction, 
    getbuilder_param, mod_from_text_param, 
    _docspec_python, _back_converter_round_trip1)

posonlyargs = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")
typecomment = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")

@getbuilder_param
def test_class_docstring(getbuilder: Callable[[], astbuilder.Builder]) -> None:
    # test if we catch the docstring for a class
    builder = getbuilder()
    builder.add_module_string('''
    class C:
        """my class"""
    ''', modname='test')
    builder.build_modules()

    klass = builder.root.all_objects['test.C']
    assert klass is not None
    assert klass.docstring is not None
    assert klass.docstring.content == 'my class'
    assert isinstance(klass, pydocspec.Class)
    assert klass.bases is None
    assert klass.decorations is None


@mod_from_text_param
def test_class_decos_and_bases(mod_from_text: ModFromTextFunction, caplog) -> None:
    # test if we catch the bases and decorations for a class
    mod = mod_from_text('''
    @property
    @attr.s(auto_attribs=True, frozen=True)
    class C(str, pkg.MyBase):
        """my class"""
    ''', modname='test')
    #assert caplog.text == ''
    assert len(caplog.text.strip().split('\n')) == 2 # because we can't resolve builtin types for now.
    m = mod.get_member('C')
    assert m is not None
    assert isinstance(m, pydocspec.Class)
    decorations = m.decorations
    assert decorations is not None
    
    assert len(decorations) == 2
    assert [d.name for d in decorations] == ["property", "attr.s"]

    for d in decorations:

        if d.name == 'attr.s':
            assert d.name_ast.as_string() == d.expr_ast.func.as_string()
            assert isinstance(d.expr_ast, astroid.nodes.Call)
            assert d.arglist == ['auto_attribs=True', 'frozen=True']
        else:
            assert d.name_ast.as_string() == d.expr_ast.as_string()

        assert d.expr_ast is not None
        assert isinstance(d.expr_ast, astroid.nodes.NodeNG)

        assert isinstance(d.name_ast, (astroid.nodes.Name, astroid.nodes.Attribute))
    bases = m.bases
    assert bases is not None
    assert len(bases) == 2
    if mod_from_text == _docspec_python.mod_from_text:
        # docspec_python behaves weirdly...
        assert bases == ["str", " pkg.MyBase"]
    else:
        assert bases == ["str", "pkg.MyBase"]
    assert m.bases_ast is not None
    for b in m.bases_ast:
        assert isinstance(b, (astroid.nodes.Name, astroid.nodes.Attribute))

@getbuilder_param
def test_function_name_dulpicate_module(getbuilder: Callable[[], astbuilder.Builder]) -> None:
    """
    It's possible that a function or class name is the same as a module's. 
    The builder should not crash.
    """

    top_src = '''
    class mod: pass # this names shadows the module "mod".
    '''

    mod_src = '''
    from . import mod
    '''

    builder = getbuilder()
    builder.add_module_string(top_src, modname='top', is_package=True)
    builder.add_module_string(mod_src, modname='mod', parent_name='top')
    # processing the tree is mandatory
    builder.build_modules()

    top = builder.root.all_objects['top']
    # mod = builder.root.all_objects['top.mod']
    
    assert top.expand_name('mod') == 'top.mod'
    
    all_mod = builder.root.all_objects.getall('top.mod')
    assert all_mod is not None
    assert len(all_mod) == 2

    assert isinstance(top['mod'], pydocspec.Class)

    # the order seem a bit random...
    assert list(top.get_members('mod')) == [all_mod[0], all_mod[1]]

    assert isinstance(all_mod[0].get_member('mod'), pydocspec.Indirection)
    assert all_mod[0].resolve_name('mod') == top.resolve_name('mod') == top['mod']

    # This is most likely to surprise you when in an __init__.py and you are importing or 
    # defining a value that has the same name as a submodule of the current package. 
    # If the submodule is loaded by any module at any point after the import or definition 
    # of the same name, it will shadow the imported or defined name in the __init__.py’s global namespace.
    # http://python-notes.curiousefficiency.org/en/latest/python_concepts/import_traps.html?highlight=same%20name#the-submodules-are-added-to-the-package-namespace-trap

@getbuilder_param
def test_relative_import_in_package(getbuilder: Callable[[], astbuilder.Builder]) -> None:
    """Relative imports in a package must be resolved by going up one level
    less, since we don't count "__init__.py" as a level.

    Hierarchy::

      top: def f
       - pkg: imports f and g
          - mod: def g
    """

    top_src = '''
    class f: pass
    '''
    mod_src = '''
    class g: pass
    '''
    pkg_src = '''
    from .. import f
    from .mod import g
    '''

    builder = getbuilder()
    # top, pkg, mod
    builder.add_module_string(top_src, modname='top', is_package=True,)
    builder.add_module_string(pkg_src, modname='pkg', parent_name='top', is_package=True,)
    builder.add_module_string(mod_src, modname='mod', parent_name='top.pkg',)
    
    # processing the tree is mandatory
    builder.build_modules()

    top = builder.root.all_objects['top']
    pkg = builder.root.all_objects['top.pkg']
    mod = builder.root.all_objects['top.pkg.mod']
    
    repr_vis = visitors.ReprVisitor(fields=['is_package', 'target'])
    top.walk(repr_vis)
    assert repr_vis.repr == """\
- Module 'top' at l.0, is_package: True
| - Module 'pkg' at l.0, is_package: True
| | - Module 'mod' at l.0
| | | - Class 'g' at l.2
| | - Indirection 'f' at l.2, target: 'top.f'
| | - Indirection 'g' at l.3, target: 'top.pkg.mod.g'
| - Class 'f' at l.2
"""

    assert pkg.expand_name('f') == top.expand_name('f')
    assert pkg.expand_name('g') == mod.expand_name('g')

    assert pkg.resolve_name('f') == top['f']
    assert pkg.resolve_name('g') == mod['g']

@getbuilder_param
def test_relative_import_in_package_star_import(getbuilder: Callable[[], astbuilder.Builder]) -> None:
    """Relative imports in a package must be resolved by going up one level
    less, since we don't count "__init__.py" as a level. 

    Hierarchy::

      top: class f
       - pkg: imports f and * from mod
          - mod: class g, e, h, j
    """

    top_src = '''
    class f: pass
    '''
    mod_src = '''
    __all__=('e','j')
    class g: pass
    class e: pass
    class h: pass
    class j: pass
    '''
    pkg_src = '''
    from .. import f
    from .mod import *
    '''

    builder = getbuilder()
    builder.add_module_string(top_src, modname='top', is_package=True)
    builder.add_module_string(pkg_src, modname='pkg', parent_name='top', is_package=True)
    builder.add_module_string(mod_src, modname='mod', parent_name='top.pkg')
    # processing the tree is mandatory
    builder.build_modules()

    top = builder.root.all_objects['top']
    pkg = builder.root.all_objects['top.pkg']
    mod = builder.root.all_objects['top.pkg.mod']

#     repr_vis = visitors.ReprVisitor()
#     top.walk(repr_vis)
#     assert repr_vis.repr == """\
# - Module 'top' at l.0, is_package: True
# | - Class 'f' at l.2
# | - Module 'pkg' at l.0, is_package: True
# | | - Indirection 'f' at l.2, target: 'top.f'
# | | - Indirection 'e' at l.3, target: 'top.pkg.mod.e'
# | | - Indirection 'j' at l.3, target: 'top.pkg.mod.j'
# """

    assert pkg.expand_name('f') == top.expand_name('f') == 'top.f'
    assert pkg.expand_name('e') == mod.expand_name('e') == 'top.pkg.mod.e'
    assert pkg.expand_name('j') == mod.expand_name('j') == 'top.pkg.mod.j'

    assert pkg.resolve_name('f') == top.get_member('f')
    assert pkg.resolve_name('e') == mod.get_member('e')
    assert pkg.resolve_name('j') == mod.get_member('j')

    assert isinstance(pkg.get_member('e'), pydocspec.Indirection)
    assert isinstance(pkg.get_member('j'), pydocspec.Indirection)

    assert isinstance(mod, pydocspec.Module)
    assert mod.dunder_all == ['e', 'j']
    assert not isinstance(pkg.get_member('h'), pydocspec.Indirection) # not re-exported because of __all__ var
    assert not isinstance(pkg.get_member('g'), pydocspec.Indirection) # not re-exported because of __all__ var

@getbuilder_param
def test_aliasing(getbuilder: Callable[[], astbuilder.Builder]) -> None:

    src_private = '''
    class A:
        pass
    '''
    src_export = '''
    from _private import A as B
    # __all__ = ['B'] # This is not actually needed for the test to pass.
    '''
    src_user = '''
    from public import B
    class C(B):
        pass
    '''

    builder = getbuilder()
    builder.add_module_string(src_private, modname='_private')
    builder.add_module_string(src_export, modname='public')
    builder.add_module_string(src_user, modname='app')
    # processing the tree is mandatory
    builder.build_modules()

    C = builder.root.all_objects['app.C']
    assert isinstance(C, pydocspec.Class)

    assert C.bases == ['B']
    assert C.resolved_bases == [builder.root.all_objects['_private.A']] 

    # The pydoctor's version of this test expected ['public.B'] as the result, this because
    # of the reparenting process applied to objects re-exported by __all__ variable. 
    # pydocspec does not do that, it will return the "true" python name of the origin class.
    # Note1: The initial version (2006) of this test expected ['_private.A'] as the result, too. 
    # Note2:
    # - relying on on-demand processing of other modules is unreliable when
    #   there are cyclic imports: expand_name() on a module that is still being
    #   processed can return the not-found result for a name that does exist. 
    #   This is why we do not rely on expand_name() in the implementation of indirections creation.

@mod_from_text_param
def test_aliasing_recursion(mod_from_text: ModFromTextFunction) -> None:
    src = '''
    class C:
        pass
    from mod import C
    class D(C):
        pass
    '''
    mod = mod_from_text(src, modname='mod')
    D = mod['D']
    assert isinstance(D, pydocspec.Class)
    assert D.bases == ['C'], D.bases
    if mod_from_text == _docspec_python.mod_from_text:
        # In docspec_python, the indirection is added.
        assert D.resolved_bases == ['mod.C'], D.resolved_bases
    else:
        # We don't create indirections that have the exact same qualified name
        # and target, so we resolve the base to the class successfuly.
        # TODO: double check this behaviour.
        assert D.resolved_bases == [mod['C']], D.resolved_bases
        # An older version of this test expected ['mod.C'], Like if it was unresolved. 
        # Now, the indirections that have the same fullname and target are simply ignored.

# TODO: Do a test with __all__variable re-export and assert that no exported members 
# do not get an indirection object created.

@getbuilder_param
@pytest.mark.parametrize('level', (1, 2, 3, 4))
def test_relative_import_past_top(
        getbuilder: Callable[[], astbuilder.Builder],
        level: int,
        caplog
        ) -> None:
    """A warning is logged when a relative import goes beyond the top-level
    package.
    """
    caplog.set_level('WARNING', 'pydocspec')
    builder = getbuilder()
    builder.add_module_string('', modname='pkg', is_package=True)
    builder.add_module_string(f'''
    from {'.' * level + 'X'} import A
    ''', modname='mod', parent_name='pkg')
    # processing the tree is mandatory (not here actually, but process it anyway)
    builder.build_modules()
    
    if level == 1:
        assert not caplog.text
    else:
        assert f"<fromtext>:2: relative import level ({level}) too high" in caplog.text, caplog.text

@mod_from_text_param
def test_class_with_base_from_module(mod_from_text: ModFromTextFunction) -> None:
    src = '''
    from X.Y import A
    from Z import B as C
    class D(A, C):
        class f: pass
    '''
    mod = mod_from_text(src)
    assert len(mod.members) == 3

    ind1 = mod.get_member('A')
    ind2 = mod.get_member('C')
    assert isinstance(ind1, pydocspec.Indirection)
    assert isinstance(ind2, pydocspec.Indirection)
    assert ind1.target == 'X.Y.A'
    assert ind2.target == 'Z.B'

    clsD = mod.get_member('D')
    assert clsD is not None
    assert clsD.full_name == 'test.D'
    assert clsD.docstring == None
    assert isinstance(clsD, pydocspec.Class)
    assert len(clsD.members) == 1

    assert clsD.bases is not None
    assert len(clsD.bases) == 2
    base1, base2 = clsD.resolved_bases
    assert base1 == 'X.Y.A'
    assert base2 == 'Z.B'

@mod_from_text_param
def test_class_with_base_from_module_alt(mod_from_text: ModFromTextFunction) -> None:
    src = '''
    import X
    import Y.Z as M
    class D(X.A, X.B.C, M.C):
        class f: pass
    '''
    mod = mod_from_text(src,)
    if mod_from_text == _docspec_python.mod_from_text:
        # docspec_python adds indirection anyhow
        assert len(mod.members) == 3
    else:
        # our loader does not create indirection that have the same name and target. 
        assert len(mod.members) == 2
        assert mod.get_member('X') == None # we don't create useless indirections.
    
    ind = mod.get_member('M')
    assert isinstance(ind, pydocspec.Indirection)
    assert ind.target == 'Y.Z'

    clsD = mod.get_member('D')
    assert clsD is not None
    assert clsD.full_name == 'test.D'
    assert clsD.docstring == None
    assert isinstance(clsD, pydocspec.Class)
    assert len(clsD.members) == 1

    assert clsD.bases is not None
    assert len(clsD.bases) == 3
    base1, base2, base3 = clsD.resolved_bases
    assert base1 == 'X.A', base1
    assert base2 == 'X.B.C', base2
    assert base3 == 'Y.Z.C', base3

@mod_from_text_param
def test_no_docstring(mod_from_text: ModFromTextFunction) -> None:
    # Inheritance of the docstring of an overridden method depends on
    # methods with no docstring having None in their 'docstring' field.
    mod = mod_from_text('''
    def f():
        pass
    class C:
        def m(self):
            pass
    ''', modname='test')
    f = mod['f']
    assert f is not None
    assert f.docstring is None
    m = mod.resolve_name('C.m')
    assert m is not None
    assert m.docstring is None

@mod_from_text_param
def test_all_recognition(mod_from_text: ModFromTextFunction) -> None:
    """The value assigned to __all__ is parsed to Module.all."""
    mod = mod_from_text('''
    def f():
        pass
    __all__ = ['f']
    ''')
    assert mod.dunder_all == ['f']
    assert '__all__' in list(o.name for o in mod._members())
    # Should pydocspec remove the __all__varible from the members?
    # It's metadata after all...

@mod_from_text_param
def test_docformat_recognition(mod_from_text: ModFromTextFunction) -> None:
    """The value assigned to __docformat__ is parsed to Module.docformat."""
    mod = mod_from_text('''
    __docformat__ = 'Epytext en'

    def f():
        pass
    ''')
    assert mod.docformat == 'Epytext en'
    # assert '__docformat__' not in mod.contents
    # Should pydocspec remove the __docformat__ from the members?
    # It's metadata after all...

@mod_from_text_param
def test_docformat_warn_not_str(mod_from_text: ModFromTextFunction, caplog) -> None:

    mod = mod_from_text('''
    __docformat__ = [i for i in range(3)]

    def f():
        pass
    ''', modname='mod')
    assert '<fromtext>:2: Cannot parse value assigned to "__docformat__": not a string\n' in caplog.text
    assert mod.docformat is None
    assert len(caplog.text.strip().split('\n')) == 1, caplog.text
    # assert '__docformat__' not in mod.contents

@mod_from_text_param
def test_docformat_warn_not_str2(mod_from_text: ModFromTextFunction, caplog) -> None:

    mod = mod_from_text('''
    __docformat__ = 3.14

    def f():
        pass
    ''', modname='mod')
    assert '<fromtext>:2: Cannot parse value assigned to "__docformat__": not a string\n' in caplog.text
    assert mod.docformat == None
    assert len(caplog.text.strip().split('\n')) == 1, caplog.text
    # assert '__docformat__' not in mod.contents

@mod_from_text_param
def test_docformat_warn_empty(mod_from_text: ModFromTextFunction, caplog) -> None:

    mod = mod_from_text('''
    __docformat__ = '  '

    def f():
        pass
    ''', modname='mod')
    assert '<fromtext>:2: Cannot parse value assigned to "__docformat__": empty value\n' in caplog.text
    assert mod.docformat == None
    assert len(caplog.text.strip().split('\n')) == 1, caplog.text
    # assert '__docformat__' not in mod.contents

@mod_from_text_param
def test_function_simple(mod_from_text: ModFromTextFunction) -> None:
    src = '''
    """ MOD DOC """
    def f():
        """This is a docstring."""
    '''
    mod = mod_from_text(src)
    func, = mod.members
    assert func.full_name== 'test.f'
    assert func.docstring == """This is a docstring."""
    assert isinstance(func, pydocspec.Function)
    assert func.is_async is False


@mod_from_text_param
def test_function_async(mod_from_text: ModFromTextFunction) -> None:
    src = '''
    """ MOD DOC """
    async def a():
        """This is a docstring."""
    '''
    mod = mod_from_text(src)
    func, = mod.members
    assert func.full_name == 'test.a'
    assert func.docstring == """This is a docstring."""
    assert isinstance(func, pydocspec.Function)
    assert func.is_async is True


@pytest.mark.parametrize('signature', (
    '()',
    '(*, a, b=None)',
    '(*, a=(), b)',
    '(a, b=3, *c, **kw)',
    '(f=True)',
    '(x=0.1, y=-2)',
    "(s='theory', t=\"con'text\")",
    ))
@mod_from_text_param
def test_function_signature(signature: str, mod_from_text: ModFromTextFunction) -> None:
    """
    A round trip from source to inspect.Signature and back produces
    the original text.
    """
    mod = mod_from_text(f'def f{signature}: ...')
    docfunc, = mod.members
    assert isinstance(docfunc, pydocspec.Function)
    text = str(docfunc.signature())
    assert text == signature

@posonlyargs
@pytest.mark.parametrize('signature', (
    '(x, y, /)',
    '(x, y=0, /)',
    '(x, y, /, z, w)',
    '(x, y, /, z, w=42)',
    '(x, y, /, z=0, w=0)',
    '(x, y=3, /, z=5, w=7)',
    '(x, /, *v, a=1, b=2)',
    '(x, /, *, a=1, b=2, **kwargs)',
    ))
@mod_from_text_param
def test_function_signature_posonly(signature: str, mod_from_text: ModFromTextFunction) -> None:
    if mod_from_text == _docspec_python.mod_from_text:
        # tests with positional only arguments does not currently passes with docspec_python
        # https://github.com/NiklasRosenstein/docspec/issues/57
        return
    test_function_signature(signature, mod_from_text)

@pytest.mark.parametrize('signature', (
    '(a, a)',
    ))
@mod_from_text_param
def test_function_badsig(signature: str, mod_from_text: ModFromTextFunction, caplog) -> None:
    """When a function has an invalid signature, an error is logged and
    the empty signature is returned.

    Note that most bad signatures lead to a SyntaxError, which we cannot
    recover from. This test checks what happens if the AST can be produced
    but inspect.Signature() rejects the parsed parameters.
    """

    if mod_from_text in (_docspec_python.mod_from_text, _back_converter_round_trip1.mod_from_text):
        # This test only passes with our own builder
        return

    mod = mod_from_text(f'def f{signature}: ...', modname='mod')
    assert "<fromtext>:1: mod.f has invalid parameters: " in caplog.text
    docfunc, = mod.members
    assert isinstance(docfunc, pydocspec.Function)
    assert str(docfunc.signature()) == '()'

# @mod_from_text_param
# def test_docformat_warn_overrides(systemcls: Type[model.System], capsys: CapSys) -> None:
#     mod = fromText('''
#     __docformat__ = 'numpy'

#     def f():
#         pass

#     __docformat__ = 'restructuredtext'
#     ''', systemcls=systemcls, modname='mod')
#     captured = capsys.readouterr().out
#     assert captured == 'mod:7: Assignment to "__docformat__" overrides previous assignment\n'
#     assert mod.docformat == 'restructuredtext'
#     assert '__docformat__' not in mod.contents