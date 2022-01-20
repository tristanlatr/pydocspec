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

from typing import Any, Callable, Iterator, List, Optional, Union, Iterable, ClassVar, cast, TYPE_CHECKING, overload
import astroid.nodes
import dataclasses
import attr
import logging
import sys
from pathlib import Path

import docspec

from . import genericvisitor
from .dupsafedict import DuplicateSafeDict
from .dottedname import DottedName


if TYPE_CHECKING:
    from . import specfactory
    import astroid.nodes

# Remove when https://github.com/NiklasRosenstein/docspec/pull/50 is merged.
@dataclasses.dataclass(init=False)
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
]

# BASE MODEL CLASSES

Location = docspec.Location

class CanTriggerWarnings:

    def warn(self: Union['ApiObject', 'Decoration', 'Argument',  'Docstring'], # type: ignore[misc]
             msg: str, lineno_offset: int = 0) -> None:
        # TODO: find another way to report warnings.
        lineno = 0
        filename = '<unknow>'
        if self.location:
            lineno = self.location.lineno + lineno_offset
            filename = self.location.filename or filename
        logging.getLogger('pydocspec').warning(f'{filename}:{lineno}: {msg}')

@attr.s
class TreeRoot:
    """
    A collection of related documentable objects, also known as "the system".
    
    This special object provides a single view on all referencable objects in the tree and root modules.

    :note: A reference to the root instance is kept on all API objects as `ApiObject.root`.
    """

    # :note: Do not intanciate a new `TreeRoot` manually with ``TreeRoot()``, first create a factory, in one line it gives::
    #     new_root = pydocspec.specfactory.Factory.default().TreeRoot()

    root_modules: List['Module'] = attr.ib(factory=list, init=False)
    """
    The root modules of the tree.
    """
    
    all_objects: DuplicateSafeDict[str, 'ApiObject'] = attr.ib(factory=DuplicateSafeDict, init=False)
    """
    All objects of the tree in a mapping ``full_name`` -> `ApiObject`.
    
    :note: Special care is taken in order no to shadow objects with duplicate names, see `DuplicateSafeDict`.
    """

    # This class variable is set from Factory itself.
    factory: ClassVar['specfactory.Factory'] = cast('specfactory.Factory', None)
    """
    The factory used to create this collection of objects.
    """

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
        if parent is not None:
            assert isinstance(parent, HasMembers), (f"Cannot add new object ({ob!r}) inside {parent.__class__.__name__}. "
                                                            f"{parent.full_name} is not namespace.")
            # setup child in the parent's member attribute
            if ob not in parent.members:
                parent.members.append(ob)
            ob.parent = parent
        else:
            assert isinstance(ob, Module)
            # add root modules to root.root_modules attribute
            self.root_modules.append(ob)
        
        # Add object to the root.all_objects. 
        obj_dup_name = parent.get_member(ob.name) if parent else None
        should_shadow = True
        if obj_dup_name not in (None, ob):
            # If the name is already defined, decide if the new object shoud shadow the existing
            # object by comparing line numbers, object defined after wins.
            should_shadow = obj_dup_name.location.lineno <= ob.location.lineno
        
        self.all_objects.addvalue(ob.full_name, ob, shadow=should_shadow)

        # Set the ApiObject.root attribute
        ob.root = self 
        
        # in case members are already present in the new object
        for child in ob._members():
            self.add_object(child, ob)

# must not use dataclasses
class ApiObject(docspec.ApiObject, CanTriggerWarnings):

    _spec_fields: Iterable[str] = (
        # defaults
        "name", "location", "docstring", 
        # added
        "source_path", ) # root is not an object field

    def __post_init__(self) -> None:
        super().__post_init__()
        
        # help mypy
        self.parent: Optional[Union['Class', 'Module']]
        self.location: Location

        # This attribute needs to be manually set after the init time of the object.
        self.root: TreeRoot = cast(TreeRoot, NotImplemented)
        """
        `TreeRoot` instance holding references to all objects in the tree.
        """

        self.source_path: Optional[Path] = None
    
    def remove(self) -> None:
        try:
            # remove from parent members
            if self.parent is not None:
                self.parent.members.remove(self)
            else:
                self.root.root_modules.remove(self)
        except ValueError:
            pass
        
        self._remove_self()    
    
    def _remove_self(self) -> None:
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
        obs = obs if isinstance(obs, list) else (obs,)
        for ob in obs:
            obj_dup_name = self.parent.get_member(ob.name)
            if obj_dup_name is None or allow_dup:
                self.root.add_object(ob, self.parent)

    def _members(self) -> Iterable['ApiObject']:
        if isinstance(self, HasMembers): 
            return self.members
        else: 
            return ()

    def walk(self, visitor: genericvisitor.Visitor['ApiObject']) -> None:
        """
        Traverse a tree of objects, calling the `genericvisitor.Visitor.visit` 
        method of `visitor` when entering each node.

        :see: `genericvisitor.walk` for more details.
        """
        genericvisitor.walk(self, visitor, ApiObject._members)
        
    def walkabout(self, visitor: genericvisitor.Visitor['ApiObject']) -> None:
        """
        Perform a tree traversal similarly to `walk()`, except also call the `genericvisitor.Visitor.depart` 
        method before exiting each node.

        :see: `genericvisitor.walkabout` for more details.
        """
        genericvisitor.walkabout(self, visitor, ApiObject._members)
    
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
    def module(self) -> 'Module':
        if isinstance(self, Module):
            return self
        else:
            assert self.parent is not None
            return self.parent.module
    
    @property
    def scope(self) -> Union['Module', 'Class']:
        if isinstance(self, (Module, Class)):
            return self
        else:
            assert self.parent is not None
            return self.parent.scope
    
    def get_member(self, name: str) -> Optional['ApiObject']:
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
    
    def get_members(self, name: str) -> Iterator['ApiObject']:
        """
        Like `get_member` but can return several items with the same name.
        """
        if isinstance(self, HasMembers):
            for member in self.members:
                if member.name == name:
                    assert isinstance(member, ApiObject), (name, self, member)
                    yield member

