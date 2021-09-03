"""
Our own version of the docspec loader. 

:note: The current implementation is largely adapted from pydoctor's AST builder, simply based on the `ast` module. 
    Because of that, it is very fast. But single line comments (starting by ``"#"``) are ignored. 
    Except for type comments, that are supported by the AST module. 

"""
from typing import Iterable, Iterator, List, Dict, Optional, Sequence, Set, Union, cast
from pathlib import Path
from enum import Enum
from functools import partial
from itertools import chain
import sys
import ast
import platform
import inspect
import importlib.machinery
import warnings

import astor
import attr

import pydocspec
from . import astutils

def _parse_file(path: Path) -> ast.Module:
    """Parse the contents of a Python source file."""
    with open(path, 'rb') as f:
        src = f.read() + b'\n'
    return _parse(src, filename=str(path))

if sys.version_info >= (3,8):
    _parse = partial(ast.parse, type_comments=True)
else:
    _parse = ast.parse

_string_lineno_is_end = sys.version_info < (3,8) \
                    and platform.python_implementation() != 'PyPy'
"""True iff the 'lineno' attribute of an AST string node points to the last
line in the string, rather than the first line.
"""

class Collector:
    """
    Base class to organize a tree of `pydocspec` objects. 
    
    Maintains a stack of objects and incrementally build **one** `Module` instance.

    :see: `loader.add_object`
    """
    #TODO: add objects to the root in the Collector. 

    def __init__(self, root: pydocspec.ApiObjectsRoot, 
                 module: Optional[pydocspec.Module]=None) -> None:
        self.root = root
        """
        The root of the tree. 
        
        Can be used to access the ``root.factory`` attribute and create new classes.
        """
        # pytype complains because module it's defined as non-optional in ModuleVisitor.module.
        self.module = module #type:ignore[annotation-type-mismatch]
        """
        The new module.
        """

        self._current: pydocspec.ApiObject = cast(pydocspec.ApiObject, None) # the current object context 
        self._last: Optional[pydocspec.ApiObject] = None # the last exited object
        # we can push attributes, but we can't push other stuff inside it.
        self._stack: List[Union[pydocspec.Module, pydocspec.Class]] = []

    def push(self, ob: pydocspec.ApiObject) -> None:
        """
        Enter an object.
        """
        # Note: the stack is initiated with a None value.
        ctx = self._current
        if ctx is not None: 
            assert isinstance(ctx, pydocspec.HasMembers), (f"Cannot add new object ({ob!r}) inside {ctx.__class__.__name__}. "
                                                           f"{ctx.full_name} is not namespace.")
        self._stack.append(ctx)
        self._current = ob

    def pop(self, ob: pydocspec.ApiObject) -> None:
        """
        Exit an object.
        """
        assert self._current is ob , f"{ob!r} is not {self._current!r}"
        self._last = self._current
        self._current = self._stack.pop()
    
    def add_object(self, ob: pydocspec.ApiObject, push: bool = True) -> None:
        """
        See `loader.add_object`.
        """
        add_object(self.root, ob, self._current)
        
        if self._current is None:
            # yes, it's reachable, when first adding a module.
            assert isinstance(ob, pydocspec.Module) #type:ignore[unreachable]
            if self.module is None:
                self.module = ob
            else:
                # just do some assertion.
                assert self.module is ob, f"{ob!r} is not {self.module!r}"
        
        if push:
            self.push(ob)

def add_object(root: pydocspec.ApiObjectsRoot, 
               ob: pydocspec.ApiObject, 
               parent: Optional[pydocspec.ApiObject]) -> None:
    """
    Add a newly created object to the tree. 
    Responsible to add the object to the current namespace, setup parent attribute, setup 
    the new object to the root instance and respectively.

    :note: This does add root modules (if ``parent=None``) to the `ApiObjectsRoot.root_modules` attribute. 
    """
    if parent is not None:
        assert isinstance(parent, pydocspec.HasMembers), (f"Cannot add new object ({ob!r}) inside {parent.__class__.__name__}. "
                                                          f"{parent.full_name} is not namespace.")
        # setup child
        parent.members.append(ob)
        ob.parent = parent
    else:
        assert isinstance(ob, pydocspec.Module)
        # add root modules to root.root_modules attribute
        root.root_modules.append(ob)
    
    # Add object to the root.all_objects. 
    # If the object is a root module, it's either going to be added in by the converter or by the loader.
    root.all_objects[ob.full_name] = ob
    # set the ApiObject.root attribute right away.
    ob.root = root

