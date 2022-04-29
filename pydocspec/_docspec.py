"""
Mirrors `docspec` model, but without using `dataclasses` (and without deprecated attributes).
"""
# -*- coding: utf8 -*-
# Copyright (c) 2021 Niklas Rosenstein
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

__author__ = 'Niklas Rosenstein <rosensteinniklas@gmail.com>'

__version__ = '2.0.1'
"""
The target docspec version: update me when syncing features from upstream.
"""

__all__ = [
  'Location',
  'Decoration',
  'Docstring',
  'Argument',
  'ApiObject',
  'Indirection',
  'HasMembers',
  'VariableSemantic',
  'Variable',
  'FunctionSemantic',
  'Function',
  'ClassSemantic',
  'Class',
  'Module',
]

import enum
import types
import typing as t

class _HasInitAttribsMethod:
  def _init_attribs(self) -> None:
    """
    A method to define extra attributes that will be set after initialization.
    
    :Note: Most attributes don't need a special value at initialization (if they use None as default for instance), 
      in those cases, avoid overriding this method by declaring them as class variable. 
      Override this method only if you have to initialize an attribute value to a mutable object.
    """

class Location(_HasInitAttribsMethod):
  """
  Represents the location of an #ApiObject by a filename and line number.
  """
  def __init__(self, filename:str, lineno:int, endlineno: t.Optional[int] = None) -> None:
    self.filename = filename

    # Since astroid lineno attribute is sometimes None and proper type checks cannot be perform, so we fall back to 0 here in case of none values.
    self.lineno = lineno or 0

    self.endlineno: t.Optional[int] = endlineno
    """
    If the location of an entity spans over multiple lines, it can be indicated by specifying at
    which line it ends with this property.
    """

    self._init_attribs()


class Docstring(_HasInitAttribsMethod):
  """
  Represents a docstring for an #APIObject, i.e. it's content and location. This class is a subclass of `str`
  for backwards compatibility reasons. Use the #content property to access the docstring content over the
  #Docstring value directory.
  """

  def __init__(self, location: Location, content: str) -> None:
      self.location: Location = location
      """
      The location of where the docstring is defined.
      """

      self.content = content
      """
      The content of the docstring. While the #Docstring class is a subclass of `str` and holds
      the same value as *content*, using the #content property should be preferred as the inheritance
      from the `str` class may be removed in future versions.
      """

      self._init_attribs()


class Decoration(_HasInitAttribsMethod):
  """
  Represents a decorator on a #Class or #Function.
  """

  def __init__(self, location: Location, name: str, arglist: t.Optional[t.List[str]] = None) -> None:
    self.location: Location = location
    """
    The location of the decoration in the source code."""

    self.name: str = name
    """
    The name of the decorator (i.e. the text between the `@` and `(`). In languages that support it,
    this may be a piece of code.
    """
  
    self.arglist: t.Optional[t.List[str]] = arglist
    """
    Decorator arguments, one item per argument. For keyword arguments, the keyword name and equals
    sign preceed the argument value expression code.
    """

    self._init_attribs()


class ArgumentType(enum.Enum):
    """
    The type of the argument. This is currently very Python-centric, however most other languages should be able
    to represent the various argument types with a subset of these types without additions (e.g. Java or TypeScript
    only support #Positional and #PositionalRemainder arguments).
    """

    POSITIONAL_ONLY = 0
    """
    A positional only argument. Such arguments are denoted in Python like this: `def foo(a, b, /): ...`
    """

    POSITIONAL = 1
    """
    A positional argument, which may also be given as a keyword argument. Basically that is just a normal
    argument as you would see most commonly in Python function definitions.
    """

    POSITIONAL_REMAINDER = 2
    """
    An argument that denotes the capture of additional positional arguments, aka. "args" or "varags".
    """

    KEYWORD_ONLY = 3
    """
    A keyword-only argument is denoted in Python like thisL `def foo(*, kwonly): ...`
    """

    KEYWORD_REMAINDER = 4
    """
    An argument that captures additional keyword arguments, aka. "kwargs".
    """


class Argument(_HasInitAttribsMethod):
  """
  Represents a #Function argument.
  """

  Type: t.ClassVar = ArgumentType
  
  def __init__(self, location: Location, name: str, type: ArgumentType, 
               decorations: t.Optional[t.List[Decoration]] = None,
               datatype: t.Optional[str] = None,
               default_value: t.Optional[str] = None) -> None:

      self.location: Location = location
      """
      The location of the argument in the source code.
      """

      self.name: str = name
      """
      The name of the argument.
      """

      self.type: ArgumentType = type
      """
      The argument type.
      """

      self.decorations: t.Optional[t.List[Decoration]] = decorations
      """
      A list of argument decorations. Python does not actually support decorators on function arguments
      like for example Java does. This is probably premature to add into the API, but hey, here it is.
      """

      self.datatype: t.Optional[str] = datatype
      """
      The datatype/type annotation of this argument as a code string.
      """

      self.default_value: t.Optional[str] = default_value
      """
      The default value of the argument as a code string.
      """

      self._init_attribs()


