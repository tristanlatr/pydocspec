"""
Create customizable docspec classes. 
"""
import logging
from typing import Dict, Generic, List, Type, Any, Union, Sequence, TypeVar
from typing_extensions import Literal
from importlib import import_module
import attr

import pydocspec
from . import brains, _model

@attr.s(auto_attribs=True)
class GenericFactory:
    bases: Dict[str, Type[Any]]
    mixins: Dict[str, List[Type[Any]]] = attr.ib(factory=dict)

    def add_mixin(self, for_class: str, mixin:Type[Any]) -> None:
        """
        Add a mixin class to the specied object in the factory. 
        """
        if for_class not in list(self.bases):
            logging.getLogger('pydocspec').warning(f"Invalid class name. Cannot add mixin class {mixin!r} on class '{for_class}'. Possible classes are {', '.join(self.bases.keys())}")
            return
        
        try:
            mixins = self.mixins[for_class]
        except KeyError:
            mixins = []
            self.mixins[for_class] = mixins
        
        assert isinstance(mixins, list)
        mixins.append(mixin)

    def add_mixins(self, **kwargs:Union[Sequence[Type[Any]], Type[Any]]) -> None:
        """
        Add mixin classes to objects in the factory. 

        :param kwargs: Minin(s) classes to apply to names.
        """
        for key,value in kwargs.items():
            if isinstance(value, Sequence):
                for item in value:
                    self.add_mixin(key, item)
            else:
                self.add_mixin(key, value)

    def get_class(self, name:str) -> Type[Any]:
        try:
            return type(name, tuple([self.bases[name]]+self.mixins.get(name, [])), {})
        except KeyError as e:
            raise ValueError(f"Invalid class name: '{name}'") from e

class Factory(GenericFactory):
    """
    Classes are created dynamically with `type` such that they can inherith from customizable mixin classes. 
    """

    bases = {
            'TreeRoot': pydocspec.TreeRoot,
            'Class': pydocspec.Class,
            'Function': pydocspec.Function,
            'Module': pydocspec.Module,
            'Data': pydocspec.Data,
            'Indirection': pydocspec.Indirection,
            'Decoration': pydocspec.Decoration,
            'Argument': pydocspec.Argument,
            'Docstring': pydocspec.Docstring,
            'Location': pydocspec.Location,
        }

    @classmethod
    def default(cls, load_brains:bool=False) -> 'Factory':
        factory = cls(Factory.bases)
        if load_brains:
            for mod in brains.get_all_brain_modules():
                factory.import_mixins_from(mod)
        return factory

    def import_mixins_from(self, module:Union[str, Any]) -> None:
        """
        Will look for the special mapping ``pydocspec_mixin`` in the provided module.
        """
        if isinstance(module, str):
            mod = import_module(module)
        else:
            mod = module
        if hasattr(mod, 'pydocspec_mixin'):
            mixin_definitions = mod.pydocspec_mixin
            assert isinstance(mixin_definitions, dict), f"{mod}.pydocspec_mixin should be a dict, not {type(mixin_definitions)}."
            if any(mixin_definitions.values()):
                self.add_mixins(**mixin_definitions)
                return
            logging.getLogger('pydocspec').warning(f"No mixin classes added for module {mod}, check the validity of the pydocspec_mixin attribute.")

    @property
    def TreeRoot(self) -> Type[pydocspec.TreeRoot]:
        root = self.get_class('TreeRoot')
        # set the TreeRoot.factory class variable.
        assert issubclass(root, pydocspec.TreeRoot)
        root.factory = self
        return root
    
    @property
    def Class(self) -> Type[pydocspec.Class]:
        klass = self.get_class('Class')
        assert issubclass(klass, pydocspec.Class)
        return klass

    @property
    def Function(self) -> Type[pydocspec.Function]:
        func = self.get_class('Function')
        assert issubclass(func, pydocspec.Function)
        return func

    @property
    def Module(self) -> Type[pydocspec.Module]:
        mod = self.get_class('Module')
        assert issubclass(mod, pydocspec.Module)
        return mod

    @property
    def Data(self) -> Type[pydocspec.Data]:
        data = self.get_class('Data')
        assert issubclass(data, pydocspec.Data)
        return data

    @property
    def Indirection(self) -> Type[pydocspec.Indirection]:
        indirection = self.get_class('Indirection')
        assert issubclass(indirection, pydocspec.Indirection)
        return indirection

    @property
    def Decoration(self) -> Type[pydocspec.Decoration]:
        deco = self.get_class('Decoration')
        assert issubclass(deco, pydocspec.Decoration)
        return deco

    @property
    def Argument(self) -> Type[pydocspec.Argument]:
        arg = self.get_class('Argument')
        assert issubclass(arg, pydocspec.Argument)
        return arg
    
    @property
    def Docstring(self) -> Type[pydocspec.Docstring]:
        doc = self.get_class('Docstring')
        assert issubclass(doc, pydocspec.Docstring)
        return doc
    
    @property
    def Location(self) -> Type[pydocspec.Location]:
        loc = self.get_class('Location')
        assert issubclass(loc, pydocspec.Location)
        return loc