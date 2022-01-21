"""
General purpose visitor pattern implementation, with extensions.
"""
from collections import defaultdict
import enum
import abc
from typing import Generic, Iterable, Optional, TypeVar

T = TypeVar("T")

class Visitor(Generic[T], abc.ABC):
  """
  "Visitor" pattern abstract superclass implementation for tree traversals.

  Each class has corresponding methods, doing nothing by
  default; override individual methods for specific and useful
  behaviour.  The `visit()` method is called by
  `walk()` upon entering a object.  `walkabout()` also calls
  the `depart()` method before exiting a object.

  The generic methods call "``visit_`` + objet class name" or
  "``depart_`` + objet class name", resp.

  This is a base class for visitors whose ``visit_...`` & ``depart_...``
  methods should be implemented for *all* concrete objets types encountered. 
  """

  def visit(self, ob: T) -> None:
    """Visit an object."""
    method = 'visit_' + ob.__class__.__name__
    visitor = getattr(self, method, getattr(self, method.lower(), self.unknown_visit))
    visitor(ob)
  
  def depart(self, ob: T) -> None:
    """Depart an object."""
    method = 'depart_' + ob.__class__.__name__
    visitor = getattr(self, method, getattr(self, method.lower(), self.unknown_departure))
    visitor(ob)
  
  def unknown_visit(self, ob: T) -> None:
    """
    Called when entering unknown object types.

    Raise an exception unless overridden.
    """
    raise NotImplementedError(
        '%s visiting unknown object type: %s'
        % (self.__class__, ob.__class__.__name__))

  def unknown_departure(self, ob: T) -> None:
    """
    Called before exiting unknown object types.

    Raise exception unless overridden.
    """
    raise NotImplementedError(
        '%s departing unknown object type: %s'
        % (self.__class__, ob.__class__.__name__))
  
  def walk(self, ob: T) -> None:
    """
    Traverse a tree of objects, calling the
    `visit()` method of `visitor` when entering each
    node.  (The `walkabout()` method is similar, except it also
    calls the `depart()` method before exiting each objects.)

    This tree traversal supports limited in-place tree
    modifications.  Replacing one node with one or more nodes is
    OK, as is removing an element.  However, if the node removed
    or replaced occurs after the current node, the old node will
    still be traversed, and any new nodes will not.

    :param ob: An object to walk.
    :param visitor: A `Visitor` object, containing a
        ``visit`` implementation for each object type encountered.
    :param get_children: A callable that returns the children of an object. 
    """
    self.visit(ob)
    for child in self.get_children(ob):
        self.walk(child)
    
  def walkabout(self, ob: T) -> None:
    """
    Perform a tree traversal similarly to `walk()` (which
    see), except also call the `depart()` method before exiting each node.

    :param ob: An object to walk.
    :param visitor: A `Visitor` object, containing a
        ``visit`` and ``depart`` implementation for each concrete object type encountered.
    :param get_children: A callable that returns the children of an object. 
    """
    self.visit(ob)
    for child in self.get_children(ob):
        self.walkabout(child)
    self.depart(ob)
  
  @abc.abstractclassmethod
  def get_children(cls, ob: T) -> Iterable[T]:
    raise NotImplementedError()

# Adapted from https://github.com/pawamoy/griffe
# Copyright (c) 2021, Timothée Mazzucotelli

class PartialVisitor(Visitor[T]):
  """
  Visitor class that do not have to define all possible visit_.* methods since it overrides
  the default behaviour of unknown_visit() and unknown_departure() not to raise NotImplementedError.
  """
  def unknown_visit(self, ob: T) -> None:
    pass
  def unknown_departure(self, ob: T) -> None:
    pass    

class When(enum.Enum):
    """This enumeration contains the different times an extension is used.

    Attributes:
        BEFORE: For each node, before calling the visit() method on the customizable visitor.
          ..note:: The depart() method will be called AFTER calling depart() on 
            the customizable visitor. Outer scope.
        AFTER: For each node, before calling the visit(), and before the children gets visited.
          ..note:: The depart() method will be called  after the children have been visited, 
            and BEFORE calling depart() on the customizable visitor. Inner scope. 
    
    Example:
      Considering that the customizable visitor `MainVisitor` is set up with two extension visitors: 
      one that runs `BEFORE` and one that runs `AFTER`, all 3 visitors simply print the name of 
      the visitor class and the call beeing made.

      Running the `MainVisitor` on the following tree::

        :0 - Module: a
        | :1 - Indirection: Union
      
      Will generate the following output::

        Before              .visit(a)
        MainVistor          .visit(a)
        After               .visit(a)
        Before              .visit(a.Union)
        MainVistor          .visit(a.Union)
        After               .visit(a.Union)
        After               .depart(a.Union)
        MainVistor          .depart(a.Union)
        Before              .depart(a.Union)
        After               .depart(a)
        MainVistor          .depart(a)
        Before              .depart(a)
    """

    BEFORE = enum.auto()
    AFTER = enum.auto()

