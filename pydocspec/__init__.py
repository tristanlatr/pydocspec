"""
Pydocspec is a object specification for representing API documentation of a collection of related python modules. 
It offers facility to resolve names according to python lookups rules and provides additional informations. 

**Warning**:

Work in progress... API might change without deprecation notice.

**Usage**:

>>> import pydocspec
>>> root = pydocspec.load_python_modules([Path('./pydocspec')])

**How it works**

First, a root object gets created with the `specfactory`, then the `astbuilder` creates all the other objects
and populate the strict-minimum attributes. Then the `processor` takes that tree and populated all other attributes.

**Extensibility**:

The core of the logic is design to be extensible with extensions modules. See `pydocspec.ext`.
"""

# TODOs:
# - Setup code coverage.
# - Build pydocspec from imported modules too, if they are available in the system.
# - Add overriden in / overrides . What to do withData with annotation only?


from pathlib import Path
import types
from typing import TYPE_CHECKING, Iterable, Iterator, List, Optional, Sequence, Tuple, Union, Type, Any, cast, overload
import inspect
import os.path
import sys
import logging

import attr
from cached_property import cached_property

from . import _docspec, astroidutils, dupsafedict
from .dottedname import DottedName
from . import _model
from ._model import Inheritable, HasMembers

# should not import ast or astroid

if TYPE_CHECKING:
    import docspec_python
    from . import astbuilder
    import astroid

__docformat__ = 'restructuredtext'
__all__ = [
  'TreeRoot',
  'Location',
  'Decoration',
  'Argument',
  'ApiObject',
  'Variable',
  'Function',
  'Class',
  'Module',
  'Docstring',
]

_RESOLVE_ALIAS_MAX_RECURSE = 3

Location = _model.Location
Docstring = _model.Docstring
Argument = _model.Argument
Decoration = _model.Decoration

class TreeRoot(_model.TreeRoot):
    """
    A collection of related documentable objects, also known as "the system".
    
    This special object provides a single view on all referencable objects in the tree and root modules.

    :note: A reference to the root instance is kept on all API objects as `ApiObject.root`.
    """

    # help mypy
    root_modules: List['Module'] # type: ignore[assignment]
    all_objects: dupsafedict.DuplicateSafeDict[str, 'ApiObject'] # type: ignore[assignment]


class ApiObject(_model.ApiObject):
    """
    An augmented `docspec.ApiObject`, with functionalities to resolve names for the python language.
    """

    def _init_attribs(self) -> None:
        super()._init_attribs()

        # new attributes

        self.doc_sources: List['ApiObject'] = []
        """Objects that can be considered as a source of documentation.

        The motivating example for having multiple sources is looking at a
        superclass' implementation of a method for documentation for a
        subclass'.
        """

        self.aliases: List['Variable'] = []
        """
        Aliases to this object.
        """
    
    # help mypy
    root: TreeRoot
    parent: Optional[Union['Class', 'Module']]
    location: Location
    module: 'Module'
    docstring: Optional[Docstring]

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
            if follow_aliases and isinstance(member, Variable) and astroidutils.is_name(member.value_ast):
                indirection = member._alias_indirection
                return self._resolve_indirection(indirection, _indirections) or indirection.target
            if isinstance(member, Indirection):
                return self._resolve_indirection(member, _indirections) or member.target
            return member.full_name

        elif isinstance(self, Class): # type:ignore[unreachable]
            assert self.parent is not None  # type:ignore[unreachable]
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
    

class Variable(_model.Variable, ApiObject):
    """
    Represents a variable assignment.
    """

    @overload # type:ignore[misc]
    def __init__(self, 
                 location: Location, 
                 name: str, 
                 docstring: Optional[Docstring],
                 datatype: Optional[str], 
                 value: Optional[str], 
                 datatype_ast: Optional['astroid.nodes.NodeNG'],
                 value_ast: Optional['astroid.nodes.NodeNG'],
                 modifiers: Optional[List[str]] = None, 
                 semantic_hints: Optional[List[_docspec.VariableSemantic]] = None,
                 is_type_guarged: bool = False) -> None:
        ...
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def _init_attribs(self) -> None:
        super()._init_attribs()

        self.is_instance_variable: bool = False
        """
        Whether this Variable is an instance variable.
        """

        self.is_class_variable: bool = False
        """
        Whether this Variable is a class variable.
        """

        self.is_module_variable: bool = False
        """
        Whether this Variable is a module variable.
        """

        self.is_alias: bool = False
        """
        Whether this Variable is an alias.
        Aliases are folowed by default when using `ApiObject.expand_name`. 
        """

        self.is_type_alias: bool = False
        """
        Whether this Variable is a type alias.
        """

        self.is_constant: bool = False
        """
        Whether this Variable is a constant.
        """

    @cached_property
    def _alias_indirection(self) -> 'Indirection':
        # private helper object to resolve names only.
        assert self.value is not None
        indirection = Indirection(name=self.name, location=self.location, docstring=None, target=self.value)
        indirection.parent = self.parent
        indirection.root = self.root
        return indirection

    # help mypy
    parent: Union['Class', 'Module']


