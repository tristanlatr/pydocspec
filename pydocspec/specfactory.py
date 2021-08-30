"""
Create customizable docspec classes. 
"""
from typing import List, Type, Any, Union, Sequence
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

    _ApiObjectsRoot_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Class_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Function_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Module_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Data_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Indirection_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Decoration_mixins: List[Type[Any]] = attr.ib(factory=list)
    _Argument_mixins: List[Type[Any]] = attr.ib(factory=list)

    _ApiObjectsRoot_base: Type[pydocspec.ApiObjectsRoot] = attr.ib(default=pydocspec.ApiObjectsRoot)
    _Class_base: Type[pydocspec.Class] = attr.ib(default=pydocspec.Class)
    _Function_base: Type[pydocspec.Function] = attr.ib(default=pydocspec.Function)
    _Module_base: Type[pydocspec.Module] = attr.ib(default=pydocspec.Module)
    _Data_base: Type[pydocspec.Data] = attr.ib(default=pydocspec.Data)
    _Indirection_base: Type[pydocspec.Indirection] = attr.ib(default=pydocspec.Indirection)
    _Decoration_base: Type[pydocspec.Decoration] = attr.ib(default=pydocspec.Decoration)
    _Argument_base: Type[pydocspec.Argument] = attr.ib(default=pydocspec.Argument)

    @classmethod
    def default(cls) -> 'Factory':
        factory = cls()
        for mod in brains.get_all_brain_modules():
            factory.import_mixins_from(mod)
        return factory

    def _add_mixin(self, for_class: Literal['ApiObjectsRoot', 'Class', 'Function', 'Module', 'Data', 
                                           'Indirection', 'Decoration', 'Argument'], 
                  mixin:Type[Any]) -> None:
        """
        Add a mixin class to the specied object in the factory. 
        """
        try:
            mixins = getattr(self, f"_{for_class}_mixins")
        except AttributeError as e:
            raise AttributeError(f'Class name "{for_class}" is invalid. Please double check the documentation.') from e
        assert isinstance(mixins, list)
        mixins.append(mixin)

    def _add_mixins(self, **kwargs:Union[Sequence[Type[Any]], Type[Any]]) -> None:
        """
        Add mixin classes to objects in the factory. 

        @keyword ApiObjectsRoot: Mixin types to apply to the root object.
        @keyword Class: Mixin types to apply to the class object.
        @keyword Function: Mixin types to apply to the function object.
        @keyword Module: Mixin types to apply to the module object.
        @keyword Data: Mixin types to apply to the data object.
        @keyword Indirection: Mixin types to apply to the indirection object.
        @keyword Decoration: Mixin types to apply to the decoration object.
        @keyword Argument: Mixin types to apply to the argument object.
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

    @property
    def ApiObjectsRoot(self) -> Type[pydocspec.ApiObjectsRoot]:
        root = type('ApiObjectsRoot', tuple([self._ApiObjectsRoot_base]+self._ApiObjectsRoot_mixins), {})
        # set the ApiObjectsRoot.factory class variable.
        assert issubclass(root, pydocspec.ApiObjectsRoot)
        root.factory = self
        return root
    
    @property
    def Class(self) -> Type[pydocspec.Class]:
        klass = type('Class', tuple([self._Class_base]+self._Class_mixins), {})
        assert issubclass(klass, pydocspec.Class)
        return klass

    @property
    def Function(self) -> Type[pydocspec.Function]:
        func = type('Function', tuple([self._Function_base]+self._Function_mixins), {})
        assert issubclass(func, pydocspec.Function)
        return func

    @property
    def Module(self) -> Type[pydocspec.Module]:
        mod = type('Module', tuple([self._Module_base]+self._Module_mixins), {})
        assert issubclass(mod, pydocspec.Module)
        return mod

    @property
    def Data(self) -> Type[pydocspec.Data]:
        data = type('Data', tuple([self._Data_base]+self._Data_mixins), {})
        assert issubclass(data, pydocspec.Data)
        return data

    @property
    def Indirection(self) -> Type[pydocspec.Indirection]:
        indirection = type('Indirection', tuple([self._Indirection_base]+self._Indirection_mixins), {})
        assert issubclass(indirection, pydocspec.Indirection)
        return indirection

    @property
    def Decoration(self) -> Type[pydocspec.Decoration]:
        deco = type('Decoration', tuple([self._Decoration_base]+self._Decoration_mixins), {})
        assert issubclass(deco, pydocspec.Decoration)
        return deco

    @property
    def Argument(self) -> Type[pydocspec.Argument]:
        arg = type('Argument', tuple([self._Argument_base]+self._Argument_mixins), {})
        assert issubclass(arg, pydocspec.Argument)
        return arg

