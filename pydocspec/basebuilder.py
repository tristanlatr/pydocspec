from pathlib import Path
from typing import Generic, List, Tuple, TypeVar, Union, Optional, cast, TYPE_CHECKING
import abc
import inspect

import attr
import astroid.nodes

from . import _model
import docspec

if TYPE_CHECKING:
    import pydocspec
    from pydocspec import specfactory

ModuleT = TypeVar('ModuleT')
ApiObjectT = TypeVar('ApiObjectT', bound=docspec.ApiObject)

@attr.s(auto_attribs=True, frozen=True)
class MarkedTreeWalkingState(Generic[ApiObjectT]):
    current: ApiObjectT
    last: ApiObjectT
    stack: Tuple[ApiObjectT, ...]

MarkedTreeWalkingStateT = MarkedTreeWalkingState

@attr.s
class TreeWalkingState(Generic[ApiObjectT]):
    MarkedTreeWalkingState=MarkedTreeWalkingState
    current: ApiObjectT = attr.ib()
    last: ApiObjectT = attr.ib()
    stack: List[ApiObjectT] = attr.ib(factory=list) # should be only classes and modules
    
    def mark(self) -> MarkedTreeWalkingStateT[ApiObjectT]:
        return self.MarkedTreeWalkingState(
            current=self.current, 
            last=self.last, 
            stack=tuple(self.stack))
    def restore(self, mark: MarkedTreeWalkingStateT[ApiObjectT]) -> None:
        self.current = mark.current
        self.last = mark.last
        self.stack = list(mark.stack)

class BaseCollector(Generic[ModuleT, ApiObjectT]):
    def __init__(self, module: Optional[ModuleT]=None) -> None:
        
        self.module = module
        """
        The new module.
        """

        self.state: TreeWalkingState[ApiObjectT] = TreeWalkingState(
            cast(ApiObjectT, None), 
            cast(ApiObjectT, None), [])

    @property
    def current(self) -> ApiObjectT:
        return self.state.current
    @current.setter
    def current(self, ob: ApiObjectT) -> None:
        self.state.current = ob
    @property
    def last(self) -> ApiObjectT:
        return self.state.last
    @last.setter
    def last(self, ob: ApiObjectT) -> None:
        self.state.last = ob
    @property
    def stack(self) -> List[ApiObjectT]:
        return self.state.stack

    def push(self, ob: ApiObjectT) -> None:
        """
        Enter an object. We can push attributes, but we can't push other stuff inside it.
        """
        # Note: the stack is initiated with a None value.
        ctx = self.current
        if ctx is not None: 
            assert isinstance(ctx, docspec.HasMembers), (f"Cannot add new object ({ob!r}) inside {ctx.__class__.__name__}. "
                                                           f"{ctx!r} must be a class or a module.")
        self.stack.append(ctx) #type:ignore[arg-type]
        self.current = ob

    def pop(self, ob: ApiObjectT) -> None:
        """
        Exit an object.
        """
        assert self.current is ob , f"{ob!r} is not {self.current!r}"
        self.last = self.current
        self.current = self.stack.pop()

class Collector(BaseCollector[_model.Module, _model.ApiObject]):
    """
    Base class to organize a tree of `pydocspec` objects. 
    
    Maintains a stack of objects and incrementally build **one** `Module` instance.

    :see: `pydocspec.TreeRoot.add_object`
    """

    def __init__(self, root: _model.TreeRoot, 
                 module: Optional[_model.Module]=None) -> None:
        super().__init__(module=module)
        
        self.root = root
        """
        The root of the tree. 
        
        Can be used to access the ``root.factory`` attribute and create new instances.
        """
    
    def add_object(self, ob: _model.ApiObject, push: bool = True, 
                   parent: Optional[_model.ApiObject]=None) -> None:
        """
        See `TreeRoot.add_object`.
        """
        
        parent_ = parent or self.current

        # Do assertion to make sure we don't add an object that requires a parent as root module
        if not isinstance(ob, (_model.Module,)):
            assert parent_ is not None
        
        self.root.add_object(ob, parent_)
        
        if parent_ is None:
            # yes, it's reachable, when first adding a module.
            assert isinstance(ob, _model.Module) #type:ignore[unreachable]
            if self.module is None:
                self.module = ob
            else:
                # just do some assertion.
                assert self.module is ob, f"{ob!r} is not {self.module!r}"
        
        if push:
            self.push(ob)
        else:
            self.last = ob # save new object in .last attribute

# NOT used yet. 
class BaseBuilder(abc.ABC):
    root: 'pydocspec.TreeRoot'

    def add_module(self, path: Path) -> None:...
    def add_module_string(self, text: str, modname: str,
                          parent_name: Optional[str] = None,
                          path: str = '<fromtext>',
                          is_package: bool = False, ) -> None: ...
    def build_modules(self) -> None: ...


def parameter2argument(param: inspect.Parameter, factory: 'specfactory.Factory') -> 'pydocspec.Argument':
    """
    Convert a `inspect.Parameter` instance to a `pydocspec.Argument`.
    """
    kindmap = {
        inspect.Parameter.POSITIONAL_ONLY: docspec.Argument.Type.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD: docspec.Argument.Type.POSITIONAL,
        inspect.Parameter.VAR_POSITIONAL: docspec.Argument.Type.POSITIONAL_REMAINDER,
        inspect.Parameter.KEYWORD_ONLY: docspec.Argument.Type.KEYWORD_ONLY,
        inspect.Parameter.VAR_KEYWORD: docspec.Argument.Type.KEYWORD_REMAINDER,
    }

    if param.annotation != inspect.Signature.empty:
        annotation_str = param.annotation.as_string() if isinstance(param.annotation, astroid.nodes.NodeNG) else str(param.annotation)
        annotation_ast = param.annotation if isinstance(param.annotation, astroid.nodes.NodeNG) else None
    else:
        annotation_str = annotation_ast = None
    
    if param.default != inspect.Signature.empty:
        default_value_str = param.default.as_string() if isinstance(param.default, astroid.nodes.NodeNG) else str(param.default)
        default_value_ast = param.default if isinstance(param.default, astroid.nodes.NodeNG) else None
    else:
        default_value_str = default_value_ast = None

    return factory.Argument(
        name=param.name, 
        location=factory.Location(
            filename='', # TODO: Fill by post-processor
            lineno=0,
        ),
        type=kindmap[param.kind], #type:ignore[index]
        datatype=annotation_str, 
        default_value=default_value_str,
        datatype_ast=annotation_ast,
        default_value_ast=default_value_ast, )