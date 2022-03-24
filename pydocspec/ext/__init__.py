"""
Extensions sytem.

Mixin classes ca be applied to objects: "Module", "Class", "Function", "Data", "Indirection", 
"Docstring", "Decoration", "Argument", "Location", **BUT NOT "TreeRoot"**.

:Note: Tree root instance is created before extensions are loaded.

You create an extension like this:

.. python::
        
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
    

:note: Mixin classes are going to be added to the list of bases when creating the new objects with the 
`specfactory.Factory`. Because of that, the documentation of the classes listed in this module are incomplete, properties
and methods provided by mixin classes can be review in their respective documentation, under the package `pydocspec.ext`.

"""

import abc
from typing import Any, Callable, Dict, Iterable, Iterator, Tuple, Type, Union, TYPE_CHECKING, cast
import attr
import sys
import importlib

from cached_property import cached_property
import astroid.nodes
import astroid.manager

if TYPE_CHECKING:
    from pydocspec import astbuilder, TreeRoot

# On Python 3.7+, use importlib.resources from the standard library.
# On older versions, a compatibility package must be installed from PyPI.
if sys.version_info < (3, 7):
    import importlib_resources
else:
    import importlib.resources as importlib_resources

from pydocspec.visitors import AstVisitorExt as _AstVisitorExt, ApiObjectVisitorExt as _ApiObjectVisitorExt

# Extensions base API

class ApiObjectVisitorExt(_ApiObjectVisitorExt):...
class AstVisitorExt(_AstVisitorExt): ...

class ClassMixin: ...
class ModuleMixin: ...
class FunctionMixin: ...
class DataMixin: ...
class IndirectionMixin: ...
class DocstringMixin: ...
class DecorationMixin: ...
class LocationMixin: ...

class ApiObjectMixin(ModuleMixin, ClassMixin, FunctionMixin, DataMixin, IndirectionMixin): ...
class HasMembersMixin(ModuleMixin, ClassMixin): ...
class InheritableMixin(FunctionMixin, DataMixin): ...

# class TreeRootMixin: ... # can't add mixins to TreeRoot.

def load_extension_module(builder:'astbuilder.Builder', mod: str) -> None:
    setup_extension = _get_setup_extension_func_from_module(mod)
    setup_extension(ExtRegistrar(mod, builder))

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

@attr.s
class _AstroidTransform(abc.ABC):
    """
    Base class to customize astroid inference system with a bridge to pydocspec tree.
    """
    root: 'TreeRoot' = attr.ib()

    @abc.abstractproperty
    def node_class(self) -> Type['astroid.nodes.NodeNG']:
        """
        Which node class this inference tip applies to.
        """
        ...
    @abc.abstractmethod
    def predicate(self, node: astroid.nodes.AssignName) -> bool:
        ...
    @abc.abstractproperty
    def _transform_func(self) -> Callable[[astroid.nodes.NodeNG],Any]:
        ...
    def register(self) -> None:
        assert self.node_class is not None
        astroid.manager.AstroidManager().register_transform(
            self.node_class, 
            self._transform_func, 
            self.predicate)
    
    def unregister(self) -> None:
        astroid.manager.AstroidManager().unregister_transform(
            self.node_class, 
            self._transform_func, 
            self.predicate)

class AstroidInferenceTip(_AstroidTransform):
    """
    Encapsulate an astroid inference tip to be registered with the `ExtRegistrar`.

    :See: https://pylint.pycqa.org/projects/astroid/en/latest/extending.html#ast-inference-tip-transforms
    """
    @cached_property
    def _transform_func(self) -> Callable[[astroid.nodes.NodeNG], Any]:
        return astroid.inference_tip(self.inference_tip) # type:ignore[no-any-return]
    @abc.abstractmethod
    def inference_tip(self, node: astroid.nodes.NodeNG, ctx:Any) -> astroid.nodes.NodeNG:
        ...

class AstroidTransform(_AstroidTransform):
    """
    Encapsulate an astroid transform to be registered with the `ExtRegistrar`.

    :See: https://pylint.pycqa.org/projects/astroid/en/latest/extending.html#ast-transforms-example
    """
    @cached_property
    def _transform_func(self) -> Callable[[astroid.nodes.NodeNG],Any]:
        return self.transform
    @abc.abstractmethod
    def transform(self, node: astroid.nodes.NodeNG) -> astroid.nodes.NodeNG:
        ...

# Utilites to register extenions' components.

