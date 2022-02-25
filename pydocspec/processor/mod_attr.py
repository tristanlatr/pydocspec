"""
Helpers to populate attributes of `Module` instances. 
"""

from typing import Any, List, Optional
import astroid.nodes
import astroid.exceptions
import astroid.helpers
import astroid.util
from pydocspec import _model, astroidutils, visitors
    

def dunder_all(ob: _model.Module) -> Optional[List[str]]:
    var = ob.get_member('__all__')
    if not var or not isinstance(var, _model.Data) or not var.value_ast:
        return None
    value = var.value_ast
    
    if ob._ast is not None:
        # Infer the __all__ variable with astroid inference system.
        ivalue = list(ob._ast.igetattr("__all__"))[-1] # Do best effort inference.
        if ivalue != astroid.util.Uninferable:
            assert isinstance(ivalue, astroid.nodes.NodeNG)
            value = ivalue
        else:
            var.warn(f'Can\'t infer the value assigned to "{var.full_name}", too complex.')
            return None
    
    if not isinstance(value, (astroid.nodes.List, astroid.nodes.Tuple)):
        var.warn(f'Cannot parse value assigned to "{var.full_name}", must be a list or tuple.')
        return None

    names = []
    for idx, item in enumerate(value.elts):
        try:
            name: object = astroidutils.literal_eval(item)
        except ValueError:
            var.warn(f'Cannot parse element {idx} of "{var.full_name}"')
        else:
            if isinstance(name, str):
                names.append(name)
            else:
                var.warn(f'Element {idx} of "{var.full_name}" has '
                    f'type "{type(name).__name__}", expected "str"')
    
    # infer list operations
    if ob._ast is not None:
        Infer__all__Operations(names, mod=ob).walk(ob._ast)

    return names

class Infer__all__Operations(visitors.AstVisitor):
    """
    Walks the module level ast tree and infer list operations results to ``self.names``. 
    """

    SUPPORTED_OPS = set(('append', 'extend', 'remove'))

    def __init__(self, names: List[str], mod: _model.Module) -> None:
        super().__init__(extensions=None)
        self.names = names
        self.mod = mod

    # Ignore operations inside functions and classes
    def visit_functiondef(self, node: Any) -> None:
        raise self.SkipNode()
    def visit_asyncfunctiondef(self, node: Any) -> None:
        raise self.SkipNode()
    def visit_classdef(self, node: Any) -> None:
        raise self.SkipNode()
    
    def visit_call(self, node: astroid.nodes.Call) -> None:
        
        call_func = astroidutils.node2dottedname(node.func, strict=True)
        
        if not call_func or len(call_func) != 2 or call_func[0] != '__all__':
            # Not a call to __all__.something()
            return
        
        meth = call_func[1]
        if meth not in self.SUPPORTED_OPS :
            self.mod.warn(f"Can't infer result of call to '__all__.{meth}()'.", 
                          lineno_offset=node.lineno)
            return
        
        # All supported operations only take one positional argument 
        # so we don't need to validate args with astroidutils.bind_args()
        if len(node.args)!=1:
            self.mod.warn(f"Invalid call to '__all__.{meth}()'.", 
                          lineno_offset=node.lineno)
            return

        # Infer argument value
        ivalue = node.args[0].inferred()[-1] # Best effort inference.
        if ivalue in (astroid.util.Uninferable, None):
            self.mod.warn(f"Can't infer '__all__.{meth}()' argument value.", 
                          lineno_offset=node.lineno)
            return
        
        try:
            value = astroidutils.literal_eval(ivalue)
        except ValueError as e:
            self.mod.warn(f"Can't infer '__all__.{meth}()' argument value. {e}", 
                          lineno_offset=node.lineno)
            return

        if meth == 'append':
            if not isinstance(value, (str,)):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be a string, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            self.names.append(value)
        elif meth == 'extend':
            if not hasattr(value, '__iter__'):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be an iterable, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            for i, name in enumerate(value):
                if not isinstance(name, str):
                    self.mod.warn(f"Element {i} of the iterable passed to '__all__.{meth}()' has an invalid type, should be a string, not {name!r}.", 
                          lineno_offset=node.lineno)
                    continue
                self.names.append(name)
        elif meth == 'remove':
            if not isinstance(value, (str,)):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be a string, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            try:
                self.names.remove(value)
            except ValueError:
                self.mod.warn(f"Argument passed to '__all__.{meth}()' is invalid, {value!r} is not present in __all__.", 
                          lineno_offset=node.lineno)
                return

def docformat(ob: _model.Module) -> Optional[str]:
    var = ob.get_member('__docformat__')
    if not var or not isinstance(var, _model.Data) or not var.value_ast:
        return None
    #TODO: use astroid infer()
    try:
        value = astroidutils.literal_eval(var.value_ast)
    except ValueError:
        var.warn('Cannot parse value assigned to "__docformat__": not a string')
        return None
    
    if not isinstance(value, str):
        var.warn('Cannot parse value assigned to "__docformat__": not a string')
        return None
        
    if not value.strip():
        var.warn('Cannot parse value assigned to "__docformat__": empty value')
        return None
    
    return value


def is_package(ob: _model.Module) -> bool:

    return ob.is_package or any(isinstance(o, _model.Module) for o in ob.members)


def public_names(ob: _model.Module) -> List[str]:
    """
    A name is public if it does not start by an underscore. 
    Submodules are not imported when wildcard importing a module, 
    so they are not listed as part of the public names. 

    :note: This is used to resolve wildcard imports when no `__all__` variable is
        defined.
    """
    return list(dict.fromkeys([name for name in (m.name for m in ob.members if \
        not ((isinstance(m, _model.Indirection) and m.is_type_guarged) \
            or isinstance(m, _model.Module)) )
            if not name.startswith('_')]))
    
    # Maybe the following rationale is better:
    # Even if submodules are not imported when wildcard importing a module, 
    # this returns submodules as part of the public names anyway. 