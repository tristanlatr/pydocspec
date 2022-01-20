from typing import Optional, Type, cast
import ast
import textwrap
import pytest

from pydocspec import astbuilder, processor, visitors
import pydocspec

import astroid.builder
import astroid.nodes

from . import CapSys, rootcls_param

_parse_mod_str = astroid.builder.AstroidBuilder().string_build

def mod_from_ast(
        ast: astroid.nodes.Module,
        modname: str = 'test',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.TreeRoot] = None,
        rootcls: Optional[Type[pydocspec.TreeRoot]] = None,
        ) -> pydocspec.Module:

    if root is None:
        assert rootcls is not None, "rootcls must be defined if root is not passed."
        _root = rootcls()
    else:
        _root = root

    builder = astbuilder.Builder(_root)

    parent = _root.all_objects.get(parent_name) if parent_name else None
    if parent_name:
        assert isinstance(parent, pydocspec.Module), f"cannot find module '{parent_name}' in system {_root!r}"

    mod = builder._add_module('<testpath>', modname, 
        # Set containing package as parent.
        # (we tell mypy that we already assert tha parent is a Module)
        parent=parent, #type:ignore[arg-type]
        is_package=is_package)

    assert mod in builder.unprocessed_modules

    if parent_name is None:
        full_name = modname
    else:
        full_name = f'{parent_name}.{modname}'

    assert mod.full_name == full_name
    assert mod is _root.all_objects[full_name]

    builder._process_module_ast(ast, mod)

    builder.processing_map[mod.full_name] = astbuilder.ProcessingState.PROCESSED

    if root is None:
        # Assume that an implicit system will only contain one module,
        # so process it as a convenience. If it contains more that one module, it should be processed
        processor.Processor.default().process(_root)

    return cast(pydocspec.Module, mod)

def mod_from_text(
        text: str,
        modname: str = 'test',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.TreeRoot] = None,
        rootcls: Optional[Type[pydocspec.TreeRoot]] = None,
        ) -> pydocspec.Module:
    
    ast = _parse_mod_str(textwrap.dedent(text), modname)
    return mod_from_ast(ast=ast, modname=modname, is_package=is_package, 
                        parent_name=parent_name, root=root, rootcls=rootcls)

@rootcls_param
def test_class_docstring(rootcls: Type[pydocspec.TreeRoot]) -> None:
    # test if we catch the docstring for a class
    mod = mod_from_text('''
    class C:
        """my class"""
    ''', modname='test', rootcls=rootcls)
    m = mod.get_member('C')
    assert m is not None
    assert m.docstring is not None
    assert m.docstring.content == 'my class'
    assert isinstance(m, pydocspec.Class)
    assert m.bases is None
    assert m.decorations is None


@rootcls_param
def test_class_decos_and_bases(rootcls: Type[pydocspec.TreeRoot]) -> None:
    # test if we catch the bases and decorations for a class
    mod = mod_from_text('''
    @property
    @attr.s
    class C(str, pkg.MyBase):
        """my class"""
    ''', modname='test', rootcls=rootcls)
    m = mod.get_member('C')
    assert m is not None
    assert isinstance(m, pydocspec.Class)
    decorations = m.decorations
    assert decorations is not None
    assert len(decorations) == 2
    assert [d.name for d in decorations] == ["property", "attr.s"]
    for d in decorations:
        assert d.name_ast == d.expr_ast
        assert isinstance(d.name_ast, (astroid.nodes.Name, astroid.nodes.Attribute))
    bases = m.bases
    assert bases is not None
    assert len(bases) == 2
    assert bases == ["str", "pkg.MyBase"]
    assert m.bases_ast is not None
    for b in m.bases_ast:
        assert isinstance(b, (astroid.nodes.Name, astroid.nodes.Attribute))

#TODO: fix me!
@pytest.mark.xfail
@rootcls_param
def test_function_name_dulpicate_module(rootcls: Type[pydocspec.TreeRoot]) -> None:
    """
    It's possible that a function or class name is the same as a module's. 
    The builder should not crash.
    """

    top_src = '''
    class mod: pass # this names shadows the module "mod".
    '''

    mod_src = '''
    from .. import mod
    '''

    system = rootcls()
    
    top = mod_from_text(top_src, modname='top', is_package=True, root=system)
    mod = mod_from_text(mod_src, modname='mod', parent_name='top', root=system)
    # processing the tree is mandatory
    processor.Processor.default().process(system)

    assert top.expand_name('mod') == 'top.mod'
    
    all_mod = system.all_objects.getall('top.mod')
    assert all_mod is not None
    assert len(all_mod) == 2

    assert isinstance(top.get_member('mod'), pydocspec.Class) # we get the module currently.
    assert list(top.get_members('mod')) == [all_mod[0], all_mod[1]]
    assert isinstance(mod.get_member('mod'), pydocspec.Indirection)
    assert mod.resolve_name('mod') is top.resolve_name('mod')

    # This is most likely to surprise you when in an __init__.py and you are importing or 
    # defining a value that has the same name as a submodule of the current package. 
    # If the submodule is loaded by any module at any point after the import or definition 
    # of the same name, it will shadow the imported or defined name in the __init__.py’s global namespace.
    # http://python-notes.curiousefficiency.org/en/latest/python_concepts/import_traps.html?highlight=same%20name#the-submodules-are-added-to-the-package-namespace-trap

