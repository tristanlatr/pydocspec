
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
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Iterable, Iterator, List, Dict, Optional, Sequence, Set, Tuple, Union, cast
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
import attr

# Implementation note: 
# The builder should not import pydocspec, it should not be aware of pydocspec.* classes

from pydocspec import (_model, astroidutils, introspect, processor, 
                       basebuilder, genericvisitor, 
                       dottedname, visitors)

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

class ModuleVisitor(astroidutils.NodeVisitor, basebuilder.Collector):
    # help mypy
    module: _model.Module
    
    def __init__(self, builder: 'Builder', module: _model.Module) -> None:
        super().__init__(builder.root, module)
        self.builder = builder
    
    def default(self, node: astroid.nodes.NodeNG) -> None:
        """
        Visit the nested nodes in the body of a node.
        """
        body: Optional[Sequence[astroid.nodes.NodeNG]] = getattr(node, 'body', None)
        if body is not None:
            for child in body:
                self.visit(child)
    
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
        
        ob.docstring = cast('docspec.Docstring', self.root.factory.Docstring(docstring, 
            self.root.factory.Location(None, lineno=docstring_lineno)))
    
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
        if isinstance(value, astroid.nodes.Const) and value.pytype() == 'str':
            attr = self.last
            if isinstance(attr, _model.Data) and attr.parent is self.current:
                self._set_docstring(attr, value)

        self.generic_visit(node)

    ### MODULE ###

    def visit_Module(self, node: astroid.nodes.Module) -> None:
        """
        Visit an {astroid.nodes.Module}.
        """

        # unprocessed modules should not have been initialized with a docstring yet.
        # assert self.module.docstring is None

        if len(node.body) > 0 and isinstance(node.body[0], astroid.nodes.Expr) and \
            isinstance(node.body[0].value, astroid.nodes.Const) and node.body[0].value.pytype() == 'str':
            # setting the module docstring
            self._set_docstring(self.module, node.body[0].value)

        # Set the AST node
        self.module._ast = node

        self.add_object(self.module)
    
        self.default(node)

        # The processing of the __all__ variable should go there since it's used in _import_all()
        # TODO: move this where we created the Data object
        self.module.dunder_all = processor._module_helpers.dunder_all(self.module)

        self.pop(self.module)
    
    ### CLASSES ###

    def visit_ClassDef(self, node: astroid.nodes.ClassDef) -> None:
        """
        Visit a class. 
        """
        # Ignore classes within functions.
        if isinstance(self.current, _model.Function):
            return None

        bases_str: Optional[List[str]] = None
        bases_ast: Optional[List[astroid.nodes.NodeNG]] = None

        if node.bases:
            bases_str = []
            bases_ast = []

        # compute the Class.bases attribute
        for n in node.bases:
            str_base = n.as_string()
            assert isinstance(bases_str, list)
            assert isinstance(bases_ast, list)
            bases_str.append(str_base)
            bases_ast.append(n)

        lineno = node.lineno

        # If a class is decorated, set the linenumber from the line of the first decoration.
        
        decorators = node.decorators.nodes if node.decorators else None
        
        if decorators:
            lineno = decorators[0].lineno

        # create new class
        cls: _model.Class = self.root.factory.Class(node.name, 
                                    location=self.root.factory.Location(None, lineno=lineno),
                                    docstring=None, metaclass=None, 
                                    bases=bases_str, 
                                    bases_ast=bases_ast,
                                    decorations=None, 
                                    members=[], 
                                    is_type_guarged=astroidutils.is_type_guarded(node, self.current), 
                                    _ast=node, )

        # set docstring
        if len(node.body) > 0 and isinstance(node.body[0], astroid.nodes.Expr) and isinstance(node.body[0].value, astroid.nodes.Const):
            self._set_docstring(cls, node.body[0].value)

        # set decorations
        if decorators:
            cls.decorations = []
            for decnode in decorators:

                # compute decoration attributes
                name_ast: astroid.nodes.NodeNG
                name: str
                args_ast: Optional[List[astroid.nodes.NodeNG]]
                args: Optional[List[str]]

                if isinstance(decnode, astroid.nodes.Call):
                    name_ast = decnode.func
                    dotted_name = astroidutils.node2dottedname(name_ast)
                    args_ast = decnode.args
                    args = []
                else:
                    name_ast = decnode
                    dotted_name = astroidutils.node2dottedname(name_ast)
                    args_ast = args = None
                
                if dotted_name is None:
                    name = astroidutils.to_source(name_ast)

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
                deco.expr_ast = decnode
                
                cls.decorations.append(deco)
        
        self.add_object(cls)
        self.default(node)
        self.pop(cls)

    ### IMPORTS ###

    def visit_ImportFrom(self, node: astroid.nodes.ImportFrom) -> None:
        ctx = self.current
        if not isinstance(ctx, _model.HasMembers):
            assert ctx is not None, "processing import statement with no current context: {node!r}"
            ctx.module.warn("processing import statement ({node!r}) in odd context: {ctx!r}",
                            lineno_offset=node.lineno)
            return

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
            for i in self._import_all(modname, lineno=node.lineno, 
                                      is_type_guarged=is_type_guarged):
                self.add_object(i, push=False)
        else:
            for i in self._import_names(modname, node.names, lineno=node.lineno, 
                                        is_type_guarged=is_type_guarged):
                self.add_object(i, push=False)

    def _import_all(self, modname: str, lineno: int, 
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
                processor._module_helpers.public_names(from_module))

        # Add imported names to our module namespace.
        assert isinstance(self.current, _model.HasMembers)
        
        yield from self._import_names(modname, 
            [(n, None) for n in names], 
            lineno, is_type_guarged)

    def _import_names(self, modname: str, names: Iterable[Tuple[str, Optional[str]]], lineno: int, 
                      is_type_guarged:bool) -> Iterator[_model.Indirection]:
        """Handle a C{from <modname> import <names>} statement."""

        for al in names:
            orgname, asname = al[0], al[1]
            if asname is None:
                asname = orgname

            indirection = self.root.factory.Indirection(name=asname, 
                location=self.root.factory.Location(filename=None, lineno=lineno), docstring=None, 
                target=f'{modname}.{orgname}', is_type_guarged=is_type_guarged)
            
            yield indirection

    def visit_Import(self, node: astroid.nodes.Import) -> None:
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
        
        for al in node.names:
            fullname, asname = al[0], al[1]
            if asname is not None:
                indirection = self.root.factory.Indirection(name=asname, 
                    location=self.root.factory.Location(filename=None, lineno=node.lineno), docstring=None, 
                    target=fullname, is_type_guarged=astroidutils.is_type_guarded(node, ctx))
                self.add_object(indirection, push=False)
            # Do not create an indirection with the same name and target, this is pointless and it will
            # make the ApiObject._resolve_indirection() method reccurse one time more than needed.

    # TODO: Code the rest of it!

    ### ATTRIBUTES ###

    # def visit_Assign(self, node: astroid.nodes.Assign) -> None:
    #     lineno = node.lineno
    #     expr = node.value

    #     type_comment: Optional[str] = getattr(node, 'type_comment', None)
    #     if type_comment is None:
    #         annotation = None
    #     else:
    #         annotation = astroidutils.unstring_annotation(astroid.nodes.Const(type_comment, lineno=lineno))

    #     for target in node.targets:
    #         if isinstance(target, astroid.nodes.Tuple):
    #             for elem in target.elts:
    #                 # Note: We skip type and aliasing analysis for this case, (why?)
    #                 #       but we do record line numbers.
    #                 self._handleAssignment(elem, None, None, lineno)
    #         else:
    #             self._handleAssignment(target, annotation, expr, lineno)

    # def visit_AnnAssign(self, node: astroid.nodes.AnnAssign) -> None:
    #     annotation = astroidutils.unstring_annotation(node.annotation)
    #     self._handleAssignment(node.target, annotation, node.value, node.lineno)
    
    # def _handleAssignment(self,
    #         target_node: astroid.nodes.NodeNG,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     if isinstance(target_node, astroid.nodes.Name):
    #         target = target_node.name
    #         scope = self.current
    #         if isinstance(scope, _model.Module):
    #             self._handleAssignmentInModule(target, annotation, expr, lineno)
    #         elif isinstance(scope, _model.Class):
    #             # if not self._handleOldSchoolMethodDecoration(target, expr):
    #             self._handleAssignmentInClass(target, annotation, expr, lineno)
    #     elif isinstance(target_node, astroid.nodes.Attribute):
    #         value = target_node.expr
    #         if target_node.attr == '__doc__':
    #             self._handleDocstringUpdate(value, expr, lineno)
    #         elif isinstance(value, astroid.nodes.Name) and value.id == 'self':
    #             self._handleInstanceVar(target_node.attr, annotation, expr, lineno)
    #         # TODO: Fix https://github.com/twisted/pydoctor/issues/13
    
    # # this could be done in post-processing
    # # def _handleOldSchoolMethodDecoration(self, target: str, expr: Optional[astroid.nodes.NodeNG]) -> bool:
    # #     #TODO: handle property()

    # #     if not isinstance(expr, astroid.nodes.Call):
    # #         return False
    # #     func = expr.func
    # #     if not isinstance(func, astroid.nodes.Name):
    # #         return False
    # #     func_name = func.name
    # #     args = expr.args
    # #     if len(args) != 1:
    # #         return False
    # #     arg, = args
    # #     if not isinstance(arg, astroid.nodes.Name):
    # #         return False
    # #     if target == arg.name and func_name in ['staticmethod', 'classmethod']:
    # #         target_obj = self.current.get_member(target)
    # #         if isinstance(target_obj, _model.Function):

    # #             # _handleOldSchoolMethodDecoration must only be called in a class scope.
    # #             assert isinstance(target_obj.parent, _model.Class)

    # #             if func_name == 'staticmethod':
    # #                 target_obj.is_staticmethod = True

    # #             elif func_name == 'classmethod':
    # #                 target_obj.is_classmethod = True
    # #             return True
    # #     return False
    
    # def _warnsConstantAssigmentOverride(self, obj: _model.Data, lineno_offset: int) -> None:
    #     obj.report(f'Assignment to constant "{obj.name}" overrides previous assignment '
    #                 f'at line {obj.location.lineno}, the original value will not be part of the docs.', 
    #                         section='ast', lineno_offset=lineno_offset)
                            
    # def _warnsConstantReAssigmentInInstance(self, obj: _model.Data, lineno_offset: int = 0) -> None:
    #     obj.report(f'Assignment to constant "{obj.name}" inside an instance is ignored, this value will not be part of the docs.', 
    #                     section='ast', lineno_offset=lineno_offset)

    # def _handleConstant(self, obj: _model.Data, value: Optional[astroid.nodes.NodeNG], lineno: int) -> None:
        
    #     if is_attribute_overridden(obj, value):
            
    #         if obj.is_constant or obj.is_class_variable or obj.is_module_variable:
    #             # Module/Class level warning, regular override.
    #             self._warnsConstantAssigmentOverride(obj=obj, lineno_offset=lineno-obj.location.lineno)
    #         else:
    #             # Instance level warning caught at the time of the constant detection.
    #             self._warnsConstantReAssigmentInInstance(obj)

    #     obj.value_ast = value
        
    #     obj.is_constant = True

    #     # A hack to to display variables annotated with Final with the real type instead.
    #     if obj.is_using_typing_final:
    #         if isinstance(obj.datatype_ast, astroid.nodes.Subscript):
    #             try:
    #                 annotation = astroidutils.extract_final_subscript(obj.datatype_ast)
    #             except ValueError as e:
    #                 obj.warn(str(e), lineno_offset=lineno-obj.location.lineno)
    #                 obj.datatype_ast = astroidutils.infer_type(value) if value else None
    #             else:
    #                 # Will not display as "Final[str]" but rather only "str"
    #                 obj.datatype_ast = annotation
    #         else:
    #             # Just plain "Final" annotation.
    #             # Simply ignore it because it's duplication of information.
    #             obj.datatype_ast = astroidutils.infer_type(value) if value else None
    
    # def _handleAlias(self, obj: _model.Data, value: Optional[astroid.nodes.NodeNG], lineno: int) -> None:
    #     """
    #     Must be called after obj.setLineNumber() to have the right line number in the warning.

    #     Create an alias or update an alias.
    #     """
        
    #     if is_attribute_overridden(obj, value) and astroidutils.is_alias(obj.value_ast):
    #         obj.report(f'Assignment to alias "{obj.name}" overrides previous alias '
    #                 f'at line {obj.location.lineno}.', 
    #                         section='ast', lineno_offset=lineno-obj.location.lineno)

    #     obj.kind = model.DocumentableKind.ALIAS
    #     # This will be used for HTML repr of the alias.
    #     obj.value = value
    #     dottedname = node2dottedname(value)
    #     # It cannot be None, because we call _handleAlias() only if is_alias() is True.
    #     assert dottedname is not None
    #     name = '.'.join(dottedname)
    #     # Store the alias value as string now, this avoids doing it in _resolveAlias().
    #     obj._alias_to = name


    # def _handleModuleVar(self,
    #         target: str,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     if target in MODULE_VARIABLES_META_PARSERS:
    #         # This is metadata, not a variable that needs to be documented,
    #         # and therefore doesn't need an Attribute instance.
    #         return
    #     parent = self.builder.current
    #     obj = parent.resolveName(target)
        
    #     if obj is None:
    #         obj = self.builder.addAttribute(name=target, kind=None, parent=parent)
        
    #     if isinstance(obj, _model.Data):
            
    #         if annotation is None and expr is not None:
    #             annotation = astroidutils.infer_type(expr)
            
    #         obj.annotation = annotation
    #         obj.setLineNumber(lineno)
    #         if is_alias(expr):
    #             self._handleAlias(obj=obj, value=expr, lineno=lineno)
    #         elif is_constant(obj):
    #             self._handleConstant(obj=obj, value=expr, lineno=lineno)
    #         else:
    #             obj.kind = model.DocumentableKind.VARIABLE
    #             # We store the expr value for all Attribute in order to be able to 
    #             # check if they have been initialized or not.
    #             obj.value = expr

    #         self.newAttr = obj

    # def _handleAssignmentInModule(self,
    #         target: str,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     module = self.builder.current
    #     assert isinstance(module, model.Module)
    #     self._handleModuleVar(target, annotation, expr, lineno)

    # def _handleClassVar(self,
    #         name: str,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     cls = self.builder.current
    #     assert isinstance(cls, model.Class)
    #     if not _maybeAttribute(cls, name):
    #         return
    #     obj: Optional[_model.Data] = cls.contents.get(name)
        
    #     if obj is None:
    #         obj = self.builder.addAttribute(name=name, kind=None, parent=cls)

    #     if obj.kind is None:
    #         instance = is_attrib(expr, cls) or (
    #             cls.auto_attribs and annotation is not None and not (
    #                 isinstance(annotation, astroid.nodes.Subscript) and
    #                 node2fullname(annotation.value, cls) == 'typing.ClassVar'
    #                 )
    #             )
    #         obj.kind = model.DocumentableKind.INSTANCE_VARIABLE if instance else model.DocumentableKind.CLASS_VARIABLE

    #     if expr is not None:
    #         if annotation is None:
    #             annotation = self._annotation_from_attrib(expr, cls)
    #         if annotation is None:
    #             annotation = astroidutils.infer_type(expr)
        
    #     obj.annotation = annotation
    #     obj.setLineNumber(lineno)

    #     if is_alias(expr):
    #         self._handleAlias(obj=obj, value=expr, lineno=lineno)
    #     elif is_constant(obj):
    #         self._handleConstant(obj=obj, value=expr, lineno=lineno)
    #     else:
    #         obj.value = expr

    #     self.newAttr = obj

    # def _handleInstanceVar(self,
    #         name: str,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     func = self.builder.current
    #     if not isinstance(func, model.Function):
    #         return
    #     cls = func.parent
    #     if not isinstance(cls, model.Class):
    #         return
    #     if not _maybeAttribute(cls, name):
    #         return

    #     obj = cls.contents.get(name)
    #     if obj is None:
    #         obj = self.builder.addAttribute(name=name, kind=None, parent=cls)

    #     if annotation is None and expr is not None:
    #         annotation = astroidutils.infer_type(expr)
        
    #     obj.annotation = annotation
    #     obj.setLineNumber(lineno)

    #     # Maybe an instance variable overrides a constant, 
    #     # so we check before setting the kind to INSTANCE_VARIABLE.
    #     if obj.kind is _model.DocumentableKind.CONSTANT:
    #         self._warnsConstantReAssigmentInInstance(obj, lineno_offset=lineno-obj.location.lineno)
    #     else:
    #         obj.kind = _model.DocumentableKind.INSTANCE_VARIABLE
    #         obj.value = expr
    #     self.newAttr = obj

    # def _handleAssignmentInClass(self,
    #         target: str,
    #         annotation: Optional[astroid.nodes.NodeNG],
    #         expr: Optional[astroid.nodes.NodeNG],
    #         lineno: int
    #         ) -> None:
    #     cls = self.current
    #     assert isinstance(cls, _model.Class)
    #     self._handleClassVar(target, annotation, expr, lineno)

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
    #     scope = self.builder.current
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

    root: _model.TreeRoot
    options: Any = None

    _added_paths: Set[Path] = attr.ib(factory=set)
    # Duplication of names in the modules is not supported.
    # This is a problem for Python too, the rule is that the folder/package wins.
    # Though, duplication in other objects is supported.
    processing_map: Dict[str, ProcessingState] = attr.ib(factory=dict, init=False)
    """Mapping from module's full_name to the processing state"""
    _processing_mod_stack: List[_model.Module] = attr.ib(factory=list)
    
    ModuleVisitor = ModuleVisitor
    
    def _process_module_ast(self, mod_ast: astroid.nodes.Module, mod: _model.Module) -> None:
        builder_visitor = self.ModuleVisitor(self, mod)
        builder_visitor.visit(mod_ast)

    @property
    def unprocessed_modules(self) -> Iterator[_model.Module]:
        for mod_name, state in self.processing_map.items():
            if state is ProcessingState.UNPROCESSED:
                
                mods = self.root.all_objects.getall(mod_name)
                assert mods is not None, "Cannot find module '{mod_name}' in {root.all_objects!r}."
                
                for mod in mods:
                    # Support that function/class overrides a module name, but still process the module ;-)
                    #TODO: test this.

                    # This returns the firstly added object macthing the name, and it must be a module. 
                    assert isinstance(mod, _model.Module)
                    yield mod
                    break
                else:
                    raise RuntimeError(f"No module found for name '{mod_name}', though it appears in the processing map: {self.processing_map!r}.")

    def add_module(self, path: Path) -> None:
        """
        Add a module or package from a system path. If the path is pointing to a directory, reccursively add all submodules.
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
    
    def _introspect_module(self, path:Path, module_name:str, parent: Optional[_model.Module]) -> None:
        introspect.introspect_module(self.root,
                        path, module_name, parent)
    
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
                # support for introspection on C extensions.
                if getattr(self.options, 'introspect_c_modules', None):
                    self._introspect_module(path, module_name, parent)
            elif suffix in importlib.machinery.SOURCE_SUFFIXES:
                self._add_module(path, module_name, parent)
            break
    
    def _add_module(self,
            path: Union[Path, str],
            modname: str,
            parent: Optional[_model.Module],
            is_package: bool = False
            ) -> _model.Module: 
        """
        Create a new empty module and add it to the tree. 
        Initiate it's state in the AST processing map.
        """
        location = self.root.factory.Location(filename=str(path), lineno=0)
        mod = self.root.factory.Module(name=modname, location=location, docstring=None, members=[])

        # We check if that's a duplicate module name.
        older_mod = self.root.all_objects.get(mod.full_name)
        if older_mod:
            assert isinstance(older_mod, _model.Module)

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
        # add to tree
        self.root.add_object(mod, parent=parent)
        # init state
        self.processing_map[mod.full_name] = ProcessingState.UNPROCESSED
        # set source_path for modules
        mod.source_path = Path(path) if isinstance(path, str) else path
        return mod

    def _process_module(self, mod:_model.Module) -> None:
        """
        Parse the module file to an AST and create it's members. At the time this method is called, not all objects are created. 
        But all module instances already exist and are added to `root.all_objects`, including nested modules.
        """
        assert self.processing_map[mod.full_name] is ProcessingState.UNPROCESSED, f"can't process twice the same module: {mod}"
        self.processing_map[mod.full_name] = ProcessingState.PROCESSING
        
        path = mod.source_path
        if path is None:
            #TODO: we should warn here, source path can be none on objects created from introspection. 
            return #type:ignore[unreachable]
        
        ast = astroid.builder.AstroidBuilder().file_build(path, mod.full_name)
        
        if ast:
            self._processing_mod_stack.append(mod)
            self._process_module_ast(ast, mod)
            head = self._processing_mod_stack.pop()
            assert head is mod
        
        self.processing_map[mod.full_name] = ProcessingState.PROCESSED

    def process_modules(self) -> None:
        """
        Process unprocessed modules.
        """
        while list(self.unprocessed_modules):
            mod = next(self.unprocessed_modules)
            self._process_module(mod)
        
    def get_processed_module(self, modname: str, raise_on_cycles: bool = False) -> Optional[_model.Module]:
        """
        Returns the processed or processing (in case of cylces) module or None 
        if the name cannot be found.
        """
        mod = self.root.all_objects.get(modname)
        
        if mod is None: return None
        if not isinstance(mod, _model.Module): return None
                
        if self.processing_map.get(mod.full_name) is ProcessingState.UNPROCESSED:
            self._process_module(mod)
            assert self.processing_map[mod.full_name] in (ProcessingState.PROCESSING, ProcessingState.PROCESSED)
        
        if self.processing_map.get(mod.full_name) is ProcessingState.PROCESSING and raise_on_cycles:
            raise CyclicImport(f"Cyclic import processing module {mod.full_name!r}", mod)
        
        return mod

    