class ModuleVisitor(ast.NodeVisitor, Collector):
    # help mypy
    module: pydocspec.Module
    
    def __init__(self, loader: 'Loader', module: pydocspec.Module) -> None:
        super().__init__(loader.root, module)
        self.loader = loader

    def default(self, node: ast.AST) -> None:
        """
        Visit the children of a node.
        """
        body: Optional[Sequence[ast.stmt]] = getattr(node, 'body', None)
        if body is not None:
            for child in body:
                self.visit(child)

    def _set_docstring(self, ob: pydocspec.ApiObject, node: ast.Str) -> None:
        doc = inspect.cleandoc(node.s)
        docstring_lineno = node.lineno
        
        if _string_lineno_is_end:
            # In older CPython versions, the AST only tells us the end line
            # number and we must approximate the start line number.
            # This approximation is correct if the docstring does not contain
            # explicit newlines ('\n') or joined lines ('\' at end of line).
            docstring_lineno -= doc.count('\n')

        # Leading blank lines are stripped by cleandoc(), so we must
        # return the line number of the first non-blank line.
        for ch in doc:
            if ch == '\n':
                docstring_lineno += 1
            elif not ch.isspace():
                break
        
        ob.docstring = self.root.factory.Docstring(content=doc, 
                        location=self.root.factory.Location(None, lineno=docstring_lineno))
   
    def visit_Expr(self, node: ast.Expr) -> None:
        """
        Handles the inline attribute docstrings.
        """
        value = node.value
        if isinstance(value, ast.Str):
            attr = self._last
            if isinstance(attr, pydocspec.Data) and attr.parent is self._current:
                self._set_docstring(attr, value)

        self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> None:
        """
        Visit an {ast.Module}.
        """

        # unprocessed modules should not have been initialized with a docstring yet.
        assert self.module.docstring is None

        if len(node.body) > 0 and isinstance(node.body[0], ast.Expr) and \
            isinstance(node.body[0].value, ast.Str):
            # setting the module docstring
            self._set_docstring(self.module, node.body[0].value)
        
        self.add_object(self.module)
        self.default(node)
        self.pop(self.module)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Ignore classes within functions.
        parent = self._current
        if isinstance(parent, pydocspec.Function):
            return None

        bases_str: Optional[List[str]] = None
        bases_ast: Optional[List[ast.expr]] = None

        if node.bases:
            bases_str = []
            bases_ast = []

        # compute the Class.bases attribute
        for n in node.bases:
            dotted_name = astutils.node2dottedname(n)
            if dotted_name is not None:
                str_base = '.'.join(dotted_name)
            else:
                str_base = astutils.to_source(n)
            assert isinstance(bases_str, list)
            assert isinstance(bases_ast, list)
            bases_str.append(str_base)
            bases_ast.append(n)

        lineno = node.lineno

        # If a class is decorated, set the linenumber from the line of the first decoration.
        if node.decorator_list:
            lineno = node.decorator_list[0].lineno

        # create new class
        cls: pydocspec.Class = self.root.factory.Class(node.name, 
                                    location=self.root.factory.Location(None, lineno=lineno),
                                    docstring=None, metaclass=None, 
                                    bases=bases_str, decorations=None, members=[])
        # set bases (AST)
        cls.bases_ast = bases_ast

        # set docstring
        if len(node.body) > 0 and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
            self._set_docstring(cls, node.body[0].value)

        # set decorations
        if node.decorator_list:
            cls.decorations = []
            for decnode in node.decorator_list:

                # compute decoration attributes
                name_ast: ast.expr
                name: str
                args_ast: Optional[List[ast.expr]]
                args: Optional[List[str]]

                if isinstance(decnode, ast.Call):
                    name_ast = decnode.func
                    dotted_name = astutils.node2dottedname(name_ast)
                    args_ast = decnode.args
                    args = []
                else:
                    name_ast = decnode
                    dotted_name = astutils.node2dottedname(name_ast)
                    args_ast = args = None
                
                if dotted_name is None:
                    name = astutils.to_source(name_ast)

                    # There were expressions for which node2dottedname() returns None, 
                    # this was leading into SyntaxError when used in a decorator.
                    # From Python3.9, any kind of expressions can be used as decorators, so we don't warn anymore.
                    # See Relaxing Grammar Restrictions On Decorators: https://www.python.org/dev/peps/pep-0614/
                    if sys.version_info < (3,9):
                        cls.warn("Cannot make sense of class decorator: '{name}'")
                else:
                    name = '.'.join(dotted_name)

                deco = self.root.factory.Decoration(name=name, args=None)
                # TODO: Adjust code once this issue is fixed.
                # see https://github.com/NiklasRosenstein/docspec/issues/45
                # deco = self.root.factory.Decoration(name=name, args=args) 
                
                # set name, etc (AST)
                deco.name_ast = name_ast
                deco.args_ast = args_ast
                deco.expr_ast = decnode
                
                cls.decorations.append(deco)
        
        self.add_object(cls)
        self.default(node)
        self.pop(cls)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        ctx = self._current
        if not isinstance(ctx, pydocspec.HasMembers):
            assert ctx is not None, "processing import statement with no current context: {node!r}"
            ctx.module.warn("processing import statement ({node!r}) in odd context: {ctx!r}",
                            lineno_offset=node.lineno)
            return

        modname = node.module
        level = node.level
        if level:
            # Relative import, we should have the module in the system.
            parent: Optional[Union[pydocspec.Class, pydocspec.Module]] = ctx.module
            
            if ctx.module.is_package:
                level -= 1
            
            for _ in range(level):
                if parent is None:
                    break
                parent = parent.parent
            
            # Walking up the tree to find the module that import statement imports.
            if parent is None:
                assert ctx.module is not None
                ctx.module.warn(
                    "relative import level (%d) too high" % node.level,
                    lineno_offset=node.lineno) 
                return
            
            if modname is None:
                modname = parent.full_name
            else:
                modname = f'{parent.full_name}.{modname}'
        else:
            # The module name can only be omitted on relative imports.
            assert modname is not None

        if node.names[0].name == '*':
            self._import_all(modname, lineno=node.lineno)
        else:
            self._import_names(modname, node.names, lineno=node.lineno)

    def _import_all(self, modname: str, lineno: int) -> None:
        """Handle a ``from <modname> import *`` statement."""

        mod = self.loader.get_processed_module(modname)
        if mod is None:
            # We don't have any information about the module, so we don't know
            # what names to import.
            self._current.module.warn("import * from unknown module: '{modname}'. Cannot trace all indirections.", 
                                       lineno_offset=lineno)
            return

        # Get names to import: use __all__ if available, otherwise take all
        # names that are not private.
        names = mod.all
        if names is None:
            names = [
                name
                for name in (m.name for m in mod.members)
                if not name.startswith('_')
                ]

        # Add imported names to our module namespace.
        assert isinstance(self._current, pydocspec.HasMembers)
        
        for name in names:
            indirection = self.root.factory.Indirection(name=name, 
                location=self.root.factory.Location(filename=None, lineno=lineno), docstring=None, 
                target=f'{modname}.{name}')
            self.add_object(indirection, push=False)

    def _import_names(self, modname: str, names: Iterable[ast.alias], lineno: int) -> None:
        """Handle a C{from <modname> import <names>} statement."""

        # Process the module we're importing from.
        mod = self.loader.get_processed_module(modname)

        for al in names:
            orgname, asname = al.name, al.asname
            if asname is None:
                asname = orgname

            # If we're importing from a package, make sure imported modules
            # are processed (get_processed_module() ignores non-modules).
            if mod is not None and mod.is_package:
                self.loader.get_processed_module(f'{modname}.{orgname}')

            indirection = self.root.factory.Indirection(name=asname, 
                location=self.root.factory.Location(filename=None, lineno=lineno), docstring=None, 
                target=f'{modname}.{orgname}')
            self.add_object(indirection, push=False)

    def visit_Import(self, node: ast.Import) -> None:
        """Process an import statement.

        The grammar for the statement is roughly:

        mod_as := DOTTEDNAME ['as' NAME]
        import_stmt := 'import' mod_as (',' mod_as)*

        and this is translated into a node which is an instance of Import wih
        an attribute 'names', which is in turn a list of 2-tuples
        (dotted_name, as_name) where as_name is None if there was no 'as foo'
        part of the statement.
        """
        ctx = self._current
        if not isinstance(ctx, pydocspec.HasMembers):
            assert ctx is not None, "processing import statement with no current context: {node!r}"
            ctx.module.warn("processing import statement ({node!r}) in odd context: {ctx!r}",
                            lineno_offset=node.lineno)
            return
        
        for al in node.names:
            fullname, asname = al.name, al.asname
            if asname is not None:
                indirection = self.root.factory.Indirection(name=asname, 
                    location=self.root.factory.Location(filename=None, lineno=node.lineno), docstring=None, 
                    target=fullname)
                self.add_object(indirection, push=False)
            # Do not create an indirection with the same name and target, this is pointless and it will
            # make the ApiObject._resolve_indirection() method reccurse one time more than needed.

    # TODO: Code the rest of it!

