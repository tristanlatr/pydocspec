"""
Just like the `docspec` classes, but with ast attributes and few goodies added such that efficient 
processing can be done on these objects afterwards.

:note: This part of the model is never instanciated as-is, the pydocspec.* classes are always used. 
    The attributes in the pydocspec.* classes are not initialized by default (they are populated by the processor), 
    whereas the attributes listed in this module's classes that re initialized directly by the builder. This
    is why we maintain a separation between the two models. This way. we can use stricter typing information in the processor
    and avoid relying on features that are not yet ready.

:note: Some attributes are implemented as `property` in this package. These attributes depends on the object place in the tree, so they are computed each time. 
    Namely: `ApiObject.full_name`, `ApiObject.dottedname`, `ApiObject.module`, `ApiObject.scope`.
"""

# The model in two: classes in `pydocspec._model` and classes in `pydocspec` top level module. 
# On the one hand there are all the required attributes and on the other hand there are all the attributes that can be 
# populate from the data we already have (some of them must be set in a specific order, 
# for instance the `Class.mro` attribute must set first for the name resolution 
# system to work correctly). So this is why all attributes of all objects are populated in 
# the post-build phase, this way we can control the specific order of the processing. 
# Currently it takes 2 passes of post-build visitors to be sure attributes are correct. 
# See this discussion: https://github.com/twisted/pydoctor/issues/430#issuecomment-912905598 
# for more information à about why we're computing all attributes in the post build step and don't rely
# on on-demand processing.

from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple, Union, Iterable, ClassVar, cast, TYPE_CHECKING, overload
import astroid.nodes
import dataclasses
import attr
import logging
import sys
from pathlib import Path
import types

import docspec

from . import genericvisitor, visitors
from .dupsafedict import DuplicateSafeDict
from .dottedname import DottedName


if TYPE_CHECKING:
    from . import specfactory
    import pydocspec
    import astroid.nodes

_REQUIRED_AT_INIT: Any = object()
# Sentinel for values that should be initiated at init time.

def tree_repr(obj: 'pydocspec.ApiObject', 
              full_name:bool=False, 
              fields: Optional[Sequence[str]]=None) -> str:
    _repr_vis = visitors.ReprVisitor(full_name=full_name, fields=fields)
    _repr_vis.walk(obj)
    return _repr_vis.repr.strip()

# Remove when https://github.com/NiklasRosenstein/docspec/pull/50 is merged.
@dataclasses.dataclass(repr=False, init=False)
class _DefaultDocstring(str):
  location: Optional['Location']
  content: str = cast(str, property(lambda self: str(self)))
  def __new__(cls, content: str, location: Optional['Location']) -> 'Docstring':
    obj = super().__new__(cls, content)
    obj.__dict__['location'] = location
    return obj # type:ignore [return-value]

__docformat__ = 'restructuredtext'
__all__ = [
  'Location',
  'Decoration',
  'Argument',
  'ApiObject',
  'Data',
  'Function',
  'Class',
  'Module',
  'Docstring',
  'TreeRoot',
]

# BASE MODEL CLASSES

Location = docspec.Location

class CanTriggerWarnings:

    def warn(self: Union['ApiObject', 'Decoration', 'Argument', 'Docstring'], # type: ignore[misc]
             msg: str, lineno_offset: int = 0) -> None:
        # TODO: find another way to report warnings.
        lineno = 0
        filename = '<unknow>'
        if self.location:
            lineno = self.location.lineno + lineno_offset
            filename = self.location.filename or filename
        logging.getLogger('pydocspec').warning(f'{filename}:{lineno}: {msg}')

# Adapted from https://github.com/pawamoy/griffe
# Copyright (c) 2021, Timothée Mazzucotelli
class GetMembersMixin:
    """
    This mixin adds a `__getitem__` method to a class or module.
    It makes it easier to access members of an object.

    Returns `self` on an empty key.
    Raises `KeyError` if name cannot be found. 

    :note: Relies on  `ApiObject.get_member`.
    """

    def __getitem__(self: 'pydocspec.ApiObject', #type:ignore[misc]
                    key: Union[str, Iterable[str]]) -> 'pydocspec.ApiObject':
        if isinstance(key, str):
            if not key:
                return self
            parts = key.split(".", 1)
        else:
            parts = list(key)
        if not parts:
            return self
        if len(parts) == 1:
            ob = self.get_member(parts[0])
            if not ob:
                raise KeyError(f"Object named {parts[0]!r} not found in {self.full_name!r}")
            return ob
        return self[parts[0]][parts[1:]]

