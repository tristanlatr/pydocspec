"""
Extensions sytem.

Mixin classes ca be applied to objects: "Module", "Class", "Function", "Data", "Indirection", 
"Docstring", "Decoration", "Argument", "Location", **BUT NOT "TreeRoot"**.

:Note: Tree root instance is created before extensions are loaded.

You create an extension like this::
        
    from pydocspec.ext import DataMixin, ClassMixin, ApiObjectVisitorExt, AstVisitorExt, ExtRegistrar
    
    # define extension logic
    class MyDataMixin(DataMixin):
        ...
    class MyClassMixin(ClassMixin):
        ...
    class MyAstVisitor(AstVisitorExt):
        ...
    class MyObjectVisitor(ApiObjectVisitorExt):
        ...

    # configure your extension components in the extension system, with this special function
    # that will be called for each extensions.
    def setup_extension(r:ExtRegistrar) -> None:
        r.register_mixins(MyDataMixin, MyClassMixin)
        r.register_astbuild_visitors(MyAstVisitor)
        r.register_postbuild_visitors(MyObjectVisitor)
    )

"""

import types
from typing import Any, Callable, Dict, Iterable, Iterator, Type, Union, TYPE_CHECKING
import attr
import sys
import importlib

if TYPE_CHECKING:
    from pydocspec import astbuilder

# On Python 3.7+, use importlib.resources from the standard library.
# On older versions, a compatibility package must be installed from PyPI.
if sys.version_info < (3, 7):
    import importlib_resources
else:
    import importlib.resources as importlib_resources

from pydocspec.visitors import AstVisitorExt, ApiObjectVisitorExt

# Extensions base API

ApiObjectVisitorExt=ApiObjectVisitorExt
AstVisitorExt=AstVisitorExt
class ClassMixin: ...
class ModuleMixin: ...
class FunctionMixin: ...
class DataMixin: ...
class IndirectionMixin: ...
class DocstringMixin: ...
class DecorationMixin: ...
class LocationMixin: ...
# class TreeRootMixin: ... # can't add mixins to TreeRoot.

def load_extension_module(builder:'astbuilder.Builder', mod: Union[str, types.ModuleType]) -> None:
    setup_extension = _get_setup_extension_func_from_module(mod)
    setup_extension(ExtRegistrar(builder))

def get_default_extensions() -> Iterator[str]:
    """
    Get the full names of all the default extension modules included in L{pydocspec}.
    """
    return _get_submodules('pydocspec.ext')

def get_optional_extensions() -> Iterator[str]:
    """
    Get the full names of all the default extension modules included in L{pydocspec}.
    """
    return _get_submodules('pydocspec.ext.opt')

# Utilites to register extenions' components.

@attr.s(auto_attribs=True)
class ExtRegistrar:
    """
    The extension registrar interface class.
    """
    _builder: 'astbuilder.Builder'

    def register_mixins(self, *mixins: Type[Any]) -> None:
        self._builder.root.factory.add_mixins(**_get_mixins(*mixins))

    def register_astbuild_visitors(self, 
            *visitors: Union[AstVisitorExt, Type[AstVisitorExt]]) -> None:
        # load extensions' ast visitors
        self._builder.visitor_extensions.update(*visitors)
    
    def register_postbuild_visitors(self, 
            *visitors: Union[ApiObjectVisitorExt, Type[ApiObjectVisitorExt]]) -> None:
        # load extensions' post build visitors
        self._builder.pprocessor.visitor_extensions.update(*visitors)
    
    # TODO: implement me!
    # def register_on_modules_created_callback(self, 
    #         *callback: Callable[['astbuilder.Builder'], None]) -> None:
    #     ...

    # def register_on_astbuild_finished_callback(self, 
    #         *callback: Callable[['astbuilder.Builder'], None]) -> None:
    #     ...
    
    # def register_on_postbuild_finished_callback(self,
    #         *callback: Callable[['astbuilder.Builder'], None]) -> None:
    #     ...


_mixins_names_map: Dict[Any, str] = {
        ClassMixin: 'Class',
        ModuleMixin: 'Module',
        FunctionMixin: 'Function',
        DataMixin: 'Data',
        IndirectionMixin: 'Indirection',
        DocstringMixin: 'Docstring',
        DecorationMixin: 'Decoration',
        LocationMixin: 'Location',
        # TreeRootMixin: 'TreeRoot',
    }

def _get_mixins(*mixins: Type[Any]) -> Dict[str, Type[Any]]:
    mixins_by_name = {}
    for mixin in mixins:
        for k,v in _mixins_names_map.items():
            if isinstance(mixin, type) and issubclass(mixin, k):
                mixins_by_name[v] = mixin
                break
        else:
            raise TypeError("Mixin classes must subclass one of the base "
                f"class in module pydocspec.ext: {', '.join(_mixins_names_map)}")
    return mixins_by_name

def _get_submodules(pkg: str) -> Iterator[str]:
    for name in importlib_resources.contents(pkg):
        if (not name.startswith('_') and importlib_resources.is_resource(pkg, name)) and name.endswith('.py'):
            name = name[:-len('.py')]
            yield f"{pkg}.{name}"

def _get_setup_extension_func_from_module(module: Union[str, types.ModuleType]) -> Callable[[ExtRegistrar], None]:
    """
    Will look for the special function ``setup_extension`` in the provided module.

    Raises ValueError if module do not provide a valid setup_extension() function.
    Raise ModuleNotFoundError if module is not found.
    """
    if isinstance(module, str):
        mod = importlib.import_module(module)
    else:
        mod = module
    if hasattr(mod, 'setup_extension'):
        if callable(mod.setup_extension):
            return mod.setup_extension
        raise ValueError(f"{mod}.setup_extension should be a callable, got {mod.setup_extension}.")
    raise ValueError(f"{mod}.setup_extension() function not found.")