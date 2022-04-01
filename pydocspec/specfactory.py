"""
Create customizable docspec classes. 
"""
import logging
from typing import Dict, List, Type, Any, Union, Sequence

import pydocspec

class GenericFactory:

    def __init__(self, bases: Dict[str, Type[Any]]) -> None:
        self.bases = bases
        self.mixins: Dict[str, List[Type[Any]]] = {}

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

        Example::
            class MyClassMixin: ...
            class MyDataMixin: ...
            factory = specfactory.Factory()
            factory.add_mixins(Class=MyClassMixin, Variable=MyDataMixin)

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

    _bases = {
            'TreeRoot': pydocspec.TreeRoot,
            'Class': pydocspec.Class,
            'Function': pydocspec.Function,
            'Module': pydocspec.Module,
            'Variable': pydocspec.Variable,
            'Indirection': pydocspec.Indirection,
            'Decoration': pydocspec.Decoration,
            'Argument': pydocspec.Argument,
            'Docstring': pydocspec.Docstring,
            'Location': pydocspec.Location,
        }
    
    def __init__(self) -> None:
        super().__init__(bases=self._bases)

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
    def Variable(self) -> Type[pydocspec.Variable]:
        data = self.get_class('Variable')
        assert issubclass(data, pydocspec.Variable)
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
