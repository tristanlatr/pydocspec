from typing import List, Union, Optional, cast
import attr

from . import _model

@attr.s(auto_attribs=True)
class TreeWalkingState:
    @attr.s(auto_attribs=True, frozen=True)
    class MarkedTreeWalkingState:
        current: '_model.ApiObject'
        last: '_model.ApiObject'
        stack: List[Union[_model.Module, _model.Class]]
    current: '_model.ApiObject'
    last: '_model.ApiObject'
    stack: List[Union[_model.Module, _model.Class]] = []
    def mark(self) -> MarkedTreeWalkingState:
        return self.MarkedTreeWalkingState(
            current=self.current, 
            last=self.last, 
            stack=self.stack.copy())
    def restore(self, mark: MarkedTreeWalkingState) -> None:
        self.current = mark.current
        self.last = mark.last
        self.stack = mark.stack

class Collector:
    """
    Base class to organize a tree of `pydocspec` objects. 
    
    Maintains a stack of objects and incrementally build **one** `Module` instance.

    :see: `pydocspec.TreeRoot.add_object`
    """

    def __init__(self, root: _model.TreeRoot, 
                 module: Optional[_model.Module]=None) -> None:
        self.root = root
        """
        The root of the tree. 
        
        Can be used to access the ``root.factory`` attribute and create new classes.
        """
        
        self.module = module
        """
        The new module.
        """

        self.state = TreeWalkingState(
            cast(_model.ApiObject, None), 
            cast(_model.ApiObject, None), [])
    
    # current = property(fget=lambda self: self.state.current, 
    #                    fset=lambda self, current: setattr(self.state.current, 'current', current))

    @property
    def current(self) -> _model.ApiObject:
        return self.state.current
    @current.setter
    def current(self, ob: _model.ApiObject) -> None:
        self.state.current = ob
    @property
    def last(self) -> _model.ApiObject:
        return self.state.last
    @last.setter
    def last(self, ob: _model.ApiObject) -> None:
        self.state.last = ob
    
    @property
    def stack(self) -> List[Union[_model.Module, _model.Class]]:
        return self.state.stack

    def push(self, ob: _model.ApiObject) -> None:
        """
        Enter an object. We can push attributes, but we can't push other stuff inside it.
        """
        # Note: the stack is initiated with a None value.
        ctx = self.current
        if ctx is not None: 
            assert isinstance(ctx, _model.HasMembers), (f"Cannot add new object ({ob!r}) inside {ctx.__class__.__name__}. "
                                                           f"{ctx.full_name} is not namespace.")
        self.stack.append(ctx)
        self.current = ob

    def pop(self, ob: _model.ApiObject) -> None:
        """
        Exit an object.
        """
        assert self.current is ob , f"{ob!r} is not {self.current!r}"
        self.last = self.current
        self.current = self.stack.pop()
    
    def add_object(self, ob: _model.ApiObject, push: bool = True) -> None:
        """
        See `TreeRoot.add_object`.
        """
        self.root.add_object(ob, self.current)
        
        if self.current is None:
            # yes, it's reachable, when first adding a module.
            assert isinstance(ob, _model.Module) #type:ignore[unreachable]
            if self.module is None:
                self.module = ob
            else:
                # just do some assertion.
                assert self.module is ob, f"{ob!r} is not {self.module!r}"
        
        if push:
            self.push(ob)