from typing import Optional, Type
import ast
import textwrap
import pytest

from pydocspec import loader, postprocessor
import pydocspec

from tests import rootcls_param

def mod_from_ast(
        ast: ast.Module,
        modname: str = '<test>',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.ApiObjectsRoot] = None,
        loadercls: Type[loader.Loader] = loader.Loader,
        rootcls: Optional[Type[pydocspec.ApiObjectsRoot]] = None,
        ) -> pydocspec.Module:

    if root is None:
        assert rootcls is not None, "rootcls must be defined if root is not passed."
        _root = rootcls()
    else:
        _root = root

    _loader = loadercls(_root)

    parent = _root.all_objects.get(parent_name) if parent_name else None
    if parent_name:
        assert isinstance(parent, pydocspec.Module), f"cannot find module '{parent_name}' in system {_root!r}"

    mod = _loader._add_module('<testpath>', modname, 
        # Set containing package as parent.
        # (we tell mypy that we already assert tha parent is a Module)
        parent=parent, #type:ignore[arg-type]
        is_package=is_package)

    assert mod in _loader.unprocessed_modules

    if parent_name is None:
        full_name = modname
    else:
        full_name = f'{parent_name}.{modname}'

    assert mod.full_name == full_name
    assert mod is _root.all_objects[full_name]

    _loader._process_module_ast(ast, mod)

    _loader._processing_map[mod.full_name] = loader.ProcessingState.PROCESSED
    assert mod in _loader.processed_modules

    if root is None:
        # Assume that an implicit system will only contain one module,
        # so post-process it as a convenience.
        postprocessor.PostProcessor.default().post_process(_root)

    return mod

def mod_from_text(
        text: str,
        modname: str = '<test>',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.ApiObjectsRoot] = None,
        loadercls: Type[loader.Loader] = loader.Loader,
        rootcls: Optional[Type[pydocspec.ApiObjectsRoot]] = None,
        ) -> pydocspec.Module:
    
    ast = loader._parse(textwrap.dedent(text))
    return mod_from_ast(ast=ast, modname=modname, is_package=is_package, 
                        parent_name=parent_name, root=root, loadercls=loadercls, 
                        rootcls=rootcls)

@rootcls_param
def test_class_docstring(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
def test_class_decos_and_bases(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
        assert isinstance(d.name_ast, (ast.Name, ast.Attribute))
    bases = m.bases
    assert bases is not None
    assert len(bases) == 2
    assert bases == ["str", "pkg.MyBase"]
    for b in m.bases_ast:
        assert isinstance(b, (ast.Name, ast.Attribute))

@rootcls_param
def test_relative_import_in_package(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
    mod = mod_from_text(mod_src, modname='top.pkg.mod', root=system)
    pkg = mod_from_text(pkg_src, modname='pkg', parent_name='top', is_package=True, root=system)

    assert pkg.expand_name('f') == top.expand_name('f')
    assert pkg.expand_name('g') == mod.expand_name('g')

    assert pkg.resolve_name('f') == top.get_member('f')
    assert pkg.resolve_name('g') == mod.get_member('g')

@rootcls_param
def test_relative_import_in_package_star_import(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
    mod = mod_from_text(mod_src, modname='top.pkg.mod', root=system)
    pkg = mod_from_text(pkg_src, modname='pkg', parent_name='top', is_package=True, root=system)

    assert pkg.expand_name('f') == top.expand_name('f')
    assert pkg.expand_name('e') == mod.expand_name('e')
    assert pkg.expand_name('j') == mod.expand_name('j')

    assert pkg.resolve_name('f') == top.get_member('f')
    assert pkg.resolve_name('e') == mod.get_member('e')
    assert pkg.resolve_name('j') == mod.get_member('j')

    assert isinstance(pkg.get_member('e'), pydocspec.Indirection)
    assert isinstance(pkg.get_member('j'), pydocspec.Indirection)
    assert isinstance(pkg.get_member('h'), pydocspec.Indirection)
    assert isinstance(pkg.get_member('g'), pydocspec.Indirection)

@rootcls_param
def test_aliasing(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
    def addsrc(root: pydocspec.ApiObjectsRoot) -> None:
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
        rootcls: Type[pydocspec.ApiObjectsRoot],
        level: int
        ) -> None:
    """A warning is logged when a relative import goes beyond the top-level
    package.
    """
    with pytest.warns(None) as record:
        system = rootcls()
        mod_from_text('', modname='pkg', is_package=True, root=system)
        mod_from_text(f'''
        from {'.' * level + 'X'} import A
        ''', modname='mod', parent_name='pkg', root=system)
    
    if level == 1:
        assert len(record) == 0, [m.message for m in record]
    else:
        assert f"UserWarning('[pkg.mod] <testpath>:2: relative import level ({level}) too high')" == repr(record[0].message)

@rootcls_param
def test_class_with_base_from_module(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
    assert clsD.full_name == '<test>.D'
    assert clsD.docstring == None
    assert isinstance(clsD, pydocspec.Class)
    assert len(clsD.members) == 1

    assert clsD.bases is not None
    assert len(clsD.bases) == 2
    base1, base2 = clsD.resolved_bases
    assert base1 == 'X.Y.A'
    assert base2 == 'Z.B'

@rootcls_param
def test_class_with_base_from_module_alt(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
    assert clsD.full_name == '<test>.D'
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
# def test_no_docstring(rootcls: Type[pydocspec.ApiObjectsRoot]) -> None:
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
