"""
Our own version of the docspec loader. 

@note: The current implementation is based on the C{ast} module only. 
    Because of that, single line comments (starting by "C{#}") are ignored.
"""
from typing import List

import attr

import pydocspec
from . import specfactory

@attr.s(auto_attribs=True)
class BaseBuilder:
    """
    Base class to create a tree of C{pydocspec} objects. 
    
    This builds one C{Module} instance.
    """

    factory: specfactory.Factory

    module: pydocspec.Module = attr.ib(default=None, init=False)
    """
    The new module.
    """

    _current : pydocspec.ApiObject = attr.ib(default=None, init=False)
    _stack: List[pydocspec.ApiObject] = attr.ib(factory=list, init=False)

    def push(self, ob: pydocspec.ApiObject) -> None:
        """
        Enter an object.
        """
        self._stack.append(self._current)
        self._current = ob

    def pop(self, ob: pydocspec.ApiObject) -> None:
        """
        Exit an object.
        """
        assert self._current is ob , f"{ob!r} is not {self._current!r}"
        self._current = self._stack.pop()
    
    def add_object(self, ob: pydocspec.ApiObject) -> None:
        """
        Add a newly created object to the tree, and enter it.
        """
        if self._current:
            assert isinstance(self._current, pydocspec.HasMembers)
            self._current.members.append(ob)
            self._current.sync_hierarchy(self._current.parent)
        else:
            assert isinstance(ob, pydocspec.Module)
            self.module = ob
        
        self.push(ob)


