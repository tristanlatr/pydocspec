from typing import Optional, Type
import ast
import textwrap
import pytest

from pydocspec import loader, specfactory, postprocessor
import pydocspec

default_factory = specfactory.Factory.default()
no_brain_factory = specfactory.Factory.default(load_brains=False)
rootcls_param = pytest.mark.parametrize(
    'rootcls', (no_brain_factory.ApiObjectsRoot, default_factory.ApiObjectsRoot)
    )

def mod_from_ast(
        ast: ast.Module,
        modname: str = '<test>',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.ApiObjectsRoot] = None,
        loadercls: Optional[Type[loader.Loader]] = loader.Loader,
        rootcls: Type[pydocspec.ApiObjectsRoot] = default_factory.ApiObjectsRoot,
        ) -> pydocspec.Module:

    if root is None:
        _root = rootcls()
    else:
        _root = root

    _loader = loadercls(_root)

    mod = _loader._add_module('<testing>', modname, 
        # Set containing package as parent.
        parent=_root.all_objects[parent_name] if parent_name else None,
        is_package=is_package)

    assert mod in _loader.unprocessed_modules

    if parent_name is None:
        full_name = modname
    else:
        full_name = f'{parent_name}.{modname}'

    _loader._process_module_ast(ast, mod)
    assert mod is _root.all_objects[full_name]

    _loader._processing_map[mod.full_name] = loader.ProcessingState.PROCESSED
    assert mod in _loader.processed_modules

    if root is None:
        # Assume that an implicit system will only contain one module,
        # so post-process it as a convenience.
        postprocessor.PostProcessor.default().post_process(_root)

    return mod

def mod_from_text(
        text: str,
        *,
        modname: str = '<test>',
        is_package: bool = False,
        parent_name: Optional[str] = None,
        root: Optional[pydocspec.ApiObjectsRoot] = None,
        loadercls: Optional[Type[loader.Loader]] = loader.Loader,
        rootcls: Type[pydocspec.ApiObjectsRoot] = default_factory.ApiObjectsRoot,
        ) -> pydocspec.Module:
    
    ast = loader._parse(textwrap.dedent(text))
    return mod_from_ast(ast, modname, is_package, parent_name, root, loadercls, rootcls)

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
