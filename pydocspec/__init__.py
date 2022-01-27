"""
Pyocspec is a object specification for representing and loading API documentation 
of a collection of related python modules. It extends docspec for the python language, 
offers facility to resolve names and provides additional informations.

**Warning**:

Work in progress... API might change without deprecation notice.

**Usage**:

>>> import pydocspec
>>> root = pydocspec.load_python_modules([Path('./pydocspec')])

**How it works**

First, a root object gets created with the `specfactory`, then the `astbuilder` creates all the other objects
and populate the strict-minimum attributes. Then the `processor` takes that tree and populated all other attributes.

**Extensibility**:

The core of the logic is design to be extensible with plugins modules, called "brain" modules. One can define custom
mixin classes and post-processes in a new module, add the special ``pydocspec_mixin`` and/or ``pydocspec_processes`` module 
variables, then include the module's full name as part of the ``additional_brain_modules`` argument of function `converter.convert_docspec_modules`. 

Mixin classes are going to be added to the list of bases when creating the new objects with the 
`specfactory.Factory`. Because of that, the documentation of the classes listed in this module are incomplete, properties
and methods provided by mixin classes can be review in their respective documentation, under the package `brains`.
"""

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, List, Optional, Sequence, TextIO, Tuple, Union, Type, Any, cast

import inspect

import attr
import docspec
import os.path
import sys
import logging

from . import astroidutils, dupsafedict
from .dottedname import DottedName
from . import _model
from ._model import Inheritable, HasMembers

# should not import ast or astroid

if TYPE_CHECKING:
    import docspec_python
    from . import astbuilder, processor