@attr.s(auto_attribs=True)
class ExtRegistrar:
    """
    The extension registrar interface class.
    """
    extname: str
    _builder: 'astbuilder.Builder'

    @staticmethod
    def _setattr_extname_on_objs(obs:Iterable[Any], name:str) -> None:
        # Mark the objects with the extension name they belong to. 
        # This will help us implement a ExtRegistrar.unregister(extname:str) method.
        for o in obs:
            setattr(o, 'extname', name)

    def register_mixins(self, *mixins: Type[Any]) -> None:
        """
        Register mixin classes for model objects. Mixins shoud extend one of the 
        base mixin classes in `pydocspec.ext` module, i.e. `ClassMixin` or `ApiObjectMixin`, etc.
        """
        self._setattr_extname_on_objs(mixins, self.extname)
        self._builder.root.factory.add_mixins(**_get_mixins(*mixins))

    def register_astbuild_visitors(self, 
            *visitors: Union[AstVisitorExt, Type[AstVisitorExt]]) -> None:
        """
        Register AST visitor extensions.
        """
        self._setattr_extname_on_objs(visitors, self.extname)
        # load extensions' ast visitors
        self._builder.visitor_extensions.update(visitors)
    
    def register_postbuild_visitors(self, 
            *visitors: Union[ApiObjectVisitorExt, Type[ApiObjectVisitorExt]]) -> None:
        """
        Register post-build visitor extensions.
        """
        self._setattr_extname_on_objs(visitors, self.extname)
        # load extensions' post build visitors
        self._builder.pprocessor.visitor_extensions.update(visitors)
    
    def register_astroid_transforms(self, 
            *transforms: Type[Union[AstroidInferenceTip, AstroidTransform]]) -> None:
        """
        Register an astroid extensions.
        """
        self._setattr_extname_on_objs(transforms, self.extname)
        # load inference tips
        for t in transforms:
            self._builder.astroid_transforms.append(t(self._builder.root))
    
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


_mixin_to_class_name: Dict[Any, str] = {
        ClassMixin: 'Class',
        ModuleMixin: 'Module',
        FunctionMixin: 'Function',
        DataMixin: 'Data',
        IndirectionMixin: 'Indirection',
        DocstringMixin: 'Docstring',
        DecorationMixin: 'Decoration',
        LocationMixin: 'Location',
        # TreeRootMixin: 'TreeRoot', # can't add mixins to TreeRoot.
    }

def _get_mixins(*mixins: Type[Any]) -> Dict[str, Type[Any]]:
    """
    Transform a list of mixins classes to a dict from the 
    concrete class name to the mixins that must be applied to it.

    This relies on the fact that mixins shoud extend one of the 
    base mixin classes in `pydocspec.ext` module.

    :raises TypeError: If a mixin does not extends any of the 
        provided base mixin classes.
    """
    mixins_by_name = {}
    for mixin in mixins:
        added = False
        for k,v in _mixin_to_class_name.items():
            if isinstance(mixin, type) and issubclass(mixin, k):
                mixins_by_name[v] = mixin
                added = True
                # do not break, such that one class can be added to several class
                # bases if it extends the right types.
        if not added:
            raise TypeError(f"Mixin classes must subclass one of the base, got {mixin} "
                f"class in module pydocspec.ext: {', '.join(m.__name__ for m in _mixin_to_class_name)}")
    return mixins_by_name

def _get_submodules(pkg: str) -> Iterator[str]:
    for name in importlib_resources.contents(pkg):
        if (not name.startswith('_') and importlib_resources.is_resource(pkg, name)) and name.endswith('.py'):
            name = name[:-len('.py')]
            yield f"{pkg}.{name}"

def _get_setup_extension_func_from_module(module: str) -> Callable[[ExtRegistrar], None]:
    """
    Will look for the special function ``setup_extension`` in the provided module.

    Raises ValueError if module do not provide a valid setup_extension() function.
    Raise ModuleNotFoundError if module is not found.

    Returns a tuple(str, callable): extension module name, setup_extension() function.
    """
    mod = importlib.import_module(module)
    
    if hasattr(mod, 'setup_extension'):
        if callable(mod.setup_extension):
            return cast('Callable[[ExtRegistrar], None]', mod.setup_extension)
        raise ValueError(f"{mod}.setup_extension should be a callable, got {mod.setup_extension}.")
    raise ValueError(f"{mod}.setup_extension() function not found.")