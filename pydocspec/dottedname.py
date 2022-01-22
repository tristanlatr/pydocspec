######################################################################
# Dotted Names
# From: https://github.com/nltk/epydoc/blob/master/src/epydoc/apidoc.py
# epydoc -- API Documentation Classes
#
# Copyright (C) 2005 Edward Loper
# Author: Edward Loper <edloper@loper.org>
# URL: <http://epydoc.sf.net>
#
# $Id: apidoc.py 1811 2009-02-03 21:29:51Z edloper $
######################################################################

from typing import Any, Iterator, Optional, Sequence, Set, Tuple, Union, overload, List
import re
import logging

#TODO: Would be good that DottedName fully implements MutableSequence[str]
class DottedName:
    """
    A sequence of identifiers, separated by periods, used to name a
    Python variable, value, or argument.  The identifiers that make up
    a dotted name can be accessed using the indexing operator:
        >>> name = DottedName('epydoc', 'api_doc', 'DottedName')
        >>> print(name)
        epydoc.api_doc.DottedName
        >>> name[1]
        'api_doc'
    
    The special, normally invalid, indentifier "??" can be used for 
    unreachable or unknown names.
    """
    UNREACHABLE = "??"
    _IDENTIFIER_RE = re.compile(r"""(?x)
        (%s |             # UNREACHABLE marker, or..
         (script-)?       #   Prefix: script (not a module)
         \w+              #   Identifier (yes, identifiers starting with a
                          #   digit are allowed. See SF bug #1649347)
         '?)              #   Suffix: submodule that is shadowed by a var
        (-\d+)?           # Suffix: unreachable vals with the same name
        $"""
        % re.escape(UNREACHABLE), re.VERBOSE)

    class InvalidDottedName(ValueError):
        """
        An exception raised by the DottedName constructor when one of
        its arguments is not a valid dotted name.
        """

    _ok_identifiers: Set[str] = set(('', '*')) # by default we accept empty identifiers and widcard, we check for validity after.
    """A cache of identifier strings that have been checked against
    _IDENTIFIER_RE and found to be acceptable."""

    def __init__(self, *pieces: Union[str, 'DottedName', Tuple[str, ...]], strict: bool = False): # True for testing...
        """
        Construct a new dotted name from the given sequence of pieces,
        each of which can be either a ``string`` or a ``DottedName``.
        Each piece is divided into a sequence of identifiers, and
        these sequences are combined together (in order) to form the
        identifier sequence for the new ``DottedName``.  If a piece
        contains a string, then it is divided into substrings by
        splitting on periods, and each substring is checked to see if
        it is a valid identifier.
        As an optimization, ``pieces`` may also contain a single tuple
        of values.  In that case, that tuple will be used as the
        ``DottedName``'s identifiers; it will *not* be checked to
        see if it's valid.

        :param strict: if true, then raise an `InvalidDottedName`
            if the given name is invalid.
        """
        def _is_valid(_pieces: Sequence[str]) -> bool:
            # empty piece of a dotted name are valid if there is at least one 
            # non-empty name and all empty anmes are at the start of the name, meaning it's a relative name
            seen = set()
            for p in _pieces:
                if p == '' and len(seen)>1:
                    return False
                seen.add(p)
            # wilcards are allowed if they are present only once at the end of the name.
            if _pieces.count('*')>0 and _pieces[-1]!='*' or _pieces.count('*')>1:
                return False
            return True
        
        if len(pieces) == 0:
            raise DottedName.InvalidDottedName('Empty DottedName')
        try:
            if len(pieces) == 1 and isinstance(pieces[0], tuple):
                identifiers: Sequence[str] = pieces[0] # Optimization
                
            else:
                identifiers = []
                for piece in pieces:
                    if isinstance(piece, DottedName):
                        identifiers += piece._identifiers
                    elif isinstance(piece, str):

                        for subpiece in piece.split('.'):
                            
                            if piece not in self._ok_identifiers and subpiece not in self._ok_identifiers:
                                # Suports relative dotted names like .mod.Class or ...pack._base
                                if not self._IDENTIFIER_RE.match(subpiece):
                                    piece_info = '' if subpiece==piece else f' in name {piece!r}'
                                    if strict:
                                        raise DottedName.InvalidDottedName(
                                            f'Bad identifier {subpiece!r}{piece_info}')
                                    else:
                                        logging.getLogger('pydocspec').warning(f"Identifier {subpiece!r}{piece_info} looks suspicious; "
                                                    "using it anyway.")
                                self._ok_identifiers.add(subpiece)
                            identifiers.append(subpiece)

                        if piece not in self._ok_identifiers and not _is_valid(identifiers):
                            if strict:
                                raise DottedName.InvalidDottedName(
                                    'Bad identifier %r' % ('.'.join(identifiers),))
                            else:
                                logging.getLogger('pydocspec').warning("Identifier %s looks suspicious; "
                                            "using it anyway." % '.'.join(identifiers))
                        self._ok_identifiers.add(piece)
                    else:
                        raise TypeError('Bad identifier %r: expected '
                                        'DottedName or str' % (piece,))
        finally:
            self._identifiers: Tuple[str, ...] = tuple(identifiers)

    def __repr__(self) -> str:
        idents = [repr(ident) for ident in self._identifiers]
        return 'DottedName(' + ', '.join(idents) + ')'

    def __str__(self) -> str:
        """
        Return the dotted name as a string formed by joining its
        identifiers with periods:
            >>> print(DottedName('epydoc', 'api_doc', 'DottedName'))
            epydoc.api_doc.DottedName
        """
        return '.'.join(self._identifiers)

    def __add__(self, other: Union[str, 'DottedName', Tuple[str, ...]]) -> 'DottedName':
        """
        Return a new ``DottedName`` whose identifier sequence is formed
        by adding ``other``'s identifier sequence to ``self``'s.
        """
        if isinstance(other, (DottedName, str)):
            return DottedName(self, other)
        else:
            return DottedName(self, *other)

    def __radd__(self, other: Union[str, 'DottedName', Tuple[str, ...]]) -> 'DottedName':
        """
        Return a new ``DottedName`` whose identifier sequence is formed
        by adding ``self``'s identifier sequence to ``other``'s.
        """
        if isinstance(other, (DottedName, str)):
            return DottedName(other, self)
        else:
            return DottedName(*(list(other)+[self])) # type: ignore[list-item]
    
    @overload
    def __getitem__(self, i: int) -> str:
        ...
    @overload
    def __getitem__(self, i: slice) -> Union['DottedName', Tuple[()]]:
        ...
    def __getitem__(self, i: Union[slice, int]) -> Union[str, 'DottedName', Tuple[()]]:
        """
        Return the ``i``th identifier in this ``DottedName``.  If ``i`` is
        a non-empty slice, then return a ``DottedName`` built from the
        identifiers selected by the slice.  If ``i`` is an empty slice,
        return an empty tuple (since empty ``DottedName``s are not valid).
        """
        if isinstance(i, slice):
            pieces = self._identifiers[i.start:i.stop]
            if pieces: return DottedName(pieces)
            else: return ()
        else:
            return self._identifiers[i]
    
    # @overload
    # def __delitem__(self, i: int) -> None:
    #     ...
    # @overload
    # def __delitem__(self, i: slice) -> None:
    #     ...
    # def __delitem__(self, i: Union[slice, int]) -> None:
    #     """
    #     Remove the ``i``th identifier in this ``DottedName``.  If ``i`` is
    #     a non-empty slice, then delete the identifiers selected by the slice.  
    #     """
    #     if isinstance(i, slice):
    #         del self._identifiers[i.start:i.stop]
    #     else:
    #         del self._identifiers[i]
    
    # def __setitem__(self, i: int, value: str) -> None: # type:ignore[override]
    #     """
    #     Set the ``i``th identifier in this ``DottedName``.
    #     """
    #     if isinstance(i, int):
    #         self._identifiers[i] = value
    #     else:
    #         raise TypeError(f"DottedName.__setitem__ expected string value, got {type(value)}")

    # def insert(self, index: int, value: str) -> None:
    #     return self._identifiers.insert(index, value)

    def __hash__(self) -> int:
        return hash(self._identifiers)

    def __cmp__(self, other: Any) -> int:
        """
        Compare this dotted name to ``other``.  Two dotted names are
        considered equal if their identifier subsequences are equal.
        Ordering between dotted names is lexicographic, in order of
        identifier from left to right.
        """
        if not isinstance(other, DottedName):
            return -1
        return (self._identifiers > other._identifiers) - \
               (self._identifiers < other._identifiers)

    def __lt__(self, other: Any) -> bool:
        return self.__cmp__(other) < 0
    
    def __le__(self, other: Any) -> bool:
        return self.__cmp__(other) <= 0
    
    def __eq__(self, other: Any) -> bool:
        return self.__cmp__(other) == 0
    
    def __ne__(self, other: Any) -> bool:
        return self.__cmp__(other) != 0
    
    def __ge__(self, other: Any) -> bool:
        return self.__cmp__(other) >= 0
    
    def __gt__(self, other: Any) -> bool:
        return self.__cmp__(other) > 0

    def __len__(self) -> int:
        """
        Return the number of identifiers in this dotted name.
        """
        return len(self._identifiers)
    
    def __iter__(self) -> Iterator[str]:
        return iter(self._identifiers)

    def container(self) -> Optional['DottedName']:
        """
        Return the DottedName formed by removing the last identifier
        from this dotted name's identifier sequence.  If this dotted
        name only has one name in its identifier sequence, return
        ``None`` instead.
        """
        if len(self._identifiers) == 1:
            return None
        else:
            return DottedName(*self._identifiers[:-1])

    def dominates(self, name: 'DottedName', strict: bool = False) -> bool:
        """
        Return true if this dotted name is equal to a prefix of
        ``name``.  If ``strict`` is true, then also require that
        ``self!=name``.
            >>> DottedName('a.b').dominates(DottedName('a.b.c.d'))
            True
        """
        len_self = len(self._identifiers)
        len_name = len(name._identifiers)

        if (len_self > len_name) or (strict and len_self == len_name):
            return False
        # The following is redundant (the first clause is implied by
        # the second), but is done as an optimization.
        return ((self._identifiers[0] == name._identifiers[0]) and
                self._identifiers == name._identifiers[:len_self])

    def contextualize(self, context: Sequence[str]) -> 'DottedName':
        """
        If ``self`` and ``context`` share a common ancestor, then return
        a name for ``self``, relative to that ancestor.  If they do not
        share a common ancestor (or if ``context`` is ``UNREACHABLE``), then
        simply return ``self``.
        This is used to generate shorter versions of dotted names in
        cases where users can infer the intended target from the
        context.
        :type context: `DottedName`
        :rtype: `DottedName`
        """
        if len(self) <= 1 or not context:
            return self
        if self[0] == context[0] and self[0] != self.UNREACHABLE:
            # It's safe to ignore the mypy error here, 
            # we return if the dotted name has only one member.
            return self[1:].contextualize(context[1:]) # type: ignore[union-attr]
        else:
            return self

def container(name:str) -> Optional[str]:
    """See `DottedName.container`."""
    c = DottedName(name).container()
    return str(c) if c else None
def dominates(container:str, name:str) -> bool:
    """See `DottedName.dominates`."""
    return DottedName(container).dominates(DottedName(name))
def contextualize(name:str, context:str) -> str:
    """See `DottedName.contextualize`."""
    return str(DottedName(name).contextualize(context))