@dataclasses.dataclass
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
    
    datatype_ast: Optional[astroid.nodes.NodeNG] = None
    value_ast: Optional[astroid.nodes.NodeNG] = None
    is_type_guarged: bool = False
    # def __post_init__(self) -> None:
    #     super().__post_init__()
    #     # help mypy
    #     self.parent: Union['Class', 'Module']

@dataclasses.dataclass
class Indirection(docspec.Indirection, ApiObject):
    """
    Represents an imported name. It can be used to properly 
    find the full name target of a link written with a local name. 
    """

    _spec_fields = ("target", "is_type_guarged") + ApiObject._spec_fields

    is_type_guarged: bool = False

@dataclasses.dataclass
class Class(docspec.Class, ApiObject):
    """
    Represents a class definition.
    """
    
    bases_ast: Optional[List[astroid.nodes.NodeNG]] = None
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
        "_ast") + ApiObject._spec_fields

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore[assignment]
        self.parent: Union['Class', 'Module']
        self.members: List['ApiObject'] # the real type is Union['Data', 'Function', 'Class', 'Indirection']

@dataclasses.dataclass
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

    return_type_ast: Optional[astroid.nodes.NodeNG] = None
    is_type_guarged: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore
        self.args: List['Argument'] # type:ignore
        self.parent: Union[Class, 'Module']

@dataclasses.dataclass
class Argument(docspec.Argument, CanTriggerWarnings):
    """
    Represents a `Function` argument.
    """
    datatype_ast: Optional[astroid.nodes.NodeNG] = None
    default_value_ast: Optional[astroid.nodes.NodeNG] = None

@dataclasses.dataclass
class Decoration(docspec.Decoration, CanTriggerWarnings):
    """
    Represents a decorator on a `Class` or `Function`.

    +---------------------------------------+-------------------------+---------------------+-----------------+
    | Code                                  | Decorator.name          | Decorator.args      | Notes           |
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

    name_ast: Optional[astroid.nodes.NodeNG] = None
    """The name of the deocration as AST, this can be any kind of expression."""

    expr_ast: Optional[astroid.nodes.NodeNG] = None
    """The full decoration AST's"""    

@dataclasses.dataclass(init=False)
class Docstring(_DefaultDocstring, CanTriggerWarnings):
    ...

@dataclasses.dataclass
class Module(docspec.Module, ApiObject):
    """
    Represents a module, basically a named container for code/API objects. Modules may be nested in other modules.
    """

    _spec_fields = ("members",  "is_package") + ApiObject._spec_fields

    is_package: bool = False
    """
    Whether this module is a package.
    """

    dunder_all: Optional[List[str]] = None # Need to be present in the lower level model because it's used by the builder for processing wildcard imports statements.
    """The module variable __all__ as list of string."""

    _ast: Optional[astroid.nodes.Module] = None
    """
    The whole module's AST. 
    Can be used in post-processes to compute any kind of supplementary informaions not devirable from objects attributes.
    
    Only set when using our own builder. `None` if the module was converted from `docspec`.
    """

    def __post_init__(self) -> None:
        super().__post_init__()

        # help mypy
        self.parent: Optional['Module']
        self.members: List['ApiObject'] # type:ignore[assignment]

HasMembers = (Module, Class)
"""
Alias to use with `isinstance`()
"""

Inheritable = (Indirection, Data, Function) 
"""
Alias to use with `isinstance`()
"""
