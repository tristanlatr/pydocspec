
"""
Traverse module/packages directories, build and transform `astroid` AST into `ApiObject` instances.

:note: Implementation is largely adapted from pydoctor's AST builder, adapted to work with `astroid`. 

:note: The builder is responsible to asseble the tree of objects, but do set all attributes. 
    It only sets the strict minumum attributes required to process the rest of the attributes.
    The strict minimum beeing represented by the classes in `_model` module.

"""
import abc
import re
import dataclasses
import textwrap
import types
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Iterable, Iterator, List, Dict, Optional, Sequence, Set, Tuple, Type, Union, cast
from pathlib import Path
from enum import Enum
from functools import partial
from itertools import chain
import sys
import logging
import platform
import inspect
import importlib.machinery

import astroid.builder
import astroid.rebuilder
import astroid.nodes
import astroid.mixins
import astroid.exceptions
import astroid.manager
import attr

# Implementation note: 
# The builder should not import pydocspec, it should not be aware of pydocspec.* classes

from pydocspec import (_model, astroidutils, introspect, processor, 
                       basebuilder, visitors)
import pydocspec

if TYPE_CHECKING:
    import docspec

_string_lineno_is_end = sys.version_info < (3,8) \
                    and platform.python_implementation() != 'PyPy'
"""True iff the 'lineno' attribute of an AST string node points to the last
line in the string, rather than the first line.
"""

def is_attribute_overridden(obj: _model.Data, new_value: Optional[astroid.nodes.NodeNG]) -> bool:
    """
    Detect if the optional C{new_value} expression override the one already stored in the L{_model.Data.value} attribute.
    """
    return obj.value_ast is not None and new_value is not None
    
    # >>> print(astroid.parse("class AST:\n    def __init__(self):\n        self.v:int=0").body[0].instantiate_class().getattr('v')[0].repr_tree())
    # AssignAttr(
    # attrname='v',
    # expr=Name(name='self'))
    # >>> print(next(astroid.parse("class AST:\n    def __init__(self):\n        self.v:int=0").body[0].instantiate_class().igetattr('v')).repr_tree())
    # Const(
    # value=0,
    # kind=None)
    # >>> print(next(astroid.parse("class AST:\n    def __init__(self, v=0):\n        self.v=v").body[0].instantiate_class().igetattr('v')).repr_tree())
    # Const(
    # value=0,
    # kind=None)

class CyclicImport(Exception):
    """
    Raised when trying to resolved an "from mod import *" statement 
    from a module that is not totally processed yet.
    """
    def __init__(self, message:str, module: '_model.Module'):            
        super().__init__(message)
        self.module: '_model.Module' = module

# Need to monkey path the astroid TreeRebuilder in order to make it ignore the `.doc` attribute, 
# we are associating the docstring expr to the object ourself because of https://github.com/PyCQA/astroid/issues/1340
#  -> TODO: use the new '.doc_node' attribute when the PR https://github.com/PyCQA/astroid/pull/1276 is merged
astroid.rebuilder.TreeRebuilder._get_doc = lambda _,o:(o, None)

