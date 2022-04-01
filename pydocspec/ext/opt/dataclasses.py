from typing import Optional, TYPE_CHECKING
from cached_property import cached_property
import astroid.nodes
from pydocspec import astroidutils, ext

if TYPE_CHECKING:
    import pydocspec

class DataClassesDataMixin(ext.VariableMixin):
    @cached_property
    def is_dataclass_field(self: 'pydocspec.Variable') -> bool: #type:ignore[misc]
        """
        Whether this Variable is a L{dataclasses.field} attribute.
        """
        return isinstance(self.value_ast, astroid.nodes.Call) and \
            astroidutils.node2fullname(self.value_ast.func, self) in (
                'dataclasses.field',
                )

class DataClassesClassMixin(ext.ClassMixin):
    @cached_property
    def dataclass_decoration(self: 'pydocspec.Class') -> Optional['pydocspec.Decoration']: #type:ignore[misc]
        """The L{dataclass} decoration of this class, if any."""
        for deco in self.decorations or ():
            if astroidutils.node2fullname(deco.name_ast, self.parent) in ('dataclasses.dataclass',):
                return deco
        return None

def setup_extension(r:ext.ExtRegistrar) -> None:
    r.register_mixins(DataClassesDataMixin, DataClassesClassMixin)