class ProcessingState(Enum):
    UNPROCESSED = 0
    PROCESSING = 1
    PROCESSED = 2

@attr.s(auto_attribs=True)
class Loader:
    """
    Coordinate the process of parsing and analysing the ast trees. 
    
    :note: The approach is to proceed incrementally, and outside-in. 
        First, you add the top-level directory structure, this computes the whole package/module structure. 
        Then, each modules are parse, it creates all object instances, then it does some analysis on what 
        we’ve found in post-processing. 
    """

    root: pydocspec.ApiObjectsRoot

    _added_paths: Set[Path] = attr.ib(factory=set)
    # Duplication of names in the modules is not currently supported.
    # This is a problem for Python too, the rule is that the folder/package wins.
    # Though, duplication in other objects is supported.
    # TODO: handle duplicates
    _processing_map: Dict[str, ProcessingState] = attr.ib(factory=dict)
    """Mapping from module's full_name to the processing state"""
    _source_path_map: Dict[str, Path] = attr.ib(factory=dict)
    """Mapping from module's full_name to it's real path"""
    _processing_mod_stack: List[pydocspec.Module] = attr.ib(factory=list)
    _ast_cache: Dict[Path, Optional[ast.Module]] = attr.ib(factory=dict)
    """Provides caching for ast modules."""
    
    ModuleVisitor = ModuleVisitor

    def _parse_file(self, path: Path) -> Optional[ast.Module]:
        """
        Exceptionnaly returns None if there was an error.
        """
        try:
            return self._ast_cache[path]
        except KeyError:
            mod: Optional[ast.Module] = None
            try:
                mod = _parse_file(path)
            except (SyntaxError, ValueError) as e:
                import warnings
                warnings.warn(f"Cannot parse file {path}: " + str(e))
                mod = None
            
            self._ast_cache[path] = mod
            return mod
    
    def _process_module_ast(self, mod_ast: ast.Module, mod: pydocspec.Module) -> None:
        builder_visitor = self.ModuleVisitor(self, mod)
        builder_visitor.visit(mod_ast)

    @property
    def unprocessed_modules(self) -> Iterator[pydocspec.Module]:
        for mod_name, state in self._processing_map.items():
            if state is ProcessingState.UNPROCESSED:
                # Support that function/class overrides a module name, but still process the module ;-)
                mods = self.root.all_objects.getall(mod_name)
                assert mods is not None, "Cannot find module '{mod_name}' in {root.all_objects!r}."
                for mod in mods:
                    assert isinstance(mod, pydocspec.Module)
                    yield mod
                    break

    def add_module(self, path: Path) -> None:
        """
        Add a module or package from a system path. If the path is pointing to a directory, reccursively add all submodules.
        """
        if path in self._added_paths:
            return
        if path.is_dir():
            if not (path / '__init__.py').is_file():
                raise RuntimeError(f"Source directory lacks __init__.py: {path}. The loader do not currently support namespace packages.")
            self._add_package(path)
        elif path.is_file():
            self._maybe_add_module(path)
        elif path.exists():
            raise RuntimeError(f"Source path is neither file nor directory: {path}")
        else:
            raise RuntimeError(f"Source path does not exist: {path}")
        self._added_paths.add(path)
    
    def _add_package(self, path: Path, parent: Optional[pydocspec.Module]=None) -> None:
        """
        Handles '__init__.py' files and reccursively calls itself when traversing subdirectories.
        """
        package = self._add_module(path / '__init__.py', path.name, parent, is_package=True)
        for path in sorted(path.iterdir()):
            if path.is_dir():
                if (path / '__init__.py').exists():
                    self._add_package(path, package)
            elif path.name != '__init__.py' and not path.name.startswith('.'):
                self._maybe_add_module(path, package)
    
    def _maybe_add_module(self, path: Path, parent: Optional[pydocspec.Module]=None) -> None:
        """
        Ignores the files that are not recognized as python files.
        """
        name = path.name
        for suffix in importlib.machinery.all_suffixes():
            if not name.endswith(suffix):
                continue
            module_name = name[:-len(suffix)]
            if suffix in importlib.machinery.EXTENSION_SUFFIXES:
                # TODO: Add support for introspection on C extensions.
                pass
            elif suffix in importlib.machinery.SOURCE_SUFFIXES:
                self._add_module(path, module_name, parent)
            break
    
    def _add_module(self,
            path: Union[Path, str],
            modname: str,
            parent: Optional[pydocspec.Module],
            is_package: bool = False
            ) -> pydocspec.Module: 
        """
        Create a new empty module and add it to the tree. Initiate it's state in the processing map.
        """
        location = self.root.factory.Location(filename=str(path), lineno=0)
        mod = self.root.factory.Module(name=modname, location=location, docstring=None, members=[])

        # We check if that's a duplicate module name.
        older_mod = self.root.all_objects.get(mod.full_name)
        if older_mod:
            assert isinstance(older_mod, pydocspec.Module)

            if is_package:
                older_mod.warn(f"Duplicate module name: '{mod.full_name}', the package/directory wins.")
                # The package wins, we remove the older module from the tree and we continue with the 
                # addition of the package.
                try:
                    self.root.root_modules.remove(older_mod)
                except ValueError:
                    assert older_mod.parent is not None
                    older_mod.parent.members.remove(older_mod)

                del self.root.all_objects[mod.full_name]
                del older_mod
            else:
                mod.warn(f"Duplicate module name: '{mod.full_name}', the package/directory wins.")
                del mod
                return older_mod
        
        # Set is_package such that we have the right information.
        mod.is_package = is_package

        add_object(self.root, mod, parent=parent)

        self._processing_map[mod.full_name] = ProcessingState.UNPROCESSED
        self._source_path_map[mod.full_name] = path

        return mod

    def _process_module(self, mod:pydocspec.Module) -> None:
        """
        Parse the module file to an AST and create it's members. At the time this method is called, not all objects are created. 
        But all module instances already exist and are added to `root.all_objects`, including nested modules.
        """
        assert self._processing_map[mod.full_name] is ProcessingState.UNPROCESSED
        self._processing_map[mod.full_name] = ProcessingState.PROCESSING
        
        path = self._source_path_map[mod.full_name]
        if path is None:
            return #type:ignore[unreachable]
        
        ast = self._parse_file(path)
        
        if ast:
            self._processing_mod_stack.append(mod)
            self._process_module_ast(ast, mod)
            head = self._processing_mod_stack.pop()
            assert head is mod
        
        self._processing_map[mod.full_name] = ProcessingState.PROCESSED

    def process_modules(self) -> None:
        """
        Process unprocessed modules.
        """
        while list(self.unprocessed_modules):
            mod = next(self.unprocessed_modules)
            self._process_module(mod)
    
    def get_processed_module(self, modname: str) -> Optional[pydocspec.Module]:
        """Returns the processed module or None if the name cannot be found."""
        mod = self.root.all_objects.get(modname)
        
        if mod is None: return None
        if not isinstance(mod, pydocspec.Module): return None
                
        if self._processing_map.get(mod.full_name) is ProcessingState.UNPROCESSED:
            self._process_module(mod)
            assert self._processing_map[mod.full_name] in (ProcessingState.PROCESSING, ProcessingState.PROCESSED)
        
        return mod

    
