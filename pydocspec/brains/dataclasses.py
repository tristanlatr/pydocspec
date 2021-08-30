import ast
from typing import Optional, TYPE_CHECKING
from cached_property import cached_property

from .. import astutils

if TYPE_CHECKING:
    import pydocspec

class DataClassesDataMixin:
    @cached_property
    def is_dataclass_field(self: 'pydocspec.Data') -> bool: #type:ignore[misc]
        """
        Whether this Data is a L{dataclasses.field} attribute.
        """
        return isinstance(self.value_ast, ast.Call) and \
            astutils.node2fullname(self.value_ast.func, self) in (
                'dataclasses.field',
                )

class DataClassesClassMixin:
    @cached_property
    def dataclass_decoration(self: 'pydocspec.Class') -> Optional['pydocspec.Decoration']: #type:ignore[misc]
        """The L{dataclass} decoration of this class, if any."""
        for deco in self.decorations or ():
            if astutils.node2fullname(deco.name_ast, self.parent) in ('dataclasses.dataclass',):
                return deco
        return None

MIXIN_CLASSES = {
    'Data': DataClassesDataMixin,
    'Class': DataClassesClassMixin,
}
