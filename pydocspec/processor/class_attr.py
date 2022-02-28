"""
Helpers to populate attributes of `Class` instances. 
"""
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union, TYPE_CHECKING

import astroid.nodes
import astroid.exceptions
import pydocspec

from pydocspec import _model, _c3linear, astroidutils
from pydocspec.processor import func_attr, helpers

if TYPE_CHECKING:
    from typing_extensions import Literal

class MRO(_c3linear.GenericMRO[pydocspec.Class]):
    """
    Implements MRO resoling for `pydocspec.Class` instances.
    """
    def bases(self, cls: pydocspec.Class) -> List[pydocspec.Class]:
        return [b for b in cls.resolved_bases if isinstance(b, pydocspec.Class)]

def is_subclass_of(ob: pydocspec.Class, baseclasses: Sequence[Union[str, pydocspec.Class]]) -> bool:
    """
    Check if class ``ob`` is a subclass of any of the base classes in ``baseclasses``.
    :returns: `True` if ``ob`` is derived from any of the base classes. 
        `False` otherwise.
    """
    for base in ob.ancestors(True):
        if base in baseclasses:
            return True
    return False

# List of exceptions class names in the standard library, Python 3.8.10
EXCEPTIONS_CLASSES = ('ArithmeticError', 'AssertionError', 'AttributeError', 
    'BaseException', 'BlockingIOError', 'BrokenPipeError', 
    'BufferError', 'BytesWarning', 'ChildProcessError', 
    'ConnectionAbortedError', 'ConnectionError', 
    'ConnectionRefusedError', 'ConnectionResetError', 
    'DeprecationWarning', 'EOFError', 
    'EnvironmentError', 'Exception', 'FileExistsError', 
    'FileNotFoundError', 'FloatingPointError', 'FutureWarning', 
    'GeneratorExit', 'IOError', 'ImportError', 'ImportWarning', 
    'IndentationError', 'IndexError', 'InterruptedError', 
    'IsADirectoryError', 'KeyError', 'KeyboardInterrupt', 'LookupError', 
    'MemoryError', 'ModuleNotFoundError', 'NameError', 
    'NotADirectoryError', 'NotImplementedError', 
    'OSError', 'OverflowError', 'PendingDeprecationWarning', 'PermissionError', 
    'ProcessLookupError', 'RecursionError', 'ReferenceError', 
    'ResourceWarning', 'RuntimeError', 'RuntimeWarning', 'StopAsyncIteration', 
    'StopIteration', 'SyntaxError', 'SyntaxWarning', 'SystemError', 
    'SystemExit', 'TabError', 'TimeoutError', 'TypeError', 
    'UnboundLocalError', 'UnicodeDecodeError', 'UnicodeEncodeError', 
    'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning', 'UserWarning', 
    'ValueError', 'Warning', 'ZeroDivisionError')

def is_exception(ob: pydocspec.Class) -> bool: 
    """must be set after resolved_bases"""
    return is_subclass_of(ob, EXCEPTIONS_CLASSES)


def mro_from_astroid(ob: _model.Class) -> Union[List[pydocspec.Class], object]:
    """
    Compute MRO from astroid, this does not require `pydocspec.Class.resolved_bases`. 
    
    Returns NotImplemented if the tree has not been built with astroid. 
    """
    # this does not support objects loaded from other places than astroid, 
    # for instance coming from JSON data.
    # This is why we need to re-compute the MRO after.
    # But it does the job for the first iteration 
    # This should not rely on Class.resolved_bases, since resolved_bases relies 
    # on Class.find() which relies on Class.mro attribute.
    # The result from this function is used temporarly to compute the resolved_bases attribute
    # then .mro attribute is re-computed with mro() function below.
    def nodemro2classmro(node_mro: List[astroid.nodes.NodeNG]) -> List[pydocspec.Class]:
        mro_ = []
        for node in node_mro:
            superclass = helpers.ast2apiobject(ob.root, node)
            if superclass is not None:
                assert isinstance(superclass, pydocspec.Class)
                mro_.append(superclass)
        return mro_

    if ob._ast is None:
        # This is probably because the tree has been converted from docspec.
        # No issue we have support for that, too.
        # Return NotImplemented, and it will be taken care of in the later processing step.
        return NotImplemented
    try:
        node_mro = ob._ast.mro()
        return nodemro2classmro(node_mro)
        # return [o for o in (helpers.ast2apiobject(ob.root, node) for node in node_mro) if o] # type:ignore
    except astroid.exceptions.MroError:
        node_mro = [ob._ast] + list(ob._ast.ancestors())
        return nodemro2classmro(node_mro)
        # return [o for o in (helpers.ast2apiobject(ob.root, node) for node in node_mro) if o] # type:ignore

 # must be set after resolved_bases
