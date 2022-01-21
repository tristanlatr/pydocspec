"""
Helpers to populate attributes of `Class` instances. 
"""

from typing import List, Optional, Union

import astroid.nodes
import astroid.exceptions
import pydocspec
from pydocspec import _model, c3linear
from . import helpers

class MRO(c3linear.GenericMRO[pydocspec.Class]):
    def bases(self, cls: pydocspec.Class) -> List[pydocspec.Class]:
        return [b for b in cls.resolved_bases if isinstance(b, pydocspec.Class)]

# List of exceptions class names in the standard library, Python 3.8.10
_exceptions = ('ArithmeticError', 'AssertionError', 'AttributeError', 
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
    # must be set after resolved_bases
    for base in ob.ancestors(True):
        if base in _exceptions:
            return True
    return False


def mro_from_astroid(ob: _model.Class) -> List[pydocspec.Class]:
    # this does not support objects loaded from other places than astroid, 
    # for instance coming from introspection of a c-module.  
    # This is why we need to re-compute the MRO after.
    # But it does the job for the first iteration 
    # This should not rely on Class.resolved_bases, since resolved_bases relies 
    # on Class.find() which relies on Class.mro attribute.
    # The result from this function is used temporarly to compute the resolved_bases attribute
    # then .mro attribute is re-computed with mro() function below.
    if ob._ast is None:
        return []
    try:
        node_mro = ob._ast.mro()
        return [o for o in (helpers.ast2apiobject(ob.root, node) for node in node_mro) if o] # type:ignore
    except astroid.exceptions.MroError:
        node_mro = [ob._ast] + list(ob._ast.ancestors())
        return [o for o in (helpers.ast2apiobject(ob.root, node) for node in node_mro) if o] # type:ignore

 # must be set after resolved_bases
def mro(ob: pydocspec.Class) -> List[pydocspec.Class]:
    # FIXME: we currently process the MRO twice for objects comming from ast :/
    try: 
        return MRO().mro(ob)
    except ValueError as e:
        ob.warn(str(e))
        return list(
            filter(lambda ob: isinstance(ob, pydocspec.Class), 
                    ob.ancestors(True)))


def resolved_bases(ob: pydocspec.Class) -> List[Union['pydocspec.Class', 'str']]: 
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
    # SOLUTION: Populate the Class.mro attribute from astroid 
    # OR use this utility method from sphinx-autoapi resolve_qualname(ctx: NodeNG, name:str) -> str
    # https://github.com/readthedocs/sphinx-autoapi/blob/71c6ceebe0b02c34027fcd3d56c8641e9b94c7af/autoapi/mappers/python/astroid_utils.py#L64
    objs: List[Union['pydocspec.Class', 'str']] = []
    for base in ob.bases or ():
        # it makes 
        # resolve_qualname() is an alternative for expand_name() that is only based on astroid
        # resolved = astroidutils.resolve_qualname(ob.scope._ast, base)
        # resolved_obj = ob.root.all_objects.get(resolved)
        # it looks like resolved_obj can be an Indirection + 
        # need to create a separate function because it breaks the converter since ob.scope._ast is None for objects comming from the converter.
        # if resolved_obj:
        #     objs.append(resolved_obj)
        # else:
        #     objs.append(resolved)
        resolved = ob.parent.resolve_name(base)
        if isinstance(resolved, pydocspec.Class):
            objs.append(resolved)
        elif resolved is not None:
            objs.append(resolved.full_name)
        else:
            objs.append(ob.parent.expand_name(base))
    return objs


def process_subclasses(ob: pydocspec.Class) -> None:
    # for all resolved_bases classes, add ob to the subclasses list
    for b in ob.resolved_bases:
        if isinstance(b, pydocspec.Class):
            b.subclasses.append(ob)

def constructor_method(ob: _model.Class) -> Optional['pydocspec.Function']:
    init_method = ob.get_member('__init__')
    if isinstance(init_method, pydocspec.Function):
        return init_method
    else:
        return None