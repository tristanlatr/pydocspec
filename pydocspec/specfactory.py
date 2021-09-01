"""
Create customizable docspec classes. 
"""
from typing import Dict, List, Type, Any, Union, Sequence
from typing_extensions import Literal
from importlib import import_module
import attr

import pydocspec
from . import brains

@attr.s(auto_attribs=True)
class Factory:
    """
    Classes are created dynamically with C{type} such that they can inherith from customizable mixin classes. 
    """
    bases: Dict[str, Type[Any]] = attr.ib(factory=dict)
    mixins: Dict[str, List[Type[Any]]] = attr.ib(factory=dict)

    @classmethod
    def default(cls, load_brains:bool=True) -> 'Factory':
        factory = cls(bases={
            'ApiObjectsRoot': pydocspec.ApiObjectsRoot,
            'Class': pydocspec.Class,
            'Function': pydocspec.Function,
            'Module': pydocspec.Module,
            'Data': pydocspec.Data,
            'Indirection': pydocspec.Indirection,
            'Decoration': pydocspec.Decoration,
            'Argument': pydocspec.Argument,
            'Docstring': pydocspec.Docstring,
            'Location': pydocspec.Location,
        })
        if load_brains:
            for mod in brains.get_all_brain_modules():
                factory.import_mixins_from(mod)
        return factory

    def _add_mixin(self, for_class: str, mixin:Type[Any]) -> None:
        """
        Add a mixin class to the specied object in the factory. 
        """
        if for_class not in list(self.bases):
            import warnings
            warnings.warn(f"Invalid class name. Cannot add mixin class {mixin!r} on class '{for_class}'. Possible classes are {', '.join(self.bases.keys())}")
            return
        
        try:
            mixins = self.mixins[for_class]
        except KeyError:
            mixins = []
            self.mixins[for_class] = mixins
        
        assert isinstance(mixins, list)
        mixins.append(mixin)

    def _add_mixins(self, **kwargs:Union[Sequence[Type[Any]], Type[Any]]) -> None:
        """
        Add mixin classes to objects in the factory. 

        :keyword ApiObjectsRoot: Mixin types to apply to the root object.
        :keyword Class: Mixin types to apply to the class object.
        :keyword Function: Mixin types to apply to the function object.
        :keyword Module: Mixin types to apply to the module object.
        :keyword Data: Mixin types to apply to the data object.
        :keyword Indirection: Mixin types to apply to the indirection object.
        :keyword Decoration: Mixin types to apply to the decoration object.
        :keyword Argument: Mixin types to apply to the argument object.
        :keyword Docstring: Mixin types to apply to the docstring object.
        :keyword Location: Mixin types to apply to the location object.
        """
        for key,value in kwargs.items():
            if isinstance(value, Sequence):
                for item in value:
                    self._add_mixin(key, item) # type:ignore[arg-type]
            else:
                self._add_mixin(key, value) # type:ignore[arg-type]

    def import_mixins_from(self, module:Union[str, Any]) -> None:
        """
        Will look for the special mapping C{MIXIN_CLASSES} in the provided module.
        """
        if isinstance(module, str):
            mod = import_module(module)
        else:
            mod = module
        if hasattr(mod, 'MIXIN_CLASSES'):
            mixin_definitions = mod.MIXIN_CLASSES # type:ignore[attr-defined]
            assert isinstance(mixin_definitions, dict), f"{mod}.MIXIN_CLASSES should be a dict, not {type(mixin_definitions)}."
            if any(mixin_definitions.values()):
                self._add_mixins(**mixin_definitions)
                return

            import warnings
            warnings.warn(f"No mixin classes added for module {mod}, check the validity of the MIXIN_CLASSES attribute.")

    def _get_class(self, name:str) -> Type[Any]:
        try:
            return type(name, tuple([self.bases[name]]+self.mixins.get(name, [])), {})
        except KeyError as e:
            raise ValueError(f"Invalid class name {name}") from e
    
    @property
    def ApiObjectsRoot(self) -> Type[pydocspec.ApiObjectsRoot]:
        root = self._get_class('ApiObjectsRoot')
        # set the ApiObjectsRoot.factory class variable.
        assert issubclass(root, pydocspec.ApiObjectsRoot)
        root.factory = self
        return root
    
    @property
    def Class(self) -> Type[pydocspec.Class]:
        klass = self._get_class('Class')
        assert issubclass(klass, pydocspec.Class)
        return klass

    @property
    def Function(self) -> Type[pydocspec.Function]:
        func = self._get_class('Function')
        assert issubclass(func, pydocspec.Function)
        return func

    @property
    def Module(self) -> Type[pydocspec.Module]:
        mod = self._get_class('Module')
        assert issubclass(mod, pydocspec.Module)
        return mod

    @property
    def Data(self) -> Type[pydocspec.Data]:
        data = self._get_class('Data')
        assert issubclass(data, pydocspec.Data)
        return data

    @property
    def Indirection(self) -> Type[pydocspec.Indirection]:
        indirection = self._get_class('Indirection')
        assert issubclass(indirection, pydocspec.Indirection)
        return indirection

    @property
    def Decoration(self) -> Type[pydocspec.Decoration]:
        deco = self._get_class('Decoration')
        assert issubclass(deco, pydocspec.Decoration)
        return deco

    @property
    def Argument(self) -> Type[pydocspec.Argument]:
        arg = self._get_class('Argument')
        assert issubclass(arg, pydocspec.Argument)
        return arg
    
    @property
    def Docstring(self) -> Type[pydocspec.Docstring]:
        arg = self._get_class('Docstring')
        assert issubclass(arg, pydocspec.Docstring)
        return arg
    
    @property
    def Location(self) -> Type[pydocspec.Location]:
        arg = self._get_class('Location')
        assert issubclass(arg, pydocspec.Location)
        return arg