class ApiObject(_HasInitAttribsMethod):
  """
  The base class for representing "API Objects". Any API object is any addressable entity in code,
  be that a variable/constant, function, class or module.
  """

  def __init__(self, location: Location, 
               name: str, 
               docstring: t.Optional[Docstring], 
              #  parent: t.Optional['HasMembers'],
               ) -> None:

      self.location: Location = location
      """
      The location of the API object, i.e. where it is sourced from/defined in the code.
      """

      self.name: str = name
      """
      The name of the entity. This is usually relative to the respective parent of the entity,
      as opposed to it's fully qualified name/absolute name. However, that is more of a
      recommendation than rule. For example the #docspec_python loader by default returns
      #Module objects with their full module name (and does not create a module hierarchy).
      """

      self.docstring: t.Optional[Docstring] = docstring
      """
      The documentation string of the API object.
      """
      
      self.parent: t.Optional['HasMembers'] = None
      """
      The parent of the API object.
      """

      self._init_attribs()

  @property
  def path(self) -> t.List['ApiObject']:
    """
    Returns a list of all of this API object's parents, from top to bottom. The list includes *self* as the
    last item.
    """

    result = []
    current: t.Optional[ApiObject] = self
    while current:
      result.append(current)
      current = current.parent
    result.reverse()
    return result

  def sync_hierarchy(self, parent: t.Optional['HasMembers'] = None) -> None:
    """
    Synchronize the hierarchy of this API object and all of it's children. This should be called when the
    #HasMembers.members are updated to ensure that all child objects reference the right #parent. Loaders
    are expected to return #ApiObject#s in a fully synchronized state such that the user does not have to
    call this method unless they are doing modifications to the tree.
    """

    self.parent = parent


class Inheritable(ApiObject):
    """
    Base class for inheritable objects.
    """


class VariableSemantic(enum.Enum):
  """
  A list of well-known properties and behaviour that can be attributed to a variable/constant.
  """

  INSTANCE_VARIABLE = 0
  """
  The #Variable object is an instance variable of a class.
  """

  CLASS_VARIABLE = 1
  """
  The #Variable object is a static variable of a class.
  """

  CONSTANT = 2
  """
  The #Variable object represents a constant value.
  """


class Variable(Inheritable):
  """
  Represents a variable assignment (e.g. for global variables (often used as constants) or class members).
  """

  Semantic: t.ClassVar = VariableSemantic

  def __init__(self, *args: t.Any,
               datatype: t.Optional[str], 
               value: t.Optional[str], 
               modifiers: t.Optional[t.List[str]] = None, 
               semantic_hints: t.Optional[t.List[VariableSemantic]] = None,
               **kwargs: t.Any
               ) -> None:
      super().__init__(*args, **kwargs)

      self.datatype: t.Optional[str] = datatype
      """
      The datatype associated with the assignment as code.
      """
      
      self.value: t.Optional[str] = value
      """
      The value of the variable as code.
      """

      self.modifiers: t.List[str] = modifiers or []
      """
      A list of language-specific modifiers that were used to declare this #Variable object.
      """

      self.semantic_hints: t.List[VariableSemantic] = semantic_hints or []
      """
      A list of hints that express semantics of this #Variable object which are not otherwise
      derivable from the context.
      """


class Indirection(Inheritable):
  """
  Represents an imported name. It can be used to properly find the full name target of a link written with a
  local name.
  """

  def __init__(self, *args: t.Any, target: str, **kwargs: t.Any) -> None:
      super().__init__(*args, **kwargs)
      self.target: str = target


class FunctionSemantic(enum.Enum):
  """
  A list of well-known properties and behaviour that can be attributed to a function.
  """

  ABSTRACT = 0
  """
  The function is abstract.
  """
  
  FINAL = 1
  """
  The function is final.
  """

  COROUTINE = 2
  """
  The function is a coroutine.
  """

  NO_RETURN = 3
  """
  The function does not return.
  """

  INSTANCE_METHOD = 4
  """
  The function is an instance method.
  """

  CLASS_METHOD = 5
  """
  The function is a classmethod.
  """

  STATIC_METHOD = 6
  """
  The function is a staticmethod.
  """

  PROPERTY_GETTER = 7
  """
  The function is a property getter.
  """

  PROPERTY_SETTER = 8
  """
  The function is a property setter.
  """

  PROPERTY_DELETER = 9
  """  
  The function is a property deleter.
  """