class BuilderVisitor(basebuilder.Collector, visitors.AstVisitor):
    # help mypy
    module: _model.Module
    
    def __init__(self, builder: 'Builder', module: _model.Module) -> None:
        visitors.AstVisitor.__init__(self, extensions=None)
        basebuilder.Collector.__init__(self, root=builder.root, module=module)
        
        self.builder = builder
    
    ### DOCSTRING ###
    def _set_docstring(self, ob: _model.ApiObject, node: astroid.nodes.Const) -> None:
        """
        Set the docstring of a object from a L{astroid.nodes.Const} node. 
        """
        doc = node.value
        if not isinstance(doc, str): 
            return
        lineno = node.lineno
        if _string_lineno_is_end:
            # In older CPython versions, the AST only tells us the end line
            # number and we must approximate the start line number.
            # This approximation is correct if the docstring does not contain
            # explicit newlines ('\n') or joined lines ('\' at end of line).
            lineno -= doc.count('\n')

        # Leading blank lines are stripped by cleandoc(), so we must
        # return the line number of the first non-blank line.
        for ch in doc:
            if ch == '\n':
                lineno += 1
            elif not ch.isspace():
                break

        docstring = inspect.cleandoc(doc)
        docstring_lineno = lineno
        
        # until https://github.com/NiklasRosenstein/docspec/pull/50 is merged.
        ob.docstring = cast('docspec.Docstring', self.root.factory.Docstring(docstring, 
            self.root.factory.Location(self.current.location.filename, lineno=docstring_lineno)))
    
    def _maybe_set_docstring(self, obj: '_model.ApiObject', 
                                 node: Union[astroid.nodes.Module, astroid.nodes.ClassDef, 
                                             astroid.nodes.FunctionDef, astroid.nodes.AsyncFunctionDef]) -> None:
            if len(node.body) > 0 and isinstance(node.body[0], astroid.nodes.Expr) \
               and isinstance(node.body[0].value, astroid.nodes.Const):
                self._set_docstring(obj, node.body[0].value)

    # DECORATIONS

    def _parse_decorations(self, decorators_nodes: Iterable[astroid.nodes.NodeNG]) -> Iterator[_model.Decoration]:        
        for decnode in decorators_nodes:

            # compute decoration attributes
            name_ast: astroid.nodes.NodeNG
            name: str
            arglist: Optional[List[str]] = None

            if isinstance(decnode, astroid.nodes.Call):
                name_ast = decnode.func
                dotted_name = astroidutils.node2dottedname(name_ast, strict=True)
                arglist = [astroidutils.to_source(n) for n in decnode.args] + \
                    [f"{(n.arg+'=') if n.arg else '**'}{astroidutils.to_source(n.value) if n.value else ''}" for n in decnode.keywords]
            else:
                name_ast = decnode
                dotted_name = astroidutils.node2dottedname(name_ast, strict=True)
            
            if dotted_name is None:
                name = astroidutils.to_source(name_ast)

                # There were expressions for which node2dottedname() returns None, 
                # this was leading into SyntaxError when used in a decorator.
                # From Python3.9, any kind of expressions can be used as decorators, so we don't warn anymore.
                # See Relaxing Grammar Restrictions On Decorators: https://www.python.org/dev/peps/pep-0614/
                if sys.version_info < (3,9):
                    cls.warn(f"Cannot make sense of class decorator: '{name}'")
            else:
                name = '.'.join(dotted_name)

            yield self.root.factory.Decoration(
                name=name, 
                arglist=arglist,
                name_ast=name_ast,
                expr_ast=decnode,
                )

    # Handles type guard, not working for some reason...
    # def visitIf(self, node: astroid.nodes.If) -> None:
    #     if astroidutils.is_type_guard(node):
    #         self.state.is_type_guarged = True
    #         logging.getLogger('pydocspec').info('Entering TYPE_CHECKING if block')
    #         self.generic_visit(node)
    #         logging.getLogger('pydocspec').info('Leaving TYPE_CHECKING if block')
    #         self.state.is_type_guarged = False
    #     else:
    #         self.generic_visit(node)

    def visit_Expr(self, node: astroid.nodes.Expr) -> None:
        """
        Handles the inline attribute docstrings.
        """
        value = node.value
        if isinstance(value, astroid.nodes.Const) and isinstance(value.value, str):
            attr = self.last
            if isinstance(attr, _model.Data) and attr.parent is self.current:
                self._set_docstring(attr, value)

    ### MODULE ###

    def visit_module(self, node: astroid.nodes.Module) -> None:
        """
        Visit an {astroid.nodes.Module}.
        """
        # TODO: check this assertion and re-enable it
        # unprocessed modules should not have been initialized with a docstring yet.
        # assert self.module.docstring is None

        if len(node.body) > 0 and isinstance(node.body[0], astroid.nodes.Expr) and \
            isinstance(node.body[0].value, astroid.nodes.Const) and node.body[0].value.pytype() == 'str':
            # setting the module docstring
            self._set_docstring(self.module, node.body[0].value)

        # The new module should already be added to the tree.
        assert self.module in self.root.all_objects.getall(self.module.full_name, []) 
        self.push(self.module)
    
    def depart_module(self, node: astroid.nodes.Module) -> None:

        # The processing of the __all__ variable should go there 
        # since it's used in _newIndirectionsFromWildcardImport()
        self.module.dunder_all = processor.mod_attr.dunder_all(self.module)

        self.pop(self.module)
    
    ### CLASSES ###

    def visit_classdef(self, node: astroid.nodes.ClassDef) -> None:
        """
        Visit a class. 
        """
        # Ignore classes within functions.
        if isinstance(self.current, _model.Function):
            raise self.SkipNode()

        bases_str: Optional[List[str]] = None
        bases_ast: Optional[List[astroid.nodes.NodeNG]] = None

        if node.bases:
            bases_str = []
            bases_ast = []

        # compute the dummy Class.bases attribute and unstring bases_ast.
        for n in node.bases:            
            assert isinstance(bases_str, list)
            assert isinstance(bases_ast, list)
        
            # try to unstring the annotation of the base classes
            try:
                n = astroidutils.unstring_annotation(n)
            except SyntaxError:
                #TODO: Log warning.
                pass
            
            bases_str.append(n.as_string())
            bases_ast.append(n)

        lineno = node.lineno

        # If a class is decorated, 
        # set the linenumber from the line of the first decoration.
        # NO, not needed anymore since we can warn on decorators directly now.
        # And also if made the ast2apiobject() function buggy because it's looking for classes with the same line number
        # if decorators:
        #     lineno = decorators[0].lineno

        # create new class
        cls: _model.Class = self.root.factory.Class(node.name, 
                                    location=self.root.factory.Location(
                                        self.current.location.filename, lineno=lineno),
                                    docstring=None, metaclass=None, 
                                    bases=bases_str, 
                                    bases_ast=bases_ast,
                                    decorations=None, 
                                    members=[], 
                                    is_type_guarged=astroidutils.is_type_guarded(node, self.current), 
                                    _ast=node)
        self.add_object(cls)

        # set docstring
        self._maybe_set_docstring(cls, node)
        
        # set decorations
        decorators = node.decorators.nodes if node.decorators else None
        if decorators:
            cls.decorations = list(self._parse_decorations(decorators))
        

    def depart_classdef(self, node: astroid.nodes.ClassDef) -> None:

        self.pop(self.current)

    ### IMPORTS ###

    def visit_importfrom(self, node: astroid.nodes.ImportFrom) -> None:
        ctx = self.current
        if not isinstance(ctx, _model.HasMembers):
            assert ctx is not None, f"processing import statement with no current context: {node!r}"
            # ctx.module.warn(f"processing import statement ({node!r}) in odd context: {ctx!r}",
            #                 lineno_offset=node.lineno)
            raise self.SkipNode()

        modname = node.modname

        level = node.level
        if level:
            # Relative import, we should have the module in the system.
            parent: Optional[Union[_model.Class, _model.Module]] = ctx.module
            
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
            
            if not modname:
                modname = parent.full_name
            else:
                modname = f'{parent.full_name}.{modname}'
        else:
            # The module name can only be omitted on relative imports.
            assert modname
        
        is_type_guarged = astroidutils.is_type_guarded(node, ctx)

        if node.names[0][0] == '*':
            for i in self._newIndirectionsFromWildcardImport(modname, lineno=node.lineno, 
                                      is_type_guarged=is_type_guarged):
                # do not add indirection with the same name and target
                # Note: we use str(self.current.dotted_name+i.name) to get the full name of the indirection 
                # because .full_name does not work on object that are not added to the tree yet.
                if str(self.current.dotted_name+i.name) != i.target:
                    self.add_object(i, push=False)
        else:
            for i in self._newIndirections(modname, node.names, lineno=node.lineno, 
                                        is_type_guarged=is_type_guarged):
                # do not add indirection with the same name and target
                if str(self.current.dotted_name+i.name) != i.target:
                    self.add_object(i, push=False)

    def _newIndirectionsFromWildcardImport(self, modname: str, lineno: int, 
                    is_type_guarged:bool) -> Iterator[_model.Indirection]:
        """
        Handle a ``from <modname> import *`` statement.
        
        This method may be called in a latter stage of the processing to 
        resolve unresolve imports in the first analysis pass.
        """

        from_module = self.builder.get_processed_module(modname)
        if from_module is None:
            # We don't have any information about the module, so we don't know
            # what names to import.
            self.current.module.warn(f"import * from unknown module: '{modname}'. Cannot trace all indirections.", 
                                    lineno_offset=lineno)
            return
        
        if self.builder.processing_map.get(from_module.full_name) == ProcessingState.PROCESSING:
            # there is a cyclic import, we can't rely on our module visitor to have 
            # collected all the objects in the module, so we use astroid instead.
            assert from_module._ast is not None
            names = from_module._ast.wildcard_import_names()
            self.current.module.warn("Can't resolve cyclic wildcard imports", lineno_offset=lineno)
        else:
            # if there is no cycles,
            # Get names to import: use __all__ if available, otherwise take all
            # names and ignore private
            names = (from_module.dunder_all or 
                processor.mod_attr.public_names(from_module))

        # Add imported names to our module namespace.
        assert isinstance(self.current, _model.HasMembers)
        
        yield from self._newIndirections(modname, 
            [(n, None) for n in names], 
            lineno, is_type_guarged)

    def _newIndirections(self, modname: str, names: Iterable[Tuple[str, Optional[str]]], lineno: int, 
                      is_type_guarged:bool) -> Iterator[_model.Indirection]:
        """Handle a C{from <modname> import <names>} statement."""

        for al in names:
            orgname, asname = al[0], al[1]
            if asname is None:
                asname = orgname

            indirection = self.root.factory.Indirection(name=asname, 
                location=self.root.factory.Location(filename=self.current.location.filename, lineno=lineno), docstring=None, 
                target=f'{modname}.{orgname}', is_type_guarged=is_type_guarged)
            
            yield indirection

    def visit_import(self, node: astroid.nodes.Import) -> None:
        """Process an import statement.

        The grammar for the statement is roughly:

        mod_as := DOTTEDNAME ['as' NAME]
        import_stmt := 'import' mod_as (',' mod_as)*

        and this is translated into a node which is an instance of Import wih
        an attribute 'names', which is in turn a list of 2-tuples
        (dotted_name, as_name) where as_name is None if there was no 'as foo'
        part of the statement.
        """
        ctx = self.current
        if not isinstance(ctx, _model.HasMembers):
            assert ctx is not None, "processing import statement with no current context: {node!r}"
            ctx.module.warn("processing import statement ({node!r}) in odd context: {ctx!r}",
                            lineno_offset=node.lineno)
            return
        is_type_guarged=astroidutils.is_type_guarded(node, ctx)
        for al in node.names:
            fullname, asname = al[0], al[1]
            if asname is not None:
                indirection = self.root.factory.Indirection(name=asname, 
                    location=self.root.factory.Location(filename=self.current.location.filename, lineno=node.lineno), docstring=None, 
                    target=fullname, is_type_guarged=is_type_guarged)
                # do not add indirection with the same name and target
                if str(self.current.dotted_name+indirection.name) != indirection.target:
                    self.add_object(indirection, push=False)
                
            # Do not create an indirection with the same name and target, this is pointless and it will
            # make the ApiObject._resolve_indirection() method reccurse one time more than needed, or even fail.

    # TODO: Code the rest of it!

    # Duplicate building names rationale: 
    #   Do not try to handle duplicates from the builder, 
    #   all objects might not be added at the time we do these checks.
    # Duplicate Module: this is not supported by the Builder, it's not supported by python neither.
    # Duplicate Indirection: Object defined after wins (older Indirection can still be accessed).
    # Duplicate Data: No exceptions. Object defined after wins (older Data can still be accessed).
    # Duplicate Class object: Object defined after wins (older Class can still be accessed).
    # Duplicate Function object: Object defined after wins (older Function can still be accessed).


    ### ATTRIBUTES ###

    def visit_assign(self, node: astroid.nodes.Assign) -> None:
        lineno = node.lineno
        expr = node.value

        type_ann = node.type_annotation
        if type_ann is None:
            annotation = None
        else:
            annotation = astroidutils.unstring_annotation(type_ann)

        for target in node.targets:
            if isinstance(target, astroid.nodes.Tuple):
                for elem in target.elts:
                    # Note: We skip type and aliasing analysis for this case, (why?)
                    #       but we do record line numbers.
                    self._handleAssignment(elem, None, None, lineno)
            else:
                self._handleAssignment(target, annotation, expr, lineno)

    def visit_annassign(self, node: astroid.nodes.AnnAssign) -> None:
        annotation = astroidutils.unstring_annotation(node.annotation)
        self._handleAssignment(node.target, annotation, node.value, node.lineno)
    
    def _handleAssignment(self,
            target_node: astroid.nodes.NodeNG,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:
        if isinstance(target_node, (astroid.nodes.Name, astroid.nodes.AssignName)):
            target = target_node.name
            scope = self.current
            if isinstance(scope, _model.Module):
                self._handleAssignmentInModule(target, annotation, expr, lineno)
            elif isinstance(scope, _model.Class):
                # if not self._handleOldSchoolMethodDecoration(target, expr): post-processing
                self._handleAssignmentInClass(target, annotation, expr, lineno)
        elif isinstance(target_node, (astroid.nodes.Attribute, astroid.nodes.AssignAttr)):
            value = target_node.expr
            if target_node.attrname == '__doc__':
                pass
                # self._handleDocstringUpdate(value, expr, lineno)
            elif isinstance(value, astroid.nodes.Name) and value.name == 'self':
                self._handleInstanceVar(target_node.attrname, annotation, expr, lineno)
            # TODO: Fix https://github.com/twisted/pydoctor/issues/13

    def _newData(self, name: str, 
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int, 
            semantics: List[pydocspec.Data.Semantic]) -> pydocspec.Data:
        """
        Create a new Data object.
        """
        if annotation is None and expr is not None:
            annotation = astroidutils.infer_type_annotation(expr)
        datatype_ast = datatype = value = value_ast = None
        if annotation is not None:
            datatype_ast = annotation
            datatype = annotation.as_string()
        if expr is not None:
            value = expr.as_string()
            value_ast = expr

        obj = self.root.factory.Data(name, 
                                    location=self.root.factory.Location(self.current.location.filename, lineno),
                                    docstring=None,
                                    datatype=datatype,
                                    datatype_ast=datatype_ast,
                                    value=value,
                                    value_ast=value_ast,
                                    semantic_hints=semantics)
        return obj

    def _handleModuleVar(self,
            name: str,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:

        obj = self._newData(name, annotation, expr, lineno, [])
        self.add_object(obj, push=False) # add object right away

        if processor.data_attr.is_constant(obj):
            obj.semantic_hints.append(obj.Semantic.CONSTANT)

            # handled in ext.dup
            # if is_alias(expr):
            #     self._handleAlias(obj=obj, value=expr, lineno=lineno)
            # elif is_constant(obj):
            #     self._handleConstant(obj=obj, value=expr, lineno=lineno)
            # else:
            #     obj.kind = model.DocumentableKind.VARIABLE
            #     # We store the expr value for all Attribute in order to be able to 
            #     # check if they have been initialized or not.
            #     obj.value = expr
        # else:
        #     pass
            # this module variable shadows another object in the module.

    def _handleAssignmentInModule(self,
            target: str,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:
        module = self.current
        assert isinstance(module, _model.Module)
        self._handleModuleVar(target, annotation, expr, lineno)

    def _handleClassVar(self,
            name: str,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:
        cls = self.current
        assert isinstance(cls, _model.Class)
        #TODO: Ensure a variable do not shadow an inherited object, post-processing.

        obj = self._newData(name, annotation, expr, lineno, 
                        [self.root.factory.Data.Semantic.CLASS_VARIABLE])
        self.add_object(obj, push=False)
        if processor.data_attr.is_constant(obj):
            obj.semantic_hints.append(obj.Semantic.CONSTANT)

        # in processor

        # if astroidutils.is_name(expr):
        #     self._handleAlias(obj=obj, value=expr, lineno=lineno)
        # elif processor.data_attr.is_constant(obj):
        #     self._handleConstant(obj=obj, value=expr, lineno=lineno)

    def _handleInstanceVar(self,
            name: str,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:
            #TODO: Ensure a variable do not shadow an inherited object, post-processing.

        func = self.current
        if not isinstance(func, _model.Function):
            return # this could happend if a self.name statement appears at the module level
        cls = func.parent
        if not isinstance(cls, _model.Class):
            return # this could happend if a function with self is defined outside of the class scope

        obj = self._newData(name, annotation, expr, lineno, 
                        [self.root.factory.Data.Semantic.INSTANCE_VARIABLE])
        self.add_object(obj, push=False, parent=cls)
        
        if processor.data_attr.is_constant(obj):
            obj.semantic_hints.append(obj.Semantic.CONSTANT)

        # Maybe an instance variable overrides a constant, 
        # so we check before adding INSTANCE_VARIABLE to semantics.
        # if processor.data_attr.is_constant(obj):
        #     self._warnsConstantReAssigmentInInstance(obj, lineno_offset=lineno-obj.location.lineno)
        # else:
        #     obj.semantic_hints.append(obj.Semantic.INSTANCE_VARIABLE) # this can be added more than once, it's ok
        #     obj.value = expr.as_string()
        #     obj.value_ast = expr

    def _handleAssignmentInClass(self,
            target: str,
            annotation: Optional[astroid.nodes.NodeNG],
            expr: Optional[astroid.nodes.NodeNG],
            lineno: int
            ) -> None:
        cls = self.current
        assert isinstance(cls, _model.Class)
        self._handleClassVar(target, annotation, expr, lineno)
    
    def visit_AsyncFunctionDef(self, node: astroid.nodes.AsyncFunctionDef) -> None:
        self._handleFunctionDef(node, is_async=True)

    def visit_FunctionDef(self, node: astroid.nodes.FunctionDef) -> None:
        self._handleFunctionDef(node, is_async=False)

    def _handleFunctionDef(self,
            node: Union[astroid.nodes.AsyncFunctionDef, astroid.nodes.FunctionDef],
            is_async: bool
            ) -> None:
        # Ignore inner functions.
        parent = self.current
        if isinstance(parent, _model.Function):
            raise self.SkipNode()

        lineno = node.lineno
        
        func_name = node.name

        func = self.root.factory.Function(name=func_name, 
                location=self.root.factory.Location(
                        filename=self.current.location.filename, 
                        lineno=lineno), 
                docstring=None, 
                modifiers=['async'] if is_async else None,
                args=[],
                return_type_ast=node.returns if node.returns else None,
                return_type=astroidutils.to_source(node.returns) if node.returns else None,
                decorations=None,
                )  
        self.add_object(func)

        # set args
        try:
            func_sig = astroidutils.build_signature(node)
        except ValueError as e:
            func.warn(f'{func.full_name} has invalid parameters: {e}')
        else:
            func.args = [basebuilder.parameter2argument(p, self.root.factory) \
                    for p in func_sig.parameters.values()]

        # set docstring
        self._maybe_set_docstring(func, node)

        # set decorations
        decorators = node.decorators.nodes if node.decorators else None
        if decorators:
            func.decorations = list(self._parse_decorations(decorators))

    def depart_FunctionDef(self, node:astroid.nodes.FunctionDef) -> None:
        self.pop(self.current)
    
    depart_AsyncFunctionDef = depart_FunctionDef

    # def _handleDocstringUpdate(self,
    #         targetNode: astroid.nodes.NodeNG,
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     def warn(msg: str) -> None:
    #         module = self.builder.currentMod
    #         assert module is not None
    #         module.report(msg, section='ast', lineno_offset=lineno)

    #     # Ignore docstring updates in functions.
    #     scope = self.current
    #     if isinstance(scope, model.Function):
    #         return

    #     # Figure out target object.
    #     full_name = node2fullname(targetNode, scope)
    #     if full_name is None:
    #         warn("Unable to figure out target for __doc__ assignment")
    #         # Don't return yet: we might have to warn about the value too.
    #         obj = None
    #     else:
    #         obj = self.system.objForFullName(full_name)
    #         if obj is None:
    #             warn("Unable to figure out target for __doc__ assignment: "
    #                  "computed full name not found: " + full_name)

    #     # Determine docstring value.
    #     try:
    #         if expr is None:
    #             # The expr is None for detupling assignments, which can
    #             # be described as "too complex".
    #             raise ValueError()
    #         docstring: object = ast.literal_eval(expr)
    #     except ValueError:
    #         warn("Unable to figure out value for __doc__ assignment, "
    #              "maybe too complex")
    #         return
    #     if not isinstance(docstring, str):
    #         warn("Ignoring value assigned to __doc__: not a string")
    #         return

    #     if obj is not None:
    #         obj.docstring = docstring
    #         # TODO: It might be better to not perform docstring parsing until
    #         #       we have the final docstrings for all objects.
    #         obj.parsed_docstring = None

class ProcessingState(Enum):
    UNPROCESSED = 0
    PROCESSING = 1
    PROCESSED = 2

@attr.s(auto_attribs=True)
class Builder:
    """
    Coordinate the process of parsing and analysing the ast trees. 
    
    :note: The approach is to proceed incrementally, and outside-in. 
        First, you add the top-level directory structure, this computes the whole package/module structure. 
        Then, each modules are parse, it creates all object instances, then it does some analysis on what 
        we’ve found in post-processing. 
    """

    root: 'pydocspec.TreeRoot'
    """
    Tree root.
    """

    pprocessor: 'processor.Processor'
    """
    Post processor. 
    """

    options: 'pydocspec.Options'
    """
    Options
    """  

    visitor_extensions: Set[Union['visitors.AstVisitorExt', Type['visitors.AstVisitorExt']]] = attr.ib(factory=set)
    """
    AST build visitor extensions.
    """
    
    _added_paths: Set[Path] = attr.ib(factory=set, init=False)
    # Duplication of names in the modules is not supported.
    # This is a problem for Python too, the rule is that the folder/package wins.
    # Though, duplication in other objects is supported.
    processing_map: Dict[str, ProcessingState] = attr.ib(factory=dict, init=False)
    """Mapping from module's full_name to the processing state"""
    _processing_mod_stack: List[_model.Module] = attr.ib(factory=list, init=False)
    
    def _process_module_ast(self, mod_ast: astroid.nodes.Module, mod: _model.Module) -> None:
        builder_visitor = BuilderVisitor(self, mod)
        builder_visitor.extensions.add(*self.visitor_extensions)
        builder_visitor.walkabout(mod_ast)
    
    @property
    def introspect_c_modules(self) -> bool:
        """
        Optionally instrospect C modules enabled?
        """
        return self.options.introspect_c_modules
    
    @property
    def unprocessed_modules(self) -> Iterator[_model.Module]:
        for mod_name, state in self.processing_map.items():
            if state is ProcessingState.UNPROCESSED:
                
                mods = self.root.all_objects.getall(mod_name)
                assert mods is not None, f"Cannot find module '{mod_name}' in the system."
                
                for mod in mods:
                    # Support that function/class overrides a module name, but still process the module ;-)
                    #TODO: test this.

                    # This returns the module object macthing the name.
                    if isinstance(mod, _model.Module): #type:ignore[unreachable]
                        yield mod #type:ignore[unreachable]
                        break
                else:
                    raise RuntimeError(f"No module found for name '{mod_name}', though it appears in the processing map: {self.processing_map!r}.")

    def add_module_string(self, text: str, modname: str,
                          parent_name: Optional[str] = None,
                          path: str = '<fromtext>',
                          is_package: bool = False, ) -> None:
        """
        Add a module to the builder from a simple string. 

        :Parameters:
            text
                The module string
            modname
                The module short name
            parent_name
                The fully qualified name of the parent package
                of this module. The package should be added to the 
                builder first.
            is_package
                Whether this module is a package.
        """
        
        # this code was originaly part of the testing modules, but I figured it would
        # be helpful to have it integrated with the Builder object.
        py_string = textwrap.dedent(text)
        parent = self.root.all_objects.get(parent_name) if parent_name else None
        if parent_name:
            if not isinstance(parent, pydocspec.Module):
                # If one adds a module string and call build_modules() 
                # after aleady have called build_modules() once,
                # another object might have shadowed the module name.
                # TODO: think about how we want to handle this situation.
                raise ValueError(f"Cannot find module '{parent_name!r}' in system, "
                        f"added modules: {', '.join(self.processing_map)}.")
        
        mod = self._add_module(path, modname, 
            # Set containing package as parent.
            # (we tell mypy that we already assert tha parent is a Module)
            parent=parent, #type:ignore[arg-type]
            is_package=is_package, 
            py_string=py_string)
        
        # Just do some assertions
        assert mod in self.unprocessed_modules
        if parent_name is None: full_name = modname
        else: full_name = f'{parent_name}.{modname}'
        assert mod.full_name == full_name
        assert mod is self.root.all_objects[full_name]

    def add_module(self, path: Path) -> None:
        """
        Add a module or package from a system path. 
        If the path is pointing to a directory, 
        reccursively add all submodules.
        """
        if path in self._added_paths:
            return
        if path.is_dir():
            if not (path / '__init__.py').is_file():
                raise RuntimeError(f"Source directory lacks __init__.py: {path}. The builder do not currently support namespace packages.")
            self._add_package(path)
        elif path.is_file():
            self._maybe_add_module(path)
        elif path.exists():
            raise RuntimeError(f"Source path is neither file nor directory: {path}")
        else:
            raise RuntimeError(f"Source path does not exist: {path}")
        self._added_paths.add(path)
    
    def _add_package(self, path: Path, parent: Optional[_model.Module]=None) -> None:
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
    
    def _maybe_add_module(self, path: Path, parent: Optional[_model.Module]=None) -> None:
        """
        Ignores the files that are not recognized as python files.
        """
        name = path.name
        for suffix in importlib.machinery.all_suffixes():
            if not name.endswith(suffix):
                continue
            module_name = name[:-len(suffix)]
            if suffix in importlib.machinery.EXTENSION_SUFFIXES:
                # builtin support for introspection on C extensions.
                if self.introspect_c_modules:
                    # we import it right now
                    if parent is None:
                        module_full_name = module_name
                    else:
                        module_full_name = f'{parent.full_name}.{module_name}'
                    py_mod = introspect._import_module(path, module_full_name)
                    self._add_module(path, module_name, parent, 
                                     is_c_module=True, py_mod=py_mod)
                
            elif suffix in importlib.machinery.SOURCE_SUFFIXES:
                self._add_module(path, module_name, parent)
            break
    
    def _discard_duplicate_mod(self, mod: _model.Module) -> Optional[_model.Module]:
        """
        Runs before adding a new module to the root. 
        Check if a module already has the same name. 

        :Returns: `None` if the process of adding this new module should continue normally.
        :Returns: The older module (already present) if the new module has been discarded.
            This should stop the new module from beeing added, it's a duplicate module.
        :Note: The rule is that the package/directory wins over the regular module, also, c-modules wins over regular modules.
        """
        # We check if that's a duplicate module name.
        is_dup = self.processing_map.get(mod.full_name) is not None
        
        if is_dup:

            # It's kindda safe to assume the modules contents have not been loaded yet,
            # so modules should not be shadowed by other objects (yet).
            older_mod = self.root.all_objects.get(mod.full_name)
            assert isinstance(older_mod, _model.Module) #type:ignore[unreachable]
            
            _warn_str = f"Duplicate module: '{mod.full_name}'." #type:ignore[unreachable]
            #  the package/directory wins
            if (older_mod.is_c_module and not mod.is_package) or \
               (older_mod.is_package and not mod.is_package):
                # C-modules wins, Packages wins
                mod.warn(_warn_str)
                del mod
                return older_mod
                # The package wins, we remove the older module from the tree and we continue with the 
                # addition of the package.
                # When importing the package, Python searches through the directories on sys.path looking for the package subdirectory.
            
            else:
                # Else, the last added module wins
                older_mod.warn(_warn_str)
                older_mod.remove()
                del older_mod
        return None

    def _add_module(self,
            path: Union[Path, str],
            modname: str,
            parent: Optional[_model.Module],
            is_package: bool = False,
            is_c_module: bool = False,
            py_mod: Optional[types.ModuleType] = None,
            py_string: Optional[str] = None,
            ) -> _model.Module: 
        """
        Create a new empty module and add it to the tree. 
        Initiate it's state in the AST processing map.

        :Parameters:
            path
                path where we can find the module file(s).
            modname
                the name of the new module (local name, not qname).
            parent
                the parent package, if any.
            is_package
                whether this module is a package.
            is_c_module
                whether this module is c extension.
            py_mod
                the live module, usually `None` because it parses 
                the source code file instead.
            py_string
                the module's string, usually `None` because it directly 
                gets the AST from the file path. 
                This is used when calling add_module_string().
        """
        location = self.root.factory.Location(filename=str(path), lineno=0)
        path = Path(path) if isinstance(path, str) else path

        mod = self.root.factory.Module(
            name=modname, 
            location=location, 
            docstring=None, 
            members=[], 
            source_path=path,
            is_package=is_package, 
            is_c_module=is_c_module,
            _py_mod=py_mod,
            _py_string=py_string)
        
        if not self._discard_duplicate_mod(mod):
            # add it to tree
            self.root.add_object(mod, parent=parent)
            # init state in processing map
            self.processing_map[mod.full_name] = ProcessingState.UNPROCESSED

        return mod

    def _process_module(self, mod:_model.Module) -> None:
        """
        Parse the module file to an AST and create it's members. At the time this method is called, not all objects are created. 
        But all module instances already exist and are added to `root.all_objects`, including nested modules.
        """
        assert self.processing_map[mod.full_name] is ProcessingState.UNPROCESSED, f"can't process twice the same module: {mod}"
        self.processing_map[mod.full_name] = ProcessingState.PROCESSING
        
        # TODO: we can easily set an option to enable fallback=True, 
        # this will import and introspect any installed module in module file is not found.

        if mod._py_mod is not None:
            # Modules created from live modules have a ._py_mod attribute.
            ast = astroid.manager.AstroidManager().ast_from_module(mod._py_mod, mod.full_name)
        elif mod._py_string is not None:
            # Modules created from string have a ._py_string attribute.
            ast = astroid.builder.AstroidManager().ast_from_string(mod._py_string, mod.full_name)
        elif mod.source_path is None:
            raise RuntimeError(f"Can't parse module {mod!r}, no 'source_path' defined.")
        else:
            ast = astroid.manager.AstroidManager().ast_from_file(mod.source_path.as_posix(), mod.full_name, fallback=False, source=True)
        
        # Set the AST node
        mod._ast = ast
        # Process the module
        self._processing_mod_stack.append(mod)
        self._process_module_ast(ast, mod)
        head = self._processing_mod_stack.pop()
        assert head is mod
        
        self.processing_map[mod.full_name] = ProcessingState.PROCESSED

    def build_modules(self) -> None:
        """
        Drives the building, builds modules until
        there is no unprocessed modules anymore. 

        Runs post-build operations after.
        """
        while list(self.unprocessed_modules):
            mod = next(self.unprocessed_modules)
            self._process_module(mod)
        self._post_build()

    def _post_build(self) -> None:
        self.pprocessor.post_build(self.root)
        
    def get_processed_module(self, modname: str, raise_on_cycles: bool = False) -> Optional[_model.Module]:
        """
        Returns the processed or processing (in case of cylces) module or None 
        if the name cannot be found.
        """
        mod = self.root.all_objects.get(modname)
        
        if mod is None: return None
        if not isinstance(mod, _model.Module): #type:ignore[unreachable]
            return None
                
        if self.processing_map.get(mod.full_name) is ProcessingState.UNPROCESSED: #type:ignore[unreachable]
            self._process_module(mod)
            assert self.processing_map[mod.full_name] in (ProcessingState.PROCESSING, ProcessingState.PROCESSED)
        
        if self.processing_map.get(mod.full_name) is ProcessingState.PROCESSING and raise_on_cycles:
            raise CyclicImport(f"Cyclic import processing module {mod.full_name!r}", mod)
        
        return mod

    