@attr.s(repr=False)
class TreeRoot:
    # :note: Do not intanciate a new `TreeRoot` manually with ``TreeRoot()``, first create a factory, in one line it gives::
    #     new_root = pydocspec.specfactory.Factory().TreeRoot()

    root_modules: List['pydocspec.Module'] = attr.ib(factory=list, init=False)
    """
    The root modules of the tree.
    """
    
    all_objects: DuplicateSafeDict[str, 'pydocspec.ApiObject'] = attr.ib(factory=DuplicateSafeDict, init=False)
    """
    All objects of the tree in a mapping ``full_name`` -> `ApiObject`.
    
    :note: Special care is taken in order no to shadow objects with duplicate names, see `DuplicateSafeDict`.
    """

    # This class variable is set from Factory itself.
    factory: ClassVar['specfactory.Factory'] = cast('specfactory.Factory', None)
    """
    The factory used to create this collection of objects.
    """
    def __str__(self) -> str:
        return self.__repr__()
    def __repr__(self) -> str:
        return (f"<TreeRoot root modules: {', '.join(m.name for m in self.root_modules)}, "
                f"total objects: {len(self.all_objects)}>")

    @overload
    def add_object(self, ob: 'ApiObject', parent: 'ApiObject') -> None:
        ...
    @overload
    def add_object(self, ob: 'Module', parent: None) -> None:
        ...
    def add_object(self, ob: 'ApiObject', parent: Optional['ApiObject']) -> None:
        """
        Add a newly created object to the tree. 
        Responsible to add the object to the parent namespace, setup parent attribute, setup 
        the new object to the root instance and respectively.

        If parent is `None`, the object passed will be treated as a root module.
        """
        ob = cast('pydocspec.ApiObject', ob)
        if parent is not None:
            assert isinstance(parent, HasMembers), (f"Cannot add new object ({ob!r}) inside {parent.__class__.__name__}. " #type:ignore[unreachable]
                                                            f"{parent.full_name} is not namespace.")
            parent = cast('Union[pydocspec.Class, pydocspec.Module]', parent)
            # setup child in the parent's member attribute
            if ob not in parent.members: #type:ignore[unreachable]
                parent.members.append(ob)
            ob.parent = parent
        else:
            assert isinstance(ob, Module) #type:ignore[unreachable]
            # add root modules to root.root_modules attribute
            self.root_modules.append(cast('pydocspec.Module', ob)) #type:ignore[unreachable]
        
        # Add object to the root.all_objects. 
        obj_dup_name = parent.get_member(ob.name) if parent else None
        should_shadow = True
        if obj_dup_name is not None and obj_dup_name is not ob:
            # If the name is already defined, decide if the new object shoud shadow the existing
            # object by comparing line numbers, object defined after wins.
            should_shadow = obj_dup_name.location.lineno <= ob.location.lineno
        
        self.all_objects.addvalue(ob.full_name, ob, shadow=should_shadow)

        # Set the ApiObject.root attribute
        ob.root = cast('pydocspec.TreeRoot', self)
        
        # in case members are already present in the new object
        for child in ob._members():
            self.add_object(child, ob)


def _enforce_required_at_init_fields(self: 'ApiObject') -> None:
    # enforce that all _spec_fields that are initialized with _REQUIRED_AT_INIT
    # must be passed at at init time.
    for f in self._spec_fields:
        if getattr(self, f) == _REQUIRED_AT_INIT:
            raise TypeError(f"{self.__class__.__name__}.__init__() missing required keyword argument: {f!r}")