class Function(Inheritable):
  """
  Represents a function definition. This can be in a #Module for plain functions or in a #Class for methods.
  The #decorations need to be introspected to understand if the function has a special purpose (e.g. is it a
  `@property`, `@classmethod` or `@staticmethod`?).
  """

  Semantic: t.ClassVar = FunctionSemantic

  def __init__(self,
               *_args:t.Any,
               modifiers: t.Optional[t.List[str]], 
               args: t.List[Argument], 
               return_type: t.Optional[str], 
               decorations: t.Optional[t.List[Decoration]],
               semantic_hints: t.Optional[t.List[FunctionSemantic]] = None,
               **kwargs:t.Any
               ) -> None:
      super().__init__(*_args, **kwargs)

      self. modifiers: t.Optional[t.List[str]] = modifiers
      """
      A list of modifiers used in the function definition. For example, the only valid modifier in Python is "async".
      """

      self.args: t.List[Argument] = args
      """
      A list of the function arguments.
      """

      self.return_type: t.Optional[str] = return_type
      """
      The return type of the function as a code string.
      """

      self.decorations: t.Optional[t.List[Decoration]] = decorations
      """
      A list of decorations used on the function.
      """

      self.semantic_hints: t.List[FunctionSemantic] = semantic_hints or []
      """
      A list of hints that describe the object.
      """


class HasMembers(ApiObject):
  """
  Base class for API objects that can have members, e.g. #Class and #Module.
  """

  def __init__(self, *args:t.Any, 
               members: t.List['ApiObject'],
               **kwargs:t.Any) -> None:
      super().__init__(*args, **kwargs)
      self.members: t.List['ApiObject'] = members
      """
      The members of the API object.
      """

  def sync_hierarchy(self, parent: t.Optional['HasMembers'] = None) -> None:
    self.parent = parent
    for member in self.members:
      member.sync_hierarchy(self)


class ClassSemantic(enum.Enum):
  """
  A list of well-known properties and behaviour that can be attributed to a class.
  """

  INTERFACE = 0
  """
  The class describes an interface.
  """

  ABSTRACT = 1
  """
  The class is abstract.
  """

  FINAL = 2
  """
  The class is final.
  """

  ENUM = 3
  """
  The class is an enumeration.
  """


class Class(HasMembers):
  """
  Represents a class definition.
  """

  Semantic: t.ClassVar = ClassSemantic

  def __init__(self, *args: t.Any,
               metaclass: t.Optional[str], 
               bases: t.Optional[t.List[str]], 
               decorations: t.Optional[t.List[Decoration]], 
               modifiers: t.Optional[t.List[str]] = None,
               semantic_hints: t.Optional[t.List[ClassSemantic]] = None,
               **kwargs:t.Any
               ) -> None:
      super().__init__(*args, **kwargs)

      self.metaclass: t.Optional[str] = metaclass
      """
      The metaclass used in the class definition as a code string.
      """

      self.bases: t.Optional[t.List[str]] = bases
      """
      The list of base classes as code strings.
      """

      self.decorations: t.Optional[t.List[Decoration]] = decorations
      """
      A list of decorations used in the class definition.
      """

      self.modifiers: t.List[str] = modifiers or []
      """
      A list of language-specific modifiers that were used to declare this #Variable object.
      """

      self.semantic_hints: t.List[ClassSemantic] = semantic_hints or []
      """
      A list of hints that describe the object.
      """


class Module(HasMembers):
  """
  Represents a module, basically a named container for code/API objects. Modules may be nested in other modules.
  Be aware that for historical reasons, some loaders lile #docspec_python by default do not return nested modules,
  even if nesting would be appropriate (and instead the #Module.name simply contains the fully qualified name).
  """

if t.TYPE_CHECKING:
  import docspec
  docspecApiObjectT = t.TypeVar('docspecApiObjectT', ApiObject, docspec.ApiObject)
else:
  docspecApiObjectT = object

# Set upstream modules shortcut
class upstream:
  """
  :ivar docspec: The docspec module if it's installed, None otherwise.
  :ivar docspec_python: The docspec_python module if it's installed, None otherwise.
  """
  
  try:
    import docspec
  except ImportError:
    docspec = None
  
  try:
    import docspec_python
  except ImportError:
    docspec_python = None
