"""
Helpers to help the helpers.
"""

from typing import Optional, Sequence, Union

import astroid.nodes
import pydocspec
from pydocspec import astroidutils, _model

def ast2apiobject(root: _model.TreeRoot, node: Union['astroid.nodes.ClassDef', 
                                        'astroid.nodes.Module']) -> Optional[Union['pydocspec.Class', 'pydocspec.Module']]:
    """implementation is duplicate safe."""
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
# to be added to the TreeRoot instance and the correctness of the result depends on the availbility of the targeted object
# in the system. So, recap, it's not recommended to use the naming system in the builder, 
# BUT when resolving import names, there is good chance that the indirection is already created, so it's ok.

def is_using_typing_final(expr: Optional[astroid.nodes.NodeNG], 
                    ctx:pydocspec.ApiObject) -> bool:
    return is_using_annotations(expr, ("typing.Final", "typing_extensions.Final"), ctx)

def is_using_typing_classvar(expr: Optional[astroid.nodes.NodeNG], 
                    ctx:pydocspec.ApiObject) -> bool:
    return is_using_annotations(expr, ('typing.ClassVar', "typing_extensions.ClassVar"), ctx)

def is_using_annotations(expr: Optional[astroid.nodes.NodeNG], 
                            annotations:Sequence[str], 
                            ctx:pydocspec.ApiObject) -> bool:
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

TYPING_ALIAS = (
        "typing.Hashable",
        "typing.Awaitable",
        "typing.Coroutine",
        "typing.AsyncIterable",
        "typing.AsyncIterator",
        "typing.Iterable",
        "typing.Iterator",
        "typing.Reversible",
        "typing.Sized",
        "typing.Container",
        "typing.Collection",
        "typing.Callable",
        "typing.AbstractSet",
        "typing.MutableSet",
        "typing.Mapping",
        "typing.MutableMapping",
        "typing.Sequence",
        "typing.MutableSequence",
        "typing.ByteString",
        "typing.Tuple",
        "typing.List",
        "typing.Deque",
        "typing.Set",
        "typing.FrozenSet",
        "typing.MappingView",
        "typing.KeysView",
        "typing.ItemsView",
        "typing.ValuesView",
        "typing.ContextManager",
        "typing.AsyncContextManager",
        "typing.Dict",
        "typing.DefaultDict",
        "typing.OrderedDict",
        "typing.Counter",
        "typing.ChainMap",
        "typing.Generator",
        "typing.AsyncGenerator",
        "typing.Type",
        "typing.Pattern",
        "typing.Match",
        # Special forms
        "typing.Final",
        "typing.Union",
        "typing.Literal",
        "typing.Optional",
    )

SUBSCRIPTABLE_CLASSES_PEP585 = (
        "tuple",
        "list",
        "dict",
        "set",
        "frozenset",
        "type",
        "collections.deque",
        "collections.defaultdict",
        "collections.OrderedDict",
        "collections.Counter",
        "collections.ChainMap",
        "collections.abc.Awaitable",
        "collections.abc.Coroutine",
        "collections.abc.AsyncIterable",
        "collections.abc.AsyncIterator",
        "collections.abc.AsyncGenerator",
        "collections.abc.Iterable",
        "collections.abc.Iterator",
        "collections.abc.Generator",
        "collections.abc.Reversible",
        "collections.abc.Container",
        "collections.abc.Collection",
        "collections.abc.Callable",
        "collections.abc.Set",
        "collections.abc.MutableSet",
        "collections.abc.Mapping",
        "collections.abc.MutableMapping",
        "collections.abc.Sequence",
        "collections.abc.MutableSequence",
        "collections.abc.ByteString",
        "collections.abc.MappingView",
        "collections.abc.KeysView",
        "collections.abc.ItemsView",
        "collections.abc.ValuesView",
        "contextlib.AbstractContextManager",
        "contextlib.AbstractAsyncContextManager",
        "re.Pattern",
        "re.Match",
    )

def is_typing_annotation(node: astroid.nodes.NodeNG, ctx: 'pydocspec.ApiObject') -> bool:
    """
    Whether this annotation node refers to a typing alias.
    """
    return is_using_annotations(node, TYPING_ALIAS, ctx) or \
            is_using_annotations(node, SUBSCRIPTABLE_CLASSES_PEP585, ctx)