class Indirection(_model.Indirection, ApiObject):
    """
    Represents an imported name. It can be used to properly 
    find the full name target of a link written with a local name. 
    """
    # resolved_target: Optional[ApiObject] = None

    # help mypy
    parent: Union['Class', 'Module']

    @overload # type:ignore[misc]
    def __init__(self, 
                 location: Location, 
                 name: str, 
                 docstring: Optional[Docstring],
                 target: str, 
                 is_type_guarged: bool = False) -> None:
        ...
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class ClassInheritedMember:
        def __init__(self, member: ApiObject, inherited_via: Tuple['Class', ...]) -> None:
            self.member = member
            self.inherited_via = inherited_via


class Class(_model.Class, ApiObject):
    """
    Represents a class definition.
    """

    InheritedMember = ClassInheritedMember

    @overload # type:ignore[misc]
    def __init__(self, 
                 location: Location, 
                 name: str, 
                 docstring: Optional[Docstring],
                 members: List['ApiObject'],
                 metaclass: Optional[str], 
                 bases: Optional[List[str]], 
                 decorations: Optional[List[Decoration]], 
                 bases_ast: Optional[List['astroid.nodes.NodeNG']],
                 modifiers: Optional[List[str]] = None,
                 semantic_hints: Optional[List[_docspec.ClassSemantic]] = None,
                 is_type_guarged: bool = False, 
                 _ast: Optional['astroid.nodes.ClassDef'] = None
                 ) -> None:
        ...
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def _init_attribs(self) -> None:
        super()._init_attribs()

        self.is_exception: bool = False
        """
        Whether this class extends one of the standard library exceptions.
        """

        self.resolved_bases: List[Union['Class', 'str']] = []
        """
        For each bases, try to resolve the name to an `ApiObject` or fallback to the expanded name.
        
        :see: `resolve_name` and `expand_name`
        """

        self.mro: List['Class'] = cast('List[Class]', NotImplemented)
        """
        The method resoltion order of this class.
        """

        self.subclasses: List['Class'] = []
        """
        The direct subclasses of this class. 
        """

        self.constructor_method: Optional['Function'] = None
        """
        The constructor method of this class.
        """

        self.inherited_members: List['ClassInheritedMember'] = []
        """
        Members inherited from superclasses.
        """

        self.is_abstractclass: bool = False
        """
        Whether this class is abstract. 
        
        A class is abstract if it has abstract methods or if it's declared with ``metaclass=ABCMeta``.
        """
  
    # help mypy
    decorations: Optional[List['Decoration']] # type:ignore[assignment]
    parent: Union['Class', 'Module']
    members: List['ApiObject'] # type:ignore[assignment]
    
    def ancestors(self, include_self: bool = False) -> Iterator[Union['Class', 'str']]:
        """Reccursively returns `resolved_bases` for all bases."""
        if include_self:
            yield self
        for b in self.resolved_bases:
            if isinstance(b, Class):
                yield from b.ancestors(True)
            else:
                yield b
    
    def find(self, name: str, include_self: bool = True) -> Optional[ApiObject]:
        """
        Look up a name in this class and its base classes. 

        :return: The object with the given name, or `None` if there isn't one.
        """
        mro = self.mro
        if not include_self:
            mro = mro[1:]
        for base in mro:
            obj: Optional['ApiObject'] = base.get_member(name)
            if obj is not None:
                return obj
        return None


