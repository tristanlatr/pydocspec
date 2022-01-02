"""
Just like the `docspec` classes, but with ast attributes and few goodies added such that efficient 
processing can be done on these objects afterwards.
"""

from typing import List, Optional, Union, Iterable, ClassVar, cast, TYPE_CHECKING
import ast
import warnings
import dataclasses
import attr

import docspec

from . import genericvisitor
from .dupsafedict import DuplicateSafeDict


if TYPE_CHECKING:
    from . import specfactory

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
]

class _sentinel(ast.expr):
    ...

# This classes are customizable brain modules, even if they are not customized here.
Location = docspec.Location

class Warning(RuntimeWarning):
    """Warning class used for pydocspec related warnings."""

class CanTriggerWarnings:
    def warn(self: Union['ApiObject', 'Decoration', 'Argument',  'Docstring'], 
             msg: str, lineno_offset: int = 0) -> None:
        # TODO: find another way to report warnings.
        lineno = self.location.lineno + lineno_offset
        warnings.warn(f'{self.location.filename}:{lineno}: {msg}', category=Warning)

@attr.s
class ApiObjectsRoot:
    """
    A collection of related documentable objects, also known as "the system".
    
    This special object provides a single view on all referencable objects in the tree and root modules.

    :note: A reference to the root instance is kept on all API objects as `ApiObject.root`.
    """

    root_modules: List['Module'] = attr.ib(factory=list, init=False)
    """
    The root modules of the tree.
    """
    
    all_objects: DuplicateSafeDict['ApiObject'] = attr.ib(factory=DuplicateSafeDict, init=False)
    """
    All objects of the tree in a mapping ``full_name`` -> `ApiObject`.
    
    :note: Special care is taken in order no to shadow objects with duplicate names, see `DuplicateSafeDict`.
    """

    # This class variable is set from Factory itself.
    factory: ClassVar['specfactory.Factory'] = cast('specfactory.Factory', None)
    """
    The factory used to create this collection of objects. `None` if the root has been created manually. 
    """

class ApiObject(docspec.ApiObject, CanTriggerWarnings):

    # This attribute needs to be manually set after the init time of the object.
    root: ApiObjectsRoot
    """
    `ApiObjectsRoot` instance holding references to all objects in the tree.
    """

    def _members(self) -> Iterable['ApiObject']:
        if isinstance(self, docspec.HasMembers): 
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

@dataclasses.dataclass
class Data(docspec.Data, ApiObject):
    """
    Represents a variable assignment.
    """
    datatype_ast: Optional[ast.expr] = None
    value_ast: Optional[ast.expr] = None

    # def __post_init__(self) -> None:
    #     docspec.Data.__post_init__(self)

    #     # help mypy
    #     self.parent: Union['Class', 'Module']

@dataclasses.dataclass
class Indirection(docspec.Indirection, ApiObject):
    """
    Represents an imported name. It can be used to properly 
    find the full name target of a link written with a local name. 
    """

@dataclasses.dataclass
class Class(docspec.Class, ApiObject):
    """
    Represents a class definition.
    """

    # def __post_init__(self) -> None:
    #     docspec.Class.__post_init__(self)

    #     # help mypy
    #     self.decorations: Optional[List['Decoration']] # type:ignore[assignment]
    #     self.parent: Union['Class', 'Module']
    #     self.members: List['ApiObject'] # type:ignore[assignment]
    
    bases_ast: Optional[List[ast.expr]] = None

@dataclasses.dataclass
class Function(docspec.Function, ApiObject):
    """
    Represents a function definition.
    """
    # def __post_init__(self) -> None:
    #     docspec.Function.__post_init__(self)

    #     # help mypy
    #     self.decorations: Optional[List['Decoration']] # type:ignore
    #     self.args: List['Argument'] # type:ignore
    #     self.parent: Union[Class, 'Module']

    return_type_ast: Optional[ast.expr] = None

@dataclasses.dataclass
class Argument(docspec.Argument, CanTriggerWarnings):
    """
    Represents a `Function` argument.
    """
    datatype_ast: Optional[ast.expr] = None
    default_value_ast: Optional[ast.expr] = None

@dataclasses.dataclass
class Decoration(docspec.Decoration, CanTriggerWarnings):

    name_ast: ast.expr = dataclasses.field(default_factory=_sentinel)
    """The name of the deocration as AST, this can be any kind of expression."""
    
    args_ast: Optional[List[ast.expr]] = None
    """The arguments of the deocration AST, if the decoration was called like a function."""

    expr_ast: ast.expr = dataclasses.field(default_factory=_sentinel)
    """The full decoration AST's"""    

@dataclasses.dataclass
class Docstring(docspec.Docstring, CanTriggerWarnings):
    ...

@dataclasses.dataclass
class Module(docspec.Module, ApiObject):
    """
    Represents a module, basically a named container for code/API objects. Modules may be nested in other modules
    """
    
    mod_ast: Optional[ast.Module] = None
    """
    The whole module's AST. 
    Can be used in post-processes to compute any kind of supplementary informaions not devirable from objects attributes.
    
    Only set when using our own loader. `None` if the module was converted from `docspec`.
    """

    # def __post_init__(self) -> None:
    #     docspec.Module.__post_init__(self)

    #     # help mypy
    #     self.members: List['ApiObject'] # type:ignore[assignment]

# HasMembers = (Module, Class)
# """
# Alias to use with `isinstance`()
# """

# Inheritable = (Indirection, Data, Function) 
# """
# Alias to use with `isinstance`()
# """