# must not use dataclasses
class ApiObject(docspec.ApiObject, CanTriggerWarnings, GetMembersMixin):

    _spec_fields: Tuple[str, ...] = (
        # defaults
        "name", "location", "docstring", 
        # added
        ) # root is not an object field

    def __post_init__(self) -> None:
        super().__post_init__()

        _enforce_required_at_init_fields(self)
        
        # help mypy
        self.parent: Optional[Union['Class', 'Module']]
        self.location: Location

        # This attribute needs to be manually set after the init time of the object.
        self.root: TreeRoot = cast(TreeRoot, NotImplemented)
        """
        `TreeRoot` instance holding references to all objects in the tree.
        """
    
    def __str__(self) -> str:
        return self.__repr__()
    def __repr__(self) -> str:
        return (f"<{type(self).__name__}:{self.full_name} at l.{self.location.lineno}>")
    
    def remove(self) -> None:
        try:
            # remove from parent members
            if self.parent is not None:
                self.parent.members.remove(self)
            else:
                assert isinstance(self, Module)
                self.root.root_modules.remove(cast('pydocspec.Module', self))
        except ValueError:
            pass
        
        self._remove_self() #type:ignore[misc]
    
    def _remove_self(self: 'pydocspec.ApiObject' #type:ignore[misc]
        ) -> None:
        # remove from the all_objects mapping
        try:
            self.root.all_objects.rmvalue(self.full_name, self)
        except KeyError:
            pass
        for o in self._members():
            o._remove_self()

    def replace(self, obs: Union[Iterable['ApiObject'], 'ApiObject'], allow_dup:bool = True) -> None:
        """
        Replace this object by one or more objects.
        
        The node will first be removed, then new object will be added to the tree. 
        """
        if obs == self:
            return
        self.remove()
        self.add_siblings(obs, allow_dup=allow_dup)
    
    def add_siblings(self, obs: Union[Iterable['ApiObject'], 'ApiObject'], allow_dup:bool = True) -> None:
        """
        A new nodes to the tree, siblings to this node.
        """
        if not obs: return None
        assert self.parent is not None, "Cannot add siblings on a root module"
        obslist = obs if isinstance(obs, list) else (obs,)
        for ob in obslist:
            obj_dup_name = self.parent.get_member(ob.name)
            if obj_dup_name is None or allow_dup:
                self.root.add_object(ob, self.parent)

    def _members(self) -> Iterable['pydocspec.ApiObject']:
        if isinstance(self, HasMembers): 
            return cast('List[pydocspec.ApiObject]', self.members)
        else: 
            return ()

    def walk(self: 'pydocspec.ApiObject', #type:ignore[misc]
             visitor: visitors.ApiObjectVisitor) -> None:
        """
        Traverse a tree of objects, calling the `genericvisitor.Visitor.visit` 
        method of `visitor` when entering each node.

        :see: `genericvisitor.Visitor.walk` for more details.
        """
        visitor.walk(self)
        
    def walkabout(self: 'pydocspec.ApiObject', #type:ignore[misc]
                  visitor: visitors.ApiObjectVisitor) -> None:
        """
        Perform a tree traversal similarly to `walk()`, except also call the `genericvisitor.Visitor.depart` 
        method before exiting each node.

        :see: `genericvisitor.Visitor.walkabout` for more details.
        """
        visitor.walkabout(self)
    
    @property
    def dotted_name(self) -> DottedName:
        """
        The fully qualified dotted name of this object, as `DottedName` instance.
        """
        return DottedName(*(ob.name for ob in self.path))

    @property
    def full_name(self) -> str:
        """
        The fully qualified dotted name of this object, as string. 
        This value is used as the key in the `ApiObject.root.all_objects` dictionnary.
        """
        return str(self.dotted_name)
    
    @property
    def module(self) -> 'pydocspec.Module':
        if isinstance(self, Module):
            # pydocspec._model.Module==pydocspec.Module
            return self # type:ignore
        else:
            assert self.parent is not None
            return self.parent.module
    
    @property
    def scope(self) -> Union['pydocspec.Module', 'pydocspec.Class']:
        if isinstance(self, (Module, Class)):
            
            return self # type:ignore
        else:
            assert self.parent is not None
            return self.parent.scope
    
    def get_member(self, name: str) -> Optional['pydocspec.ApiObject']:
        """
        Retrieve a member from the API object. This will always return `None` for
        objects that don't support members (eg. `Function` and `Data`).

        :note: Implementation relies on `ApiObject.root.all_objects` such that
            it will return the last added object in case of duplicate names.
        """
        if isinstance(self, HasMembers):
            member = self.root.all_objects.get(str(self.dotted_name+name))
            if member is not None:
                assert isinstance(member, ApiObject), (name, self, member)
                return member
        return None
    
    def get_members(self, name: str) -> Iterator['pydocspec.ApiObject']:
        """
        Like `get_member` but can return several items with the same name.
        """
        if isinstance(self, HasMembers):
            for member in self.members:
                if member.name == name:
                    assert isinstance(member, ApiObject), (name, self, member)
                    yield cast('pydocspec.ApiObject', member)
    
    def _repr(self: 'pydocspec.ApiObject',  #type:ignore[misc]
             full_name:bool=False, fields:Optional[Sequence[str]]=None) -> str:
        return tree_repr(self, full_name=full_name, fields=fields)

@dataclasses.dataclass(repr=False)
class Data(docspec.Data, ApiObject):
    """
    Represents a variable assignment.
    """

    _spec_fields = (
        # defaults
        "datatype", "value", "modifiers", "semantic_hints",
        # added
        "datatype_ast", "value_ast", "is_type_guarged",
    ) + ApiObject._spec_fields
    
    datatype_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    value_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    
    is_type_guarged: bool = False

    # def __post_init__(self) -> None:
    #     super().__post_init__()
    #     # help mypy
    #     self.parent: Union['Class', 'Module']

@dataclasses.dataclass(repr=False)
class Indirection(docspec.Indirection, ApiObject):
    """
    Represents an imported name. It can be used to properly 
    find the full name target of a link written with a local name. 
    """

    _spec_fields = ("target", "is_type_guarged") + ApiObject._spec_fields

    is_type_guarged: bool = False

