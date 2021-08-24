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

from typing import Any, Iterator, Optional, Sequence, Set, Tuple, Union, overload
import re
import warnings

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
    _IDENTIFIER_RE = re.compile("""(?x)
        (%s |             # UNREACHABLE marker, or..
         (script-)?       #   Prefix: script (not a module)
         \w+              #   Identifier (yes, identifiers starting with a
                          #   digit are allowed. See SF bug #1649347)
         '?)              #   Suffix: submodule that is shadowed by a var
        (-\d+)?           # Suffix: unreachable vals with the same name
        $"""
        % re.escape(UNREACHABLE))

    class InvalidDottedName(ValueError):
        """
        An exception raised by the DottedName constructor when one of
        its arguments is not a valid dotted name.
        """

    _ok_identifiers: Set[str] = set()
    """A cache of identifier strings that have been checked against
    _IDENTIFIER_RE and found to be acceptable."""

    def __init__(self, *pieces: Union[str, 'DottedName', Tuple[str, ...]], strict: bool = False):
        """
        Construct a new dotted name from the given sequence of pieces,
        each of which can be either a C{string} or a C{DottedName}.
        Each piece is divided into a sequence of identifiers, and
        these sequences are combined together (in order) to form the
        identifier sequence for the new C{DottedName}.  If a piece
        contains a string, then it is divided into substrings by
        splitting on periods, and each substring is checked to see if
        it is a valid identifier.
        As an optimization, C{pieces} may also contain a single tuple
        of values.  In that case, that tuple will be used as the
        C{DottedName}'s identifiers; it will I{not} be checked to
        see if it's valid.
        @kwparam strict: if true, then raise an L{InvalidDottedName}
        if the given name is invalid.
        """
        if len(pieces) == 0:
            raise DottedName.InvalidDottedName('Empty DottedName')

        if len(pieces) == 1 and isinstance(pieces[0], tuple):
            identifiers: Sequence[str] = pieces[0] # Optimization
            
        else:
            identifiers = []
            for piece in pieces:
                if isinstance(piece, DottedName):
                    identifiers += piece._identifiers
                elif isinstance(piece, str):

                    for subpiece in piece.split('.'):
                        if piece not in self._ok_identifiers:
                            if not self._IDENTIFIER_RE.match(subpiece):
                                if strict:
                                    raise DottedName.InvalidDottedName(
                                        'Bad identifier %r' % (piece,))
                                else:
                                    warnings.warn("Identifier %s looks suspicious; "
                                                "using it anyway." % repr(piece))
                            self._ok_identifiers.add(piece)
                        identifiers.append(subpiece)
                else:
                    raise TypeError('Bad identifier %r: expected '
                                    'DottedName or str' % (piece,))
        
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
        Return a new C{DottedName} whose identifier sequence is formed
        by adding C{other}'s identifier sequence to C{self}'s.
        """
        if isinstance(other, (DottedName, str)):
            return DottedName(self, other)
        else:
            return DottedName(self, *other)

    def __radd__(self, other: Union[str, 'DottedName', Tuple[str, ...]]) -> 'DottedName':
        """
        Return a new C{DottedName} whose identifier sequence is formed
        by adding C{self}'s identifier sequence to C{other}'s.
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
        Return the C{i}th identifier in this C{DottedName}.  If C{i} is
        a non-empty slice, then return a C{DottedName} built from the
        identifiers selected by the slice.  If C{i} is an empty slice,
        return an empty tuple (since empty C{DottedName}s are not valid).
        """
        if isinstance(i, slice):
            pieces = self._identifiers[i.start:i.stop]
            if pieces: return DottedName(pieces)
            else: return ()
        else:
            return self._identifiers[i]

    def __hash__(self) -> int:
        return hash(self._identifiers)

    def __cmp__(self, other: Any) -> int:
        """
        Compare this dotted name to C{other}.  Two dotted names are
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
        C{None} instead.
        """
        if len(self._identifiers) == 1:
            return None
        else:
            return DottedName(*self._identifiers[:-1])

    def dominates(self, name: 'DottedName', strict: bool = False) -> bool:
        """
        Return true if this dotted name is equal to a prefix of
        C{name}.  If C{strict} is true, then also require that
        C{self!=name}.
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
        If C{self} and C{context} share a common ancestor, then return
        a name for C{self}, relative to that ancestor.  If they do not
        share a common ancestor (or if C{context} is C{UNREACHABLE}), then
        simply return C{self}.
        This is used to generate shorter versions of dotted names in
        cases where users can infer the intended target from the
        context.
        @type context: L{DottedName}
        @rtype: L{DottedName}
        """
        if len(self) <= 1 or not context:
            return self
        if self[0] == context[0] and self[0] != self.UNREACHABLE:
            # It's safe to ignore the mypy error here, 
            # we return if the dotted name has only one member.
            return self[1:].contextualize(context[1:]) # type: ignore[union-attr]
        else:
            return self