def mro(ob: pydocspec.Class) -> List[pydocspec.Class]:
    """compute mro from apiobjects. must be set after resolved_bases"""
    try:
        try: 
            return MRO().mro(ob)
        except (ValueError,) as e:
            ob.warn(str(e))
            return list(
                filter(lambda ob: isinstance(ob, pydocspec.Class), ob.ancestors(True))) #type:ignore[arg-type]
    except RecursionError as e:
        # TODO: test recursions in base classes.
        raise RecursionError(f"Recursion error trying to resolve the MRO of class {ob.full_name!r}.")
        # f"The current MRO is: {' <- '.join(o.full_name for o in ob.mro)}") from e


# could also use this utility method from sphinx-autoapi resolve_qualname(ctx: NodeNG, name:str) -> str
# https://github.com/readthedocs/sphinx-autoapi/blob/71c6ceebe0b02c34027fcd3d56c8641e9b94c7af/autoapi/mappers/python/astroid_utils.py#L64
# resolve_qualname trips on inner classes! TODO: Fix this bug.
# resolve_qualname() is an alternative for expand_name() that is only based on astroid
# resolved = astroidutils.resolve_qualname(ob.scope._ast, base)
# resolved_obj = ob.root.all_objects.get(resolved)
# it looks like resolved_obj can be an Indirection + 
# need to create a separate function because it breaks the converter since ob.scope._ast is None for objects comming from the converter.
# if resolved_obj:
#     objs.append(resolved_obj)
# else:
#     objs.append(resolved)

def resolved_bases(ob: pydocspec.Class) -> List[Union['pydocspec.Class', 'str']]: 
    """direct bases of this class, if the name cannot be resolved as an apiobject, fallback to expanded name str.
    uses name resolution.
    """
    # Uses the name resolving feature, but the name resolving feature also depends on Class.find, wich depends on resolved_bases.
    # So this is a source of potentially subtle bugs in the name resolving when there is a base class that is actually defined 
    # in the base class of another class accessed with the subclass name.
    # Example (in this example, to be correct, the resolved_bases attr of the class Foo must be set before the class bar, leading
    # to inconsistencies due to the random order of the module processing. 
    # The situation gets even more complicated when there are cyclic imports):
    # mod1.py
    # class _Base:
    #   class barbase(str):
    #       ...
    # class Foo(_Base):
    #   ...
    # mod2.py
    # from . import mod1
    # class bar(mod1.Foo.barbase):
    #   ...
    # SOLUTION: Populate the Class.mro attribute from astroid first when possible.
    
    
    objs: List[Union['pydocspec.Class', 'str']] = []

    _workable_bases_as_string = []

    # use AST it should be set by the builder or converter!
    for node in ob.bases_ast or ():
        name = astroidutils.node2dottedname(node)
        if name:
            _workable_bases_as_string.append('.'.join(name))
        else:
            ob.warn(f"Could not understand base {node.as_string()!r}")

    for base in _workable_bases_as_string:
        
        expanded_name = ob.parent.expand_name(base)

        resolved = ob.root.all_objects.get(expanded_name)
        
        if resolved is not None:
            # only adds Class objects or str to the resolved_bases attribute.
            if isinstance(resolved, pydocspec.Class):
                if resolved==ob:
                    ob.warn(f"This object is the base of itself!")
                    #f"Name resolution: <{ob.parent.full_name}>.expand_name({base!r}) gave {expanded_name!r}.")

                else:
                    objs.append(resolved)
            else:
                objs.append(resolved.full_name)
                ob.warn(f"Can't find superclass {expanded_name!r} in the tree, some inherited members might be missing "
                        f"(though, found an {resolved.__class__.__name__} named {resolved.full_name!r}).")
        else:
            objs.append(expanded_name)
            ob.warn(f"Can't find superclass {expanded_name!r} in the tree, some inherited members might be missing.")
    
    return objs