@dataclasses.dataclass(repr=False)
class Class(docspec.Class, ApiObject):
    """
    Represents a class definition.
    """
    
    bases_ast: Optional[List[astroid.nodes.NodeNG]] = _REQUIRED_AT_INIT
    is_type_guarged: bool = False
    _ast: Optional[astroid.nodes.ClassDef] = None # is it necessary, yeah.

    _spec_fields = (
        # base fields
        "metaclass", 
        "bases", 
        "decorations", 
        "members", 
        "modifiers", 
        "semantic_hints", 
        # added fields
        "bases_ast", 
        "is_type_guarged", 
        "_ast") + ApiObject._spec_fields # _ast should not be part of fields

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore[assignment]
        self.parent: Union['Class', 'Module']
        self.members: List['ApiObject'] #type:ignore 
        # the real type is Union['Data', 'Function', 'Class', 'Indirection']

@dataclasses.dataclass(repr=False)
class Function(docspec.Function, ApiObject):
    """
    Represents a function definition.
    """

    _spec_fields = (# defaults
                    "modifiers", 
                    "args", 
                    "return_type", 
                    "decorations", 
                    "semantic_hints", 
                    # added
                    "return_type_ast", 
                    "is_type_guarged") + ApiObject._spec_fields

    return_type_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    is_type_guarged: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore
        self.args: List['Argument'] # type:ignore
        self.parent: Union[Class, 'Module']

@dataclasses.dataclass(repr=False)
class Argument(docspec.Argument, CanTriggerWarnings):
    """
    Represents a `Function` argument.
    """
    datatype_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    default_value_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT

@dataclasses.dataclass(repr=False)
class Decoration(docspec.Decoration, CanTriggerWarnings):
    """
    Represents a decorator on a `Class` or `Function`.

    +---------------------------------------+-------------------------+---------------------+-----------------+
    | Code                                  | Decorator.name          | Decorator.arglist   | Notes           |
    +=======================================+=========================+=====================+=================+
    | ``@property``                         | ``property``            | `None`              |                 |
    +---------------------------------------+-------------------------+---------------------+-----------------+
    | ``@functools.lru_cache(max_size=10)`` | ``functools.lru_cache`` | ``["max_size=10"]``	|                 |
    +---------------------------------------+-------------------------+---------------------+-----------------+
    | ``@dec['name']``                      | ``dec['name']``         | `None`              |since Python 3.9 |
    +---------------------------------------+-------------------------+-+-------------------+-----------------+
    | ``@(decorators().name)(a, b=c)``      | ``(decorators().name)`` | ``["a", "b=c"]``    |since Python 3.9 |
    +---------------------------------------+-------------------------+---------------------+-----------------+

    """

    name_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    """The name of the deocration as AST, this can be any kind of expression."""

    expr_ast: Optional[astroid.nodes.NodeNG] = _REQUIRED_AT_INIT
    """The full decoration AST's"""    

@dataclasses.dataclass(repr=False, init=False)
class Docstring(_DefaultDocstring, CanTriggerWarnings):
    ...

@dataclasses.dataclass(repr=False)
class Module(docspec.Module, ApiObject):
    """
    Represents a module, basically a named container for code/API objects. Modules may be nested in other modules.
    """

    _spec_fields = ("members",  "is_package", "is_c_module") + ApiObject._spec_fields

    is_package: bool = False
    """
    Whether this module is a package.
    """

    is_c_module: bool = False
    """
    Whether this module has been imported from a python C extension.
    """

    source_path: Optional[Path] = None
    """
    Module source path. 
    `None` if the module was converted from `docspec`.
    """

    dunder_all: Optional[List[str]] = None # Need to be present in the lower level model because it's used by the builder for processing wildcard imports statements.
    """The module variable __all__ as list of string."""

    _ast: Optional[astroid.nodes.Module] = None
    """
    The whole module's AST. 
    Can be used in post-processes to compute any kind of supplementary informaions not devirable from objects attributes.
    
    Only set when using our own astbuilder. `None` if the module was converted from `docspec`.
    """

    _py_mod: Optional[types.ModuleType] = None
    """
    The live module this object has been created from. 
    `None` for classes coming from AST.
    """

    _py_string: Optional[str] = None
    """
    The module's string. Only set for modules built from string. `None` otherwise.
    """

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.parent: Optional['Module']
        self.members: List['ApiObject'] # type:ignore[assignment]
    
    def __repr__(self) -> str:
        return (f"<{type(self).__name__}:{self.full_name} at {self.location.filename}, l.{self.location.lineno}>")

HasMembers = (Module, Class)
"""
Alias to use with `isinstance`()
"""

Inheritable = (Data, Function) 
"""
Alias to use with `isinstance`()
"""
