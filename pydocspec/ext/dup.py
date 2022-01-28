"""
Handles objects created with the same name as an object that already exisist.

Handles `classmethod()` and `staticmethod()` like::

    def f():
        ...
    f = staticmethod(f)

It removes the Data object and mark the Function f() as a static method.
"""
from typing import Optional
import astroid.nodes

import pydocspec
from pydocspec.ext import AstVisitorExt, ExtRegistrar

# this could be done in post-processing
def _handleOldSchoolMethodDecoration(self:AstVisitorExt, 
                                     target: str, 
                                     expr: Optional[astroid.nodes.NodeNG]) -> bool:
    #TODO: handle property()

    if not isinstance(expr, astroid.nodes.Call):
        return False
    func = expr.func
    if not isinstance(func, astroid.nodes.Name):
        return False
    func_name = func.name
    args = expr.args
    if len(args) != 1:
        return False
    arg, = args
    if not isinstance(arg, astroid.nodes.Name):
        return False
    if target == arg.name and func_name in ['staticmethod', 'classmethod']:
        target_obj = self.visitor.current.get_member(target)
        if isinstance(target_obj, pydocspec.Function):

            # _handleOldSchoolMethodDecoration must only be called in a class scope.
            assert isinstance(target_obj.parent, pydocspec.Class)

            if func_name == 'staticmethod':
                target_obj.is_staticmethod = True

            elif func_name == 'classmethod':
                target_obj.is_classmethod = True
            return True
    return False

    def _warnsConstantAssigmentOverride(self, obj: _model.Data, lineno_offset: int) -> None:
        obj.warn(f'Assignment to constant "{obj.name}" overrides previous assignment '
                    f'at line {obj.location.lineno}, the original value will not be part of the docs.', 
                            lineno_offset=lineno_offset)
                            
    def _warnsConstantReAssigmentInInstance(self, obj: _model.Data, lineno_offset: int = 0) -> None:
        obj.warn(f'Assignment to constant "{obj.name}" inside an instance is ignored, this value will not be part of the docs.', 
                        lineno_offset=lineno_offset)

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
    
    # post-processing
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

def setup_extension(r:ExtRegistrar) -> None:
    pass