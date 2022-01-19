from collections import OrderedDict
from collections.abc import Mapping as abc_Mapping
from typing import Any, Dict, Generic, Iterable, Iterator, List, Mapping, Optional, MutableMapping, Tuple, TypeVar, Union

_KT = TypeVar('_KT')
_VT = TypeVar('_VT')

# TODO: Would be good that this mapping object extends WeakValueDictionary such that references are deleted 
# when an object get removed from the tree. Right now, the FilterVisitor have code that calls the DuplicateSafeDict.rmvalue
# method when an object gets pruned from the tree, but that should not be necessary.
# https://docs.python.org/3/library/weakref.html#weakref.WeakValueDictionary

class DuplicateSafeDict(MutableMapping[_KT, _VT], Generic[_KT, _VT]):
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

    def __init__(self, data: Optional[Union[Mapping[_KT, _VT], Iterable[Tuple[_KT, _VT]]]] = None, **kwargs: Any) -> None:
        
        self._store: Dict[_KT, List[_VT]] = OrderedDict()
        
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key: _KT, value: _VT) -> None:
        self.addvalue(key, value)

    def __getitem__(self, key: _KT) -> _VT:
        """
        Return the last element added that matches the name.
        """
        return self._store[key][-1]

    def __delitem__(self, key: _KT) -> None:
        """
        Remove the last element added value for a key. 
        """
        queue = self._store.get(key)
        if queue and len(queue)>1:
            queue.pop()
        else:
            del self._store[key]

    def __iter__(self) -> Iterator[_KT]:
        return iter(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)
    
    def addvalue(self, key: _KT, value: _VT, shadow: bool = True) -> None:
        """
        :param shadow: Shadow or not an already existent value for that key.
            Old value is still accessible with `getall()` and `getdup()`.
        """
        queue = self._store.get(key)
        if queue:
            if queue[-1] is value:
                return
            if value in queue:
                self.rmvalue(key, value)
            if shadow:
                queue.append(value)
            else:
                queue.insert(len(queue)-1, value)
        else:
            self._store[key] = [value]

    def rmvalue(self, key: _KT, value: _VT) -> None:
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

    def getall(self, key: _KT) -> Optional[List[_VT]]:
        """
        Like 'get()' but returns all values for that name, including duplicates. 
        """
        return self._store.get(key)
    
    def getdup(self, key: _KT) -> List[_VT]:
        """
        Return the duplicates objects for that name. List might be empty. 
        Raise key error if the name doesn't exist.
        """
        return self._store[key][:-1]
    
    def allitems(self) -> Iterator[Tuple[_KT, _VT]]:
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
    def copy(self) -> 'DuplicateSafeDict[_KT, _VT]':
        d: DuplicateSafeDict[_KT, _VT] = DuplicateSafeDict()
        for name, item in self.allitems():
            d[name] = item
        return d

    def __repr__(self) -> str:
        return f"DuplicateSafeDict({list(self.allitems())})"
