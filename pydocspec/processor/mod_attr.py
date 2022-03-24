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
        ivalue = list(ob._ast.igetattr("__all__"))[-1] # Last assignment inference.
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

    return names

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