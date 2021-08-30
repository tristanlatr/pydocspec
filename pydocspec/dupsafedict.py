from collections import OrderedDict
from collections.abc import Mapping as abc_Mapping
from typing import Any, Dict, Generic, Iterable, Iterator, List, Mapping, Optional, MutableMapping, Tuple, TypeVar, Union

_KT = TypeVar('_KT')
_VT = TypeVar('_VT')

# TODO: Would be good that this mapping object extends WeakValueDictionary such that references are deleted 
# when an object get removed from the tree. Right now, the FilterVisitor have code that calls the DuplicateSafeDict.rmvalue
# method when an object gets pruned from the tree, but that should not be necessary.
# https://docs.python.org/3/library/weakref.html#weakref.WeakValueDictionary

class DuplicateSafeDict(MutableMapping[str, _VT], Generic[_VT]):
    """
    Dictionnary that do not discard old objects when they are overriden, but instead, 
    only updates a reference to the new object. 

    Duplicate values can be fetched with methods `getall`, `getdup` and `allitems`.

    >>> d = DuplicateSafeDict(me='bob', you='claudia')
    >>> d['me'] = 'james'
    >>> d['me'] = 'james'
    >>> d['me'] = 'bob'
    >>> d.getall('me')
    ['james', 'bob']
    >>> d['me'] = 'james'
    >>> d.getall('me')
    ['bob', 'james']
    >>> d.getdup('me')
    ['bob']
    >>> d == {'me':'bob', 'you':'claudia'}
    False
    >>> d == DuplicateSafeDict([('me', 'bob'), ('me', 'james'), ('you', 'claudia')])
    True
    >>> del d['me']
    >>> d.getall('me')
    ['bob']
    >>> d == dict([('me', 'bob'), ('you', 'claudia')])
    True
    """

    def __init__(self, data: Optional[Union[Mapping[str, _VT], Iterable[Tuple[str, _VT]]]] = None, **kwargs: Any) -> None:
        
        self._store: Dict[str, List[_VT]] = OrderedDict()
        
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key: str, value: _VT) -> None:
        queue = self._store.get(key)
        if queue:
            if value in queue:
                self.rmvalue(key, value)
            queue.append(value)
        else:
            self._store[key] = [value]

    def __getitem__(self, key: str) -> _VT:
        """
        Return the last element added that matches the name.
        """
        return self._store[key][-1]

    def __delitem__(self, key: str) -> None:
        """
        Remove the last element added value for a key. 
        """
        queue = self._store.get(key)
        if queue and len(queue)>1:
            queue.pop()
        else:
            del self._store[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)
    
    def rmvalue(self, key: str, value: _VT) -> None:
        """
        Remove a value from the dict. The value can be a duplicate.
        If no values are left in the queue after the removal, the whole queue will be deleted.

        Raise key error if no values exists for the key.
        Raise value error if the value if not present. 
        """
        queue = self._store[key]
        queue.remove(value)
        if len(queue) < 1:
            del self._store[key]

    def getall(self, key: str) -> Optional[List[_VT]]:
        """
        Like 'get()' but returns all values for that name, including duplicates. 
        """
        return self._store.get(key)
    
    def getdup(self, key: str) -> List[_VT]:
        """
        Return the duplicates objects for that name. List might be empty. 
        Raise key error if the name doesn't exist.
        """
        return self._store[key][:-1]
    
    def allitems(self) -> Iterator[Tuple[str, _VT]]:
        """
        Like 'items()' but returns all values, including duplicates. 
        """
        for name, item in self._store.items():
            for value in item:
                yield (name, value)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, DuplicateSafeDict):
            return list(self.allitems()) == list(other.allitems())
        if isinstance(other, abc_Mapping):
            return list(self.allitems()) == list(DuplicateSafeDict(other).allitems())
        else:
            return NotImplemented

    # Copy is required
    def copy(self) -> 'DuplicateSafeDict[_VT]':
        d: DuplicateSafeDict[_VT] = DuplicateSafeDict()
        for name, item in self.allitems():
            d[name] = item
        return d

    def __repr__(self) -> str:
        return f"DuplicateSafeDict({list(self.allitems())})"