class VisitorExtensionList(Generic[T]):
    """
    This class helps iterating on visitor extensions that should run at different times.
    """

    def __init__(self, *extensions: 'VisitorExtension[T]') -> None:
        """Initialize the extensions container.

        Parameters:
            *extensions: The extensions to add.
        """
        self._visitors: dict[When, list['VisitorExtension[T]']] = defaultdict(list)
        self.add(*extensions)

    def add(self, *extensions: 'VisitorExtension[T]') -> None:
        """Add extensions to this container.

        Parameters:
            *extensions: The extensions to add.
        """
        for extension in extensions:
            if isinstance(extension, VisitorExtension):
                if extension.when == NotImplemented:
                  raise AttributeError(f'class variable "when" must be set on visitor extension {type(extension)}')
                self._visitors[extension.when].append(extension)

    def attach_visitor(self, parent_visitor: 'CustomizableVisitor[T]') -> None:
        """Attach a parent visitor to the visitor extensions.

        Parameters:
            parent_visitor: The parent visitor, leading the visit.
        """
        for when in self._visitors.keys():
            for visitor in self._visitors[when]:
                visitor.attach(parent_visitor)

    @property
    def before_visit(self) -> list['VisitorExtension[T]']:
        """Return the visitors that run before the visit.

        Returns:
            Visitors.

        See: `When` 
        """
        return self._visitors[When.BEFORE]

    @property
    def after_visit(self) -> list['VisitorExtension[T]']:
        """Return the visitors that run after the visit.

        Returns:
            Visitors.
        
        See: `When` 
        """
        return self._visitors[When.AFTER]
   
class VisitorExtension(PartialVisitor[T]):
    """
    The node visitor extension base class, to inherit from.

    Subclasses must defined the `when` class variable, and your custom visit_* methods.::

      class TypeGuardTracker(AstVisitorExtension):
        when = When.AFTER
        def visit_If(self: 'Collector', node: astroid.nodes.If) -> None:
          if not self.state.is_type_guarged and astroidutils.is_type_guard(node):
              self.state.is_type_guarged = True
              logging.getLogger('pydocspec').info('Entering TYPE_CHECKING if block')
          
        def depart_If(self: 'Collector', node: astroid.nodes.If) -> None:
          if self.state.is_type_guarged and astroidutils.is_type_guard(node):
              logging.getLogger('pydocspec').info('Leaving TYPE_CHECKING if block')
              self.state.is_type_guarged = False
    
    See: `When` 
    """

    when: When = NotImplemented

    def __init__(self) -> None:
        """Initialize the visitor extension."""
        super().__init__()
        self.visitor: Visitor[T] = None  # type: ignore[assignment]
        """The parent visitor"""

    def walk(self, ob: T) -> None:
        raise NotImplementedError("Not supposed to walk the tree from a visitor extension")
    
    def walkabout(self, ob: T) -> None:
        raise NotImplementedError("Not supposed to walk the tree from a visitor extension")

    def attach(self, visitor: Visitor[T]) -> None:
        """Attach the parent visitor to this extension.

        Parameters:
            visitor: The parent visitor.
        """
        self.visitor = visitor
    
class CustomizableVisitor(Visitor[T]):
  """
  A visitor that can be composed by other vistitors.

  Subclasses must implement:
  - get_children()
  - all the required visit_*() methods
  - at least unknown_departure() such that it does not raise NotImplementedError
  """
  def __init__(self, extensions: Optional[VisitorExtensionList[T]]=None) -> None:
    self.extensions: 'VisitorExtensionList[T]' = extensions or VisitorExtensionList()
    self.extensions.attach_visitor(self)
    
  def visit(self, ob: T) -> None:
    """Extend the base visit with extensions.

    Parameters:
        node: The node to visit.
    """
    for v in self.extensions.before_visit:
      v.visit(ob)

    super().visit(ob)

    for v in self.extensions.after_visit:
      v.visit(ob)
  
  def depart(self, ob: T) -> None:
    
    for v in self.extensions.after_visit:
      v.depart(ob)

    super().depart(ob)

    for v in self.extensions.before_visit:
      v.depart(ob)
    