class Function(_model.Function, ApiObject):
    """
    Represents a function definition.
    """

    @overload # type:ignore[misc]
    def __init__(self, 
                 location: Location, 
                 name: str, 
                 docstring: Optional[Docstring],
                 modifiers: Optional[List[str]], 
                 args: List[Argument], 
                 return_type: Optional[str], 
                 return_type_ast: Optional['astroid.nodes.NodeNG'], 
                 decorations: Optional[List[Decoration]],
                 semantic_hints: Optional[List[_docspec.FunctionSemantic]] = None,
                 is_type_guarged: bool = False
                 ) -> None:
        ...
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


    def _init_attribs(self) -> None:
        super()._init_attribs()

        self.is_property: bool = False
        """
        Whether this Function is a property getter.
        """

        self.is_property_setter: bool = False
        """
        Whether this Function is a property setter.
        """

        self.is_property_deleter: bool = False
        """
        Whether this Function is a property deteter.
        """

        self.is_async: bool = False
        """
        Whether this Function is a coroutine, aka ``async`` function.
        """

        self.is_method: bool = False
        """
        Whether this Function is a method.
        """

        self.is_staticmethod: bool = False
        """
        Whether this Function is a static method.
        """

        self.is_classmethod: bool = False
        """
        Whether this Function is a class method.
        """

        self.is_abstractmethod: bool = False
        """
        Whether this Function is a abstract method.
        """

    # help mypy
    decorations: Optional[List['Decoration']] # type:ignore
    args: List['Argument'] # type:ignore
    parent: Union[Class, 'Module']

    def signature(self, include_types:bool=True, include_defaults:bool=True, 
                  include_return_type:bool=True, include_self:bool=True,
                  signature_class: Type[inspect.Signature] = inspect.Signature, 
                  value_formatter_class: Type[astroidutils.ValueFormatter] = astroidutils.ValueFormatter) -> inspect.Signature:
        """
        Get the function's signature. 

        :Parameters:
            include_types
                Whether to include the type annotation.
            include_defaults
                Whether to include the default values of parameters.
            include_return_type
                Whether to include the return type annotation.
            include_self
                Whether to include ``self`` as the first argument if it exist.
            signature_class
                A custom `inspect.Signature` subclass to build the signature with.
            value_formatter_class
                A custom `astroidutils.ValueFormatter` class to present the 
                annotations and parameters default values when calling `str()` on the signature object.
        
        :Returns: A signature built with the specified options.
        """
        
        # build the signature
        signature_builder = astroidutils.SignatureBuilder(signature_class=signature_class, 
                                        value_formatter_class=value_formatter_class)

        # filter args
        args = [a for a in self.args if a.name != 'self' or include_self]
        
        for argument in (a for a in args if a.type.name == 'POSITIONAL_ONLY'):
            signature_builder.add_param(argument.name, inspect.Parameter.POSITIONAL_ONLY, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type.name == 'POSITIONAL'):
            signature_builder.add_param(argument.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type.name == 'POSITIONAL_REMAINDER'):
            signature_builder.add_param(argument.name, inspect.Parameter.VAR_POSITIONAL, default=None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type.name == 'KEYWORD_ONLY'):
            signature_builder.add_param(argument.name, inspect.Parameter.KEYWORD_ONLY, 
                default=argument.default_value_ast if argument.default_value_ast and include_defaults else None,
                annotation=argument.datatype_ast if argument.datatype_ast and include_types else None)
        
        for argument in (a for a in args if a.type.name == 'KEYWORD_REMAINDER'):
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
    

class Module(_model.Module, ApiObject):
    """
    Represents a module, basically a named container for code/API objects. Modules may be nested in other modules
    """
    @overload # type:ignore[misc]
    def __init__(self, 
                 location: Location, 
                 name: str, 
                 docstring: Optional[Docstring],
                 members: List['ApiObject'],
                 is_package: bool = False, 
                 is_c_module: bool = False, 
                 source_path: Optional[Path] = None, 
                 _py_mod: Optional[types.ModuleType] = None, 
                 _py_string: Optional[str] = None) -> None:
        ...
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def _init_attribs(self) -> None:
        super()._init_attribs()

        self.docformat: Optional[str] = None # TODO: rename to dunder_docformat
        """The module variable __docformat__ as string."""

    # help mypy
    members: List['ApiObject'] #type:ignore[assignment]
    parent: Optional['Module']


# Builder / High-level API

@attr.s(auto_attribs=True)
class Options:
    extensions: List[str] = attr.ib(factory=list)
    load_optional_extensions: bool = False
    prepended_package: Optional[str] = None #TODO: implement me!
    introspect_c_modules: bool = False


def builder_from_options(options: Optional[Options]=None) -> 'astbuilder.Builder':
    """
    Factory method for Builder instances.

    This function puts together everything we need to build 
    object trees with extensions.
    """
    if not options:
        options=Options()
    
    from . import specfactory, processor, astbuilder, ext

    # list extensions
    extensions: List[str] = []
    extensions.extend(ext.get_default_extensions())
    if options.load_optional_extensions:
        extensions.extend(ext.get_optional_extensions())
    extensions.extend(options.extensions)

    # create builder
    builder = astbuilder.Builder(specfactory.Factory().TreeRoot(), 
                                 processor.Processor(),
                                 options=options, )

    # load extensions
    for m in extensions:
        ext.load_extension_module(builder, m)
    
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
