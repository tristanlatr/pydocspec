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
from pydocspec.ext import AstVisitorExt, PydocspecExtension

# this could be done in post-processing
def _handleOldSchoolMethodDecoration(self:AstVisitorExt, target: str, expr: Optional[astroid.nodes.NodeNG]) -> bool:
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

extension = PydocspecExtension(
    mixins=(),
    visitors=(),
)