@rootcls_param
def test_relative_import_in_package(rootcls: Type[pydocspec.TreeRoot]) -> None:
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

    system = rootcls()
    top = mod_from_text(top_src, modname='top', is_package=True, root=system)
    pkg = mod_from_text(pkg_src, modname='pkg', parent_name='top', is_package=True, root=system)
    mod = mod_from_text(mod_src, modname='mod', parent_name='top.pkg', root=system)
    # processing the tree is mandatory
    processor.Processor.default().process(system)

    repr_vis = visitors.ReprVisitor()
    top.walk(repr_vis)
    assert repr_vis.repr == """\
- Module 'top' at l.0, is_package: True, source_path: <testpath>
| - Class 'f' at l.2
| - Module 'pkg' at l.0, is_package: True, source_path: <testpath>
| | - Indirection 'f' at l.2, target: 'top.f'
| | - Indirection 'g' at l.3, target: 'top.pkg.mod.g'
| | - Module 'mod' at l.0, source_path: <testpath>
| | | - Class 'g' at l.2
"""

    assert pkg.expand_name('f') == top.expand_name('f')
    assert pkg.expand_name('g') == mod.expand_name('g')

    assert pkg.resolve_name('f') == top['f']
    assert pkg.resolve_name('g') == mod['g']

@rootcls_param
def test_relative_import_in_package_star_import(rootcls: Type[pydocspec.TreeRoot]) -> None:
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

    system = rootcls()
    top = mod_from_text(top_src, modname='top', is_package=True, root=system)
    mod = mod_from_text(mod_src, modname='top.pkg.mod', root=system) # a hack to make it work, the mod won't be actually present in the tree but still accessible with TreeRoot.all_objects
    pkg = mod_from_text(pkg_src, modname='pkg', parent_name='top', is_package=True, root=system)
    # processing the tree is mandatory
    processor.Processor.default().process(system)

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

    # does not work since we don't collect data for now
    # assert not isinstance(pkg.get_member('h'), pydocspec.Indirection) # not re-exported because of __all__ var
    # assert not isinstance(pkg.get_member('g'), pydocspec.Indirection) # not re-exported because of __all__ var

@rootcls_param
def test_aliasing(rootcls: Type[pydocspec.TreeRoot]) -> None:
    def addsrc(root: pydocspec.TreeRoot) -> None:
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
        mod_from_text(src_private, modname='_private', root=root)
        mod_from_text(src_export, modname='public', root=root)
        mod_from_text(src_user, modname='app', root=root)
        # processing the tree is mandatory
        processor.Processor.default().process(root)

    root = rootcls()
    addsrc(root)
    C = root.all_objects['app.C']
    assert isinstance(C, pydocspec.Class)

    assert C.bases == ['B']
    assert C.resolved_bases == [root.all_objects['_private.A']] 

    # The pydoctor's version of this test expected ['public.B'] as the result, this because
    # of the reparenting process applied to objects re-exported by __all__ variable. 
    # pydocspec does not do that, it will return the "true" python name of the origin class.
    # Note1: The initial version (2006) of this test expected ['_private.A'] as the result, too. 
    # Note2:
    # - relying on on-demand processing of other modules is unreliable when
    #   there are cyclic imports: expand_name() on a module that is still being
    #   processed can return the not-found result for a name that does exist. 
    #   This is why we do not rely on expand_name() in the implementation of indirections creation.

# TODO: Do a test with __all__variable re-export and assert that no exported members 
# do not get an indirection object created.

@rootcls_param
@pytest.mark.parametrize('level', (1, 2, 3, 4))
def test_relative_import_past_top(
        rootcls: Type[pydocspec.TreeRoot],
        level: int,
        caplog
        ) -> None:
    """A warning is logged when a relative import goes beyond the top-level
    package.
    """
    caplog.set_level('WARNING', 'pydocspec')
    system = rootcls()
    mod_from_text('', modname='pkg', is_package=True, root=system)
    mod_from_text(f'''
    from {'.' * level + 'X'} import A
    ''', modname='mod', parent_name='pkg', root=system)
    # processing the tree is mandatory (not here actually, but process it anyway)
    processor.Processor.default().process(system)
    
    if level == 1:
        assert not caplog.text
    else:
        assert f"<testpath>:2: relative import level ({level}) too high" in caplog.text, caplog.text

@rootcls_param
def test_class_with_base_from_module(rootcls: Type[pydocspec.TreeRoot]) -> None:
    src = '''
    from X.Y import A
    from Z import B as C
    class D(A, C):
        class f: pass
    '''
    mod = mod_from_text(src, rootcls=rootcls)
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

@rootcls_param
def test_class_with_base_from_module_alt(rootcls: Type[pydocspec.TreeRoot]) -> None:
    src = '''
    import X
    import Y.Z as M
    class D(X.A, X.B.C, M.C):
        class f: pass
    '''
    mod = mod_from_text(src, rootcls=rootcls)
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

# @rootcls_param
# def test_no_docstring(rootcls: Type[pydocspec.TreeRoot]) -> None:
#     # Inheritance of the docstring of an overridden method depends on
#     # methods with no docstring having None in their 'docstring' field.
#     mod = mod_from_text('''
#     def f():
#         pass
#     class C:
#         def m(self):
#             pass
#     ''', modname='test', rootcls=rootcls)
#     f = mod.get_member('f')
#     assert f is not None
#     assert f.docstring is None
#     m = mod.resolve_name('C.m')
#     assert m is not None
#     assert m.docstring is None
