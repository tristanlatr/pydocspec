"""
Extensions sytem.

Mixin classes ca be applied to objects: "Module", "Class", "Function", "Data", "Indirection", 
    "Docstring", "Decoration", "Argument", "Location" and "TreeRoot".

"""

import types
from typing import Any, Dict, Iterable, Iterator, Type, Union
import attr
import sys
import importlib

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
class TreeRootMixin: ...

@attr.s
class PydocspecExtension:
    """
    To create an extension, create a new instance of me named 'extension' like this::
        
        from pydocspec.ext import DataMixin, ClassMixin, ApiObjectVisitorExt, AstVisitorExt
        
        # define extension logic
        class MyDataMixin(DataMixin):
            ...
        class MyClassMixin(ClassMixin):
            ...
        class MyAstVisitor(AstVisitorExt):
            ...
        class MyObjectVisitor(ApiObjectVisitorExt):
            ...

        # export your extension
        extension = pydocspec.ext.PydocspecExtension(
            mixins=(MyDataMixin, MyClassMixin,),
            visitors=(MyAstVisitor, MyObjectVisitor,)
        )

    """
    mixins: Iterable[Type[Any]] = attr.ib(factory=set, converter=set)
    visitors: Iterable[Union[AstVisitorExt, 
                        ApiObjectVisitorExt,
                        Type[AstVisitorExt],
                        Type[ApiObjectVisitorExt]]] = attr.ib(factory=set, converter=set)

# Utilites to load extenions' components.

def _get_all_defaults_ext() -> Iterator[str]:
    """
    Get the full names of all the default extension modules included in L{pydocspec}.
    """
    extmodule = 'pydocspec.ext' #__name__
    for name in importlib_resources.contents(extmodule):
        if (not name.startswith('_') and importlib_resources.is_resource(extmodule, name)) and name.endswith('.py'):
            if name.endswith('.py'): name = name[:-len('.py')]
            yield f"{extmodule}.{name}"

def _get_ext_from_module(module: Union[str, types.ModuleType]) -> PydocspecExtension:
    """
    Will look for the special module variable ``extension: PydocspecExtension`` 
    in the provided module.

    Raises ValueError if module do not provide a valid .extension:PydocspecExtension variable.
    Raise ModuleNotFoundError if module is not found.
    """
    if isinstance(module, str):
        mod = importlib.import_module(module)
    else:
        mod = module
    if hasattr(mod, 'extension'):
        if isinstance(mod.extension, PydocspecExtension):
            return mod.extension
        raise ValueError(f"{mod}.extension should be a PydocspecExtension instance, got {mod.extension}.")
    raise ValueError(f"{mod}.extension variable not found, should be a PydocspecExtension instance.")

_mixins_names_map: Dict[Any, str] = {
        ClassMixin: 'Class',
        ModuleMixin: 'Module',
        FunctionMixin: 'Function',
        DataMixin: 'Data',
        IndirectionMixin: 'Indirection',
        DocstringMixin: 'Docstring',
        DecorationMixin: 'Decoration',
        LocationMixin: 'Location',
        TreeRootMixin: 'TreeRoot',
    }

def _get_mixins(self: PydocspecExtension) -> Dict[str, Type[Any]]:
    mixins_by_name = {}
    for mixin in self.mixins:
        for k,v in _mixins_names_map.items():
            if isinstance(mixin, type) and issubclass(mixin, k):
                mixins_by_name[v] = mixin
                break
        else:
            raise TypeError("Mixin classes must subclass one of the base "
                f"class in module pydocspec.ext: {', '.join(_mixins_names_map)}")
    return mixins_by_name

def _get_astbuild_visitors(self: PydocspecExtension) -> Iterable[Union[AstVisitorExt, Type[AstVisitorExt]]]:
    for ext in self.visitors:
        if isinstance(ext, AstVisitorExt) or isinstance(ext, type) and issubclass(ext, AstVisitorExt):
            yield ext

def _get_postbuild_visitors(self: PydocspecExtension) -> Iterable[Union[ApiObjectVisitorExt, Type[ApiObjectVisitorExt]]]:
    for ext in self.visitors:
        if isinstance(ext, ApiObjectVisitorExt) or isinstance(ext, type) and issubclass(ext, ApiObjectVisitorExt):
            yield ext