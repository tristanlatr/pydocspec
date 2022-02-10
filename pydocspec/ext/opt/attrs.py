"""
Handles `attrs` classes like::

    @attr.s(auto_attribs=True)
    class MyData:
        name:str
        age:float
        permissions = attr.ib()
"""
import inspect
from typing import Optional, cast, TYPE_CHECKING
from cached_property import cached_property
import astroid.nodes
import attr

from pydocspec.processor.helpers import is_using_typing_classvar
from pydocspec import astroidutils
import pydocspec.ext

if TYPE_CHECKING:
    import pydocspec

class AttrsDataMixin(pydocspec.ext.DataMixin):

    @cached_property
    def is_attrs_attribute(self: 'pydocspec.Data') -> bool: #type:ignore[misc]
        """
        Whether this Data is an L{attr.ib} attribute.
        """
        if self.Semantic.CLASS_VARIABLE in self.semantic_hints:
            explicit = isinstance(self.value_ast, astroid.nodes.Call) and \
                astroidutils.node2fullname(self.value_ast.func, self) in (
                    'attr.ib', 'attr.attrib', 'attr.attr'
                    )
            implicit = self.datatype_ast is not None and not is_using_typing_classvar(self.datatype_ast, self.parent)
            return explicit or implicit
        return False
        
        #TODO: Add a datatype_from_attrs and datatype_from_attrs_ast properties
        
class AttrsClassMixin(pydocspec.ext.ClassMixin):

    @cached_property
    def attrs_decoration(self: 'pydocspec.Class') -> Optional['pydocspec.Decoration']: #type:ignore[misc]
        """The L{attr.s} decoration of this class, if any."""
        for deco in self.decorations or ():
            if astroidutils.node2fullname(deco.name_ast, self.parent) in ('attr.s', 'attr.attrs', 'attr.attributes'):
                return deco
        return None

    @cached_property
    def uses_attrs_auto_attribs(self) -> bool:
        """Does the C{attr.s()} decoration contain C{auto_attribs=True}?"""
        attrs_deco = self.attrs_decoration
        if attrs_deco is not None and isinstance(attrs_deco.expr_ast, astroid.nodes.Call):
            return uses_auto_attribs(attrs_deco.expr_ast, cast('pydocspec.Class', self)) # we need to help mypy a bit...
        return False
    
    #TODO: Craft a special Function object based on attrs attributes and offer a constructor_method_from_attrs property

# still required with astroid?
_attrs_decorator_signature = inspect.signature(attr.s)
"""Signature of the `attr.s` class decorator."""

def uses_auto_attribs(call: astroid.nodes.Call, ctx: 'pydocspec.ApiObject') -> bool:
    """Does the given `attr.s()` decoration contain ``auto_attribs=True``?
    :param call: AST of the call to `attr.s()`.
        This function will assume that `attr.s()` is called without
        verifying that.
    :param ctx: Namespace that contains the call, used for error reporting.
    :return: `True` if `True` is passed for ``auto_attribs``,
        `False` in all other cases: if ``auto_attribs`` is not passed,
        if an explicit `False` is passed or if an error was reported.
    """
    try:
        args = astroidutils.bind_args(_attrs_decorator_signature, call)
    except TypeError as ex:
        message = str(ex).replace("'", '"')
        ctx.warn(f"Invalid arguments for attr.s(): {message}")
        return False

    auto_attribs_expr = args.arguments.get('auto_attribs')
    if auto_attribs_expr is None:
        return False

    try:
        value = astroidutils.literal_eval(auto_attribs_expr)
    except ValueError:
        ctx.warn(
            'Unable to figure out value for "auto_attribs" argument '
            'to attr.s(), maybe too complex')
        return False

    if not isinstance(value, bool):
        ctx.warn(
            f'Value for "auto_attribs" argument to attr.s() '
            f'has type "{type(value).__name__}", expected "bool"')
        return False

    return value

        # if obj.kind is None:
        #     instance = is_attrib(expr, cls) or (
        #         cls.auto_attribs and annotation is not None and not (
        #             isinstance(annotation, astroid.nodes.Subscript) and
        #             node2fullname(annotation.value, cls) == 'typing.ClassVar'
        #             )
        #         )
        #     obj.kind = model.DocumentableKind.INSTANCE_VARIABLE if instance else model.DocumentableKind.CLASS_VARIABLE              
                # attrs extension
                # if annotation is None:
                #     annotation = self._annotation_from_attrib(expr, cls)

def setup_extension(r:pydocspec.ext.ExtRegistrar) -> None:
    r.register_mixins(AttrsDataMixin, AttrsClassMixin, )

# TODO: fetch datatype_ast from attrs defaut and factory args and dataclass default and default_factory args.