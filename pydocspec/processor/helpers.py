"""
Helpers to help the helpers.
"""

from typing import Optional, Sequence, Union

import astroid.nodes
import pydocspec
from pydocspec import astroidutils

def ast2apiobject(root: pydocspec.TreeRoot, node: Union['astroid.nodes.ClassDef', 
                                        'astroid.nodes.Module']) -> Optional[Union['pydocspec.Class', 'pydocspec.Module']]:
    values = root.all_objects.getall(node.qname())
    if not values: 
        return None
    for sameloc in filter(
        lambda ob: ob.location is not None \
            and ob.location.lineno is not None \
                and ob.location.lineno==node.lineno, values):
        assert isinstance(sameloc, (pydocspec.Class, pydocspec.Module))
        return sameloc
    return None

# TODO: ctx here is not required since we could expand the annotation name with astutils.resolve_qualname()
# Even if requiring a pydocspec context object is unpratical (because the name resolving system needs the object
# to be added to the TreeRoot instance and the correctness of the result depends on the availbility of the targeter object
# in the system. So, recap, it's not recommended to use the naming system in the builder, 
# BUT whend resolving import names, there is good chance that the indirection is already created.

def is_using_typing_final(expr: Optional[astroid.nodes.NodeNG], 
                    ctx:Union[pydocspec.Class, pydocspec.Module]) -> bool:
    return is_using_annotations(expr, ("typing.Final", "typing_extensions.Final"), ctx)

def is_using_typing_classvar(expr: Optional[astroid.nodes.NodeNG], 
                    ctx:Union[pydocspec.Class, pydocspec.Module]) -> bool:
    return is_using_annotations(expr, ('typing.ClassVar', "typing_extensions.ClassVar"), ctx)

def is_using_annotations(expr: Optional[astroid.nodes.NodeNG], 
                            annotations:Sequence[str], 
                            ctx:Union[pydocspec.Class, pydocspec.Module]) -> bool:
    """
    Detect if this expr is firstly composed by one of the specified annotation(s)' full name.
    """
    full_name = astroidutils.node2fullname(expr, ctx)
    if full_name in annotations:
        return True
    if isinstance(expr, astroid.nodes.Subscript):
        # Final[...] or typing.Final[...] expressions
        if isinstance(expr.value, (astroid.nodes.Name, astroid.nodes.Attribute)):
            value = expr.value
            full_name = astroidutils.node2fullname(value, ctx)
            if full_name in annotations:
                return True
    return False