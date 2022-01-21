"""
Compute method resolution order. 
Implements `Class.mro` attribute.
"""
# MIT License
# Copyright (c) 2019 Vitaly R. Samigullin
# Adapadted from https://github.com/pilosus/c3linear

import abc
from collections import deque
from itertools import islice
from typing import Generic, List, Tuple, Optional, TypeVar, Deque

T = TypeVar('T')

class GenericMRO(Generic[T], abc.ABC):

    class Dependency(Deque[Optional['T']]):
        @property
        def head(self) -> Optional['T']:
            try:
                return self[0]
            except IndexError:
                return None
        @property
        def tail(self) -> islice:  # type: ignore
            """
            Return islice object, which is suffice for iteration or calling `in`
            """
            try:
                return islice(self, 1, self.__len__())
            except (ValueError, IndexError):
                return islice([], 0, 0)

    class DependencyList:
        """
        A class represents list of linearizations (dependencies)
        The last element of DependencyList is a list of parents.
        It's needed  to the merge process preserves the local
        precedence order of direct parent classes.
        """
        def __init__(self, *lists: List[Optional['T']]) -> None:
            self._lists = [GenericMRO.Dependency(i) for i in lists]

        def __contains__(self, item: 'T') -> bool:
            """
            Return True if any linearization's tail contains an item
            """
            return any([item in l.tail for l in self._lists])  # type: ignore

        def __len__(self) -> int:
            size = len(self._lists)
            return (size - 1) if size else 0

        def __repr__(self) -> str:
            return self._lists.__repr__()

        @property
        def heads(self) -> List[Optional['T']]:
            return [h.head for h in self._lists]

        @property
        def tails(self) -> 'DependencyList':  # type: ignore
            """
            Return self so that __contains__ could be called
            Used for readability reasons only
            """
            return self

        @property
        def exhausted(self) -> bool:
            """
            Return True if all elements of the lists are exhausted
            """
            return all(map(lambda x: len(x) == 0, self._lists))

        def remove(self, item: Optional['T']) -> None:
            """
            Remove an item from the lists
            Once an item removed from heads, the leftmost elements of the tails
            get promoted to become the new heads.
            """
            for i in self._lists:
                if i and i.head == item:
                    i.popleft()

    def _merge(self, *lists: List[Optional['T']]) -> List[Optional['T']]:

        result: List[Optional['T']] = []
        linearizations = GenericMRO.DependencyList(*lists)

        while True:
            if linearizations.exhausted:
                return result

            for head in linearizations.heads:
                if head and (head not in linearizations.tails): 
                    result.append(head) # type: ignore
                    linearizations.remove(head)

                    # Once candidate is found, continue iteration
                    # from the first element of the list
                    break
            else:
                # Loop never broke, no linearization could possibly be found
                raise ValueError('Cannot compute c3 linearization')

    @abc.abstractmethod
    def bases(self, cls: 'T') -> List['T']:
        """
        Get the direct bases of a class.
        """
        raise NotImplementedError()

    def mro(self, cls: 'T') -> List['T']:
        """
        Return a list of classes in order corresponding to Python's MRO.
        """
        
        result: List['T'] = [cls]
        _bases = self.bases(cls)
        
        if not _bases:
            return result
        else:
            return result + self._merge(*[self.mro(kls) for kls in _bases], _bases) # type: ignore