def process_subclasses(ob: pydocspec.Class) -> None:
    """for all resolved_bases classes, add ob to the subclasses list"""
    for b in ob.resolved_bases:
        if isinstance(b, pydocspec.Class) and ob not in b.subclasses:
            b.subclasses.append(ob)

def constructor_method(ob: _model.Class) -> Optional['pydocspec.Function']:
    """returns the __init__ method, i'm a bit dummy."""
    init_method = ob.get_member('__init__')
    if isinstance(init_method, pydocspec.Function):
        return init_method
    else:
        return None

def inherited_members(ob: pydocspec.Class) -> List[pydocspec.Class.InheritedMember]:
    """provide inherited_members property"""
    _inherited_members: Dict[str, pydocspec.Class.InheritedMember] = {}
    for baselist in _nested_bases(ob):
        #  If the class has super class
        if len(baselist) >= 2:
            attrs = _unmasked_attrs(baselist)
            if attrs:
                for attr in attrs:
                    _inherited_members.setdefault(attr.name, ob.InheritedMember(
                                                    member=attr, 
                                                    inherited_via=baselist))
                    
    return list(_inherited_members.values())

# def overriding_subclasses(ob: pydocspec.Class,
#         name: str,
#         _firstcall: bool = True
#         ) -> Iterator[pydocspec.Class]: 
#     """
#     Retreive the subclasses that override the given name from the parent class object (this object). 
#     """
#     if not _firstcall and name in ob.members:
#         yield ob
#     else:
#         for subclass in ob.subclasses:
#             # if subclass.isVisible:
#             yield from overriding_subclasses(subclass, name, _firstcall=False)

def _nested_bases(classobj: pydocspec.Class) -> Iterator[Tuple[pydocspec.Class, ...]]:
    """
    Helper function to retreive the complete list of base classes chains 
    (represented by tuples) for a given Class. 
    A chain of classes is used to compute the member inheritence from the 
    first element to the last element of the chain.  
    
    The first yielded chain only contains the Class itself. 

    Then for each of the super-classes respecting the MRO:
        - the next yielded chain contains the super class and the class itself, 
        - the the next yielded chain contains the super-super class, the super class and the class itself, etc...
    """
    _mro = classobj.mro
    for i, _ in enumerate(_mro):
        yield tuple(reversed(_mro[:(i+1)]))

def _unmasked_attrs(baselist: Sequence[pydocspec.Class]) -> List[pydocspec.ApiObject]:
    """
    Helper function to reteive the list of inherited children 
    given a base classes chain (As yielded by `nested_bases`). 
    
    The returned members are inherited from the Class listed 
    first in the chain to the Class listed last: they are not overriden in between. 
    """
    maybe_masking = {
        o.name
        for b in baselist[1:]
        for o in b.members
        }
    return [ o for o in baselist[0].members
             if o.name not in maybe_masking ]

def is_abstractclass(ob: 'pydocspec.Class') -> bool:
    """
    Returns whether the given class is an abstract class. 

    Must be set after Class.inherited_members.
    """
    # Check for explicit metaclass=ABCMeta on this specific class.
    meta = ob.metaclass
    if meta is not None:
        if ob.expand_name(meta) in ('abc.ABCMeta',):
            return True

    if not is_subclass_of(ob, ('abc.ABC',)):
        # For a class to be abstract, it must extend abc.ABC.
        return False
    
    for method in filter(lambda o:isinstance(o, pydocspec.Function), 
                    ob.members + [o.member for o in ob.inherited_members]):
        
        assert isinstance(method, pydocspec.Function)
        if func_attr.is_abstractmethod(method):
            return True
    
    return False