__docformat__ = 'restructuredtext'
__all__ = [
  'TreeRoot',
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

_RESOLVE_ALIAS_MAX_RECURSE = 10

Location = _model.Location
Docstring = _model.Docstring
Argument = _model.Argument
Decoration = _model.Decoration

class TreeRoot(_model.TreeRoot):
    # see _model.TreeRoot for docs.

    # help mypy
    root_modules: List['Module'] # type: ignore[assignment]
    all_objects: dupsafedict.DuplicateSafeDict[str, 'ApiObject'] # type: ignore[assignment]

class ApiObject(_model.ApiObject):
    """
    An augmented `docspec.ApiObject`, with functionalities to resolve names for the python language.
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        
        # help mypy
        self.root: TreeRoot
        self.parent: Optional[Union['Class', 'Module']]
        self.location: Location
        self.module: 'Module'

        # new attributes

        self.doc_sources: List['ApiObject'] = []
        """Objects that can be considered as a source of documentation.

        The motivating example for having multiple sources is looking at a
        superclass' implementation of a method for documentation for a
        subclass'.
        """

        self.aliases: List['Data'] = []
        """
        Aliases to this object.
        """

    # NAME RESOLVING LOGIC

    def expand_name(self, name: str, follow_aliases: bool = True, _indirections: Any=None) -> str:
        """
        Return a fully qualified name for the possibly-dotted `name`.

        To explain what this means, consider the following modules:
        mod1.py::
            from external_location import External
            class Local:
                pass
        mod2.py::
            from mod1 import External as RenamedExternal
            import mod1 as renamed_mod
            class E:
                pass
        In the context of mod2.E, ``expand_name("RenamedExternal")`` should be
        ``"external_location.External"`` and ``expand_name("renamed_mod.Local")``
        should be ``"mod1.Local"``. 
        
        This method is in charge to follow the aliases when possible!
        It will reccursively follow any alias entries found 
        up to certain level of complexity. 
        Example:
        mod1.py::
            
            import external
            class Processor:
                spec = external.Processor.more_spec
            P = Processor

        mod2.py::

            from mod1 import P
            class Runner:
                processor = P

        In the context of mod2, ``expand_name("Runner.processor.spec")`` should be
        ``"external.Processor.more_spec"``.
        
        :param name: The name to expand.
        :param follow_aliases: Whether or not to follow aliases. Indirections will still be followed anyway.
        :note: The implementation replies on iterating through the each part of the dotted name, 
            calling `_local_to_full_name` for each name in their associated context and incrementally building 
            the full_name from that. 
            Lookup members in superclasses when possible and follows aliases and indirections. 
            This mean that `expand_name` will never return the name of an alias,
            it will always follow it's indirection to the origin. Except if ``follow_aliases=False``. 
        :note: Supports relative dotted name like ``.foo.bar``.
        """
        parts = DottedName(name)
        ctx: 'ApiObject' = self # The context for the currently processed part of the name. 
        
        for i, part in enumerate(parts):
            if not part and i==0 and ctx.module.parent is not None: # we got a relative dotted name
                part = ctx.module.parent.name
            full_name = ctx._local_to_full_name(part, follow_aliases=follow_aliases, _indirections=_indirections)
            if full_name == part and i != 0:
                # The local name was not found.
                # If we're looking at a class, we try our luck with the inherited members
                if isinstance(ctx, Class):
                    inherited = ctx.find(part)
                    if inherited:
                        assert inherited.parent is not None
                        full_name = inherited.parent._local_to_full_name(inherited.name, follow_aliases=follow_aliases, 
                                                                 _indirections=_indirections)
                # We don't have a full name
                if full_name == part:
                    # TODO: Instead of returning the input, _local_to_full_name
                    #       should probably either return None or raise LookupError.
                    # Or maybe we should find a way to indicate if the expanded name is "guessed" or if we have the the correct full_name. 
                    # With the current implementation, this would mean checking if "parts[i + 1:]" contains anything. 
                    full_name = f'{ctx.full_name}.{part}'
                    break
            nxt = self.root.all_objects.get(full_name)
            if nxt is None:
                break
            ctx = nxt

        return str(DottedName(full_name, *parts[i + 1:]))

    def resolve_name(self, name: str, follow_aliases: bool = True) -> Optional['ApiObject']:
        """
        Return the object named by "name" (using Python's lookup rules) in this context.

        :note: This method will never return an `Indirection` or an alias since it's supposed to follow 
            indirections and aliases. Except if ``follow_aliases=False``. 
        """
        return self.root.all_objects.get(self.expand_name(name, follow_aliases=follow_aliases))

    def _local_to_full_name(self, name: str, follow_aliases: bool, _indirections:Any=None) -> str:
        if not isinstance(self, HasMembers): # type:ignore[unreachable]
            assert self.parent is not None
            return self.parent._local_to_full_name(name, follow_aliases, _indirections)
        
        # Follows indirections and aliases
        member = self.get_member(name) # type:ignore[unreachable]
        if member:
            if follow_aliases and isinstance(member, Data) and astroidutils.is_name(member.value_ast):
                indirection = member._alias_indirection
                return self._resolve_indirection(indirection, _indirections) or indirection.target
            if isinstance(member, Indirection):
                return self._resolve_indirection(member, _indirections) or member.target
            return member.full_name

        elif isinstance(self, Class):
            assert self.parent is not None
            return self.parent._local_to_full_name(name, follow_aliases, _indirections)
        
        return name
    
    def _resolve_indirection(self, indirection: 'Indirection', _indirections: Optional[List['Indirection']]=None) -> Optional[str]:
        """
        Follow an indirection and return the *supposed* full name of the origin object.

        Resolve the alias value to it's target full name.
        Or fall back to original alias target if we know we've exhausted the max recursions.

        :param indirection: an `Indirection` object.
        :param indirections: Chain of alias objects followed. 
            This variable is used to prevent infinite loops when doing the lookup.
        :note: It can return None in exceptionnal cases if an indirection cannot be resolved. 
            Then we use the indirection's full_name. 
        """

        if _indirections and len(_indirections) > _RESOLVE_ALIAS_MAX_RECURSE:
            _indirections[0].warn(f"Could not resolve indirection to {_indirections[0].target!r}, reach max recursions.")
            return _indirections[0].full_name

        target = indirection.target
        
        # the context is important
        ctx = indirection.parent
        assert ctx is not None

        # This checks avoids infinite recursion error when a indirection's has the same name as it's value
        if (_indirections and indirection not in _indirections) or not _indirections:
            # We redirect to the original object instead!
            return ctx.expand_name(target, _indirections=(_indirections or [])+[indirection])
        else: 
            # Issue tracing the alias back to it's original location, found the same indirection again.
            # Meaning: indirection is in _indirections
            if ctx.parent is not None and ctx.module == ctx.parent.module:
                # We try with the parent scope, only if the parent is in the same module, otherwise fail. 
                # This is used in situations like in the pydoctor.model.System class and it's aliases, 
                # because they have the same target name as the name they are aliasing, it's causing trouble.
                return ctx.parent.expand_name(target, _indirections=(_indirections or [])+[indirection])
        
        indirection.warn(f"Could not resolve indirection to {_indirections[0].target!r}.")
        return None
    
@dataclasses.dataclass(repr=False)
class Data(_model.Data, ApiObject):
    """
    Represents a variable assignment.
    """

    is_instance_variable: bool = False
    """
    Whether this Data is an instance variable.
    """

    is_class_variable: bool = False
    """
    Whether this Data is a class variable.
    """

    is_module_variable: bool = False
    """
    Whether this Data is a module variable.
    """

    is_alias: bool = False
    """
    Whether this Data is an alias.
    Aliases are folowed by default when using `ApiObject.expand_name`. 
    """

    is_constant: bool = False
    """
    Whether this Data is a constant.
    """

    @property
    def _alias_indirection(self) -> 'Indirection':
        # private helper object to resolve names only.
        assert self.value is not None
        indirection = Indirection(self.name, self.location, None, self.value)
        indirection.parent = self.parent
        indirection.root = self.root
        return indirection

    def __post_init__(self) -> None:
        super().__post_init__()
        
        # help mypy
        self.parent: Union['Class', 'Module']

    
    # @cached_property
    

    # TODO: Add type/docstring extraction from marshmallow attributes
    # https://github.com/mkdocstrings/mkdocstrings/issues/130

    # TODO: Always consider Enum values as constants. Maybe having a Class.is_enum property, similar to is_exception?

@dataclasses.dataclass(repr=False)
class Indirection(_model.Indirection, ApiObject):
  """
  Represents an imported name. It can be used to properly 
  find the full name target of a link written with a local name. 
  """
#   resolved_target: Optional[ApiObject] = None

  def __post_init__(self) -> None:
        super().__post_init__()
        
        # help mypy
        self.parent: Union['Class', 'Module']

@dataclasses.dataclass(repr=False)
class Class(_model.Class, ApiObject):
    """
    Represents a class definition.
    """
    # TODO: create property inherited_members

    is_exception: bool = False
    """Whether this class extends one of the standard library exceptions."""

    resolved_bases: List[Union['Class', 'str']] = dataclasses.field(default_factory=list)
    """
    For each bases, try to resolve the name to an `ApiObject` or fallback to the expanded name.
    
    :see: `resolve_name` and `expand_name`
    """

    mro: List['Class'] = dataclasses.field(default_factory=list)
    """
    The method resoltion order of this class.
    """

    subclasses: List['Class'] = dataclasses.field(default_factory=list)
    """
    The direct subclasses of this class. 
    """

    constructor_method: Optional['Function'] = None
    """
    The constructor method of this class.
    """

    inherited_members: List['InheritedMember'] = dataclasses.field(default_factory=list)
    """
    Members inherited from superclasses.
    """

    @dataclasses.dataclass(repr=False)
    class InheritedMember:
        member: ApiObject
        inherited_via: Tuple[ApiObject]
        
    def __post_init__(self) -> None:
        super().__post_init__()
        
        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore[assignment]
        self.parent: Union['Class', 'Module']
        self.members: List['ApiObject'] # type:ignore[assignment]
    
    def ancestors(self, include_self: bool = False) -> Iterator[Union['Class', 'str']]:
        """Reccursively returns `resolved_bases` for all bases."""
        if include_self:
            yield self
        for b in self.resolved_bases:
            if isinstance(b, Class):
                yield from b.ancestors(True)
            else:
                yield b
    
    def find(self, name: str) -> Optional[ApiObject]:
        """
        Look up a name in this class and its base classes. 

        :return: The object with the given name, or `None` if there isn't one.
        """
        for base in self.mro:
            obj: Optional['ApiObject'] = base.get_member(name)
            if obj is not None:
                return obj
        return None

@dataclasses.dataclass(repr=False)
class Function(_model.Function, ApiObject):
    """
    Represents a function definition.
    """

    is_property: bool = False
    is_property_setter: bool = False
    is_property_deleter: bool = False
    is_async: bool = False
    is_method: bool = False
    is_staticmethod: bool = False
    is_classmethod: bool = False
    is_abstractmethod: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        # help mypy
        self.decorations: Optional[List['Decoration']] # type:ignore
        self.args: List['Argument'] # type:ignore
        self.parent: Union[Class, 'Module']

    def signature(self, include_types:bool=True, include_defaults:bool=True, 
                  include_return_type:bool=True, include_self:bool=True,
                  signature_class: Type[inspect.Signature] = inspect.Signature, 
                  value_formatter_class: Type[astroidutils.ValueFormatter] = astroidutils.ValueFormatter) -> inspect.Signature:
        """
        Get the function's signature. 
        """
        
        # build the signature
        signature_builder = astroidutils.SignatureBuilder(signature_class=signature_class, 
                                        value_formatter_class=value_formatter_class)

        # filter args
        args = [a for a in self.args if a.name != 'self' or include_self]
        
        for argument in (a for a in args if a.type is docspec.Argument.Type.PositionalOnly):
            signature_builder.add_param(argument.name, inspect.Parameter.POSITIONAL_ONLY, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type is docspec.Argument.Type.Positional):
            signature_builder.add_param(argument.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type is docspec.Argument.Type.PositionalRemainder):
            signature_builder.add_param(argument.name, inspect.Parameter.VAR_POSITIONAL, default=None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type is docspec.Argument.Type.KeywordOnly):
            signature_builder.add_param(argument.name, inspect.Parameter.KEYWORD_ONLY, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type is docspec.Argument.Type.KeywordRemainder):
            signature_builder.add_param(argument.name, inspect.Parameter.VAR_KEYWORD, default=None,
            annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        if include_return_type and self.return_type_ast:
            signature_builder.set_return_annotation(self.return_type_ast)
        
        try:
            signature = signature_builder.get_signature()
        except ValueError as ex:
            self.warn(f'Function "{self.full_name}" has invalid parameters: {ex}')
            signature = inspect.Signature()
        
        return signature
    
@dataclasses.dataclass(repr=False)
class Module(_model.Module, ApiObject):
    """
    Represents a module, basically a named container for code/API objects. Modules may be nested in other modules
    """

    docformat: Optional[str] = None # TODO: rename to dunder_docformat
    """The module variable __docformat__ as string."""

    def __post_init__(self) -> None:
        super().__post_init__()
        # help mypy
        self.members: List['ApiObject'] #type:ignore[assignment]
        self.parent: Optional['Module']


# Builder / Extensions API

# loader function is a function of the following form: 
#   (files: Sequence[Path], options: Any = None) -> TreeRoot

@attr.s(auto_attribs=True)
class Options:
    extensions: List[str] = attr.ib(factory=list)
    prepended_package: Optional[str] = None #TODO: implement me!
    introspect_c_modules: bool = False

def builder_from_options(options: Optional[Options]=None) -> 'astbuilder.Builder':
    """
    Factory method for Builder instances.
    """
    if not options:
        options=Options()
    
    from . import specfactory, processor, astbuilder, ext

    # load extensions
    extensions: List['ext.PydocspecExtension'] = []
    extensions.extend(ext._get_ext_from_module(m) for m in ext._get_all_defaults_ext())
    extensions.extend(ext._get_ext_from_module(m) for m in options.extensions)
    
    factory = specfactory.Factory()

    for m in extensions:
        # load extensions' mixins
        factory.add_mixins(**ext._get_mixins(m))

    builder = astbuilder.Builder(factory.TreeRoot(), processor.Processor(),
                                 options=options, )

    for m in extensions:
        # load extensions' ast visitors
        builder.visitor_extensions.update(*ext._get_astbuild_visitors(m))
        # load extensions' post build visitors
        builder.pprocessor.visitor_extensions.update(*ext._get_postbuild_visitors(m))
    
    return builder

def load_python_modules(files: Sequence[Path], options: Optional[Options] = None) -> TreeRoot:
    """
    Load packages or modules with pydocspec's builder. 

    :param files: A list of `Path` instances pointing to filenames/directory to parse.
        Directories will be added recursively. 
    """
    builder = builder_from_options(options)

    for f in files:
        builder.add_module(f)

    builder.build_modules()

    return builder.root

def load_python_modules_with_docspec_python(files: Sequence[Path], 
                                            options: Optional[Options] = None,
                                            docspec_options: 'docspec_python.ParserOptions' = None, ) -> TreeRoot:
    """
    Load packages or modules with docspec_python and then convert them to pydocspec objects. 
    """
    from docspec_python import parse_python_module
    from pydocspec import converter

    def _find_module(module_name: str, in_folder: str ) -> str:

        filenames = [
            os.path.join(os.path.join(*module_name.split('.')), '__init__.py'),
            os.path.join(*module_name.split('.')) + '.py',
        ]

        for choice in filenames:
            abs_path = os.path.normpath(os.path.join(in_folder, choice))
            if os.path.isfile(abs_path):
                return abs_path

        raise ImportError(module_name)

    def _find_module_files(modpath: Path) -> Iterable[Tuple[str, str]]:
        """
        Returns an iterator for the Python source files in the specified module/package. The items returned
        by the iterator are tuples of the module name and filename.
        """

        def _recursive(module_name:str, path:str) -> Iterator[Tuple[str, str]]:
            # pylint: disable=stop-iteration-return
            if os.path.isfile(path):
                yield module_name, path
            elif os.path.isdir(path):
                yield next(_recursive(module_name, os.path.join(path, '__init__.py')))
                for item in os.listdir(path):
                    if item == '__init__.py':
                        continue
                    item_abs = os.path.join(path, item)
                    name = module_name + '.' + item
                    if name.endswith('.py'):
                        name = name[:-3]
                    if os.path.isdir(item_abs) and os.path.isfile(os.path.join(item_abs, '__init__.py')):
                        for x in _recursive(name, item_abs):
                            yield x
                    elif os.path.isfile(item_abs) and item_abs.endswith('.py'):
                        yield next(_recursive(name, item_abs))
            else:
                raise RuntimeError('path "{}" does not exist'.format(path))

        module_name = os.path.splitext(modpath.name)[0]
        path = _find_module(module_name, str(modpath.parent))
        if os.path.basename(path).startswith('__init__.'):
            path = os.path.dirname(path)
            yield from _recursive(module_name, path)
    
    modules = []
    for path in files:
        for module_name, filename in _find_module_files(path):
            modules.append(parse_python_module(filename, module_name=module_name, options=docspec_options, encoding='utf-8'))

    return converter.convert_docspec_modules(modules, options=options)

def _setup_stdout_logger(
    name: str,
    verbose: bool = False,
    quiet: bool = False,
    ) -> logging.Logger:
    """
    Utility to create a logger.
    """
    # format_string = "%(asctime)s - %(levelname)s (%(name)s) - %(message)s"
    format_string = "%(message)s"
    if verbose: verb_level = logging.DEBUG
    elif quiet: verb_level = logging.ERROR
    else: verb_level = logging.INFO
    log = logging.getLogger(name)
    log.setLevel(verb_level)
    std = logging.StreamHandler(sys.stdout)
    std.setLevel(verb_level)
    std.setFormatter(logging.Formatter(format_string))
    log.addHandler(std)
    return log
_setup_stdout_logger('pydocspec')