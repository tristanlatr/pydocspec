import ast
from typing import Optional, cast, TYPE_CHECKING
from cached_property import cached_property

from .. import astutils

if TYPE_CHECKING:
    import pydocspec

class AttrsDataMixin:
    @cached_property
    def is_attrs_attribute(self: 'pydocspec.Data') -> bool: #type:ignore[misc]
        """
        Whether this Data is an L{attr.ib} attribute.
        """
        return isinstance(self.value_ast, ast.Call) and \
            astutils.node2fullname(self.value_ast.func, self) in (
                'attr.ib', 'attr.attrib', 'attr.attr'
                )
        #TODO: Add a datatype_from_attrs and datatype_from_attrs_ast properties
        
class AttrsClassMixin:
    @cached_property
    def attrs_decoration(self: 'pydocspec.Class') -> Optional['pydocspec.Decoration']: #type:ignore[misc]
        """The L{attr.s} decoration of this class, if any."""
        for deco in self.decorations or ():
            if astutils.node2fullname(deco.name_ast, self.parent) in ('attr.s', 'attr.attrs', 'attr.attributes'):
                return deco
        return None

    @cached_property
    def uses_attrs_auto_attribs(self) -> bool:
        """Does the C{attr.s()} decoration contain C{auto_attribs=True}?"""
        attrs_deco = self.attrs_decoration
        if attrs_deco is not None and isinstance(attrs_deco.expr_ast, ast.Call):
            return astutils.uses_auto_attribs(attrs_deco.expr_ast, cast('pydocspec.Class', self))
        return False
    
    #TODO: Craft a special Function object based on attrs attributes and offer a constructor_method_from_attrs property

MIXIN_CLASSES = {
    'Data': (AttrsDataMixin, ),
    'Class': (AttrsClassMixin, ),
}
