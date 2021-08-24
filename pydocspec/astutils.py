"""
Various bits of reusable code related to L{ast.AST} node processing.
"""

from typing import Iterable, Optional, List, TYPE_CHECKING, Union
from inspect import BoundArguments, Signature
import ast
import inspect

import attr

if TYPE_CHECKING:
    from pydocspec import ApiObject

_attrs_decorator_signature = inspect.signature(attr.s)
"""Signature of the L{attr.s} class decorator."""

def uses_auto_attribs(call: ast.Call, ctx: 'ApiObject') -> bool:
    """Does the given L{attr.s()} decoration contain C{auto_attribs=True}?
    @param call: AST of the call to L{attr.s()}.
        This function will assume that L{attr.s()} is called without
        verifying that.
    @param module: Module that contains the call, used for error reporting.
    @return: L{True} if L{True} is passed for C{auto_attribs},
        L{False} in all other cases: if C{auto_attribs} is not passed,
        if an explicit L{False} is passed or if an error was reported.
    """
    try:
        args = bind_args(_attrs_decorator_signature, call)
    except TypeError as ex:
        message = str(ex).replace("'", '"')
        ctx._warns(f"Invalid arguments for attr.s(): {message}")
        return False

    auto_attribs_expr = args.arguments.get('auto_attribs')
    if auto_attribs_expr is None:
        return False

    try:
        value = ast.literal_eval(auto_attribs_expr)
    except ValueError:
        ctx._warns(
            'Unable to figure out value for "auto_attribs" argument '
            'to attr.s(), maybe too complex')
        return False

    if not isinstance(value, bool):
        ctx._warns(
            f'Value for "auto_attribs" argument to attr.s() '
            f'has type "{type(value).__name__}", expected "bool"')
        return False

    return value

def node2dottedname(node: Optional[ast.expr]) -> Optional[List[str]]:
    """
    Resove expression composed by L{ast.Attribute} and L{ast.Name} nodes to a list of names. 
    """
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return None
    parts.reverse()
    return parts

def node2fullname(expr: Optional[Union[ast.expr, str]], ctx: 'ApiObject') -> Optional[str]:
    """
    Return L{ctx.expand_name(name)} if C{expr} is a valid name, or C{None}.
    """
    dottedname = node2dottedname(expr) if isinstance(expr, ast.expr) else expr
    if dottedname is None:
        return None
    return ctx.expand_name('.'.join(dottedname)) 

def bind_args(sig: Signature, call: ast.Call) -> BoundArguments:
    """
    Binds the arguments of a function call to that function's signature.
    @raise TypeError: If the arguments do not match the signature.
    """
    kwargs = {
        kw.arg: kw.value
        for kw in call.keywords
        # When keywords are passed using '**kwargs', the 'arg' field will
        # be None. We don't currently support keywords passed that way.
        if kw.arg is not None
        }
    return sig.bind(*call.args, **kwargs)

def extract_expr(expr: str, filename: Optional[str] = None) -> ast.expr:
    """
    Convert a python expression to ast. 
    """
    _ast = ast.parse(expr, filename or '<unknown>')
    elem = _ast.body[0]
    assert isinstance(elem, ast.Expr), f"value should be an expression, not {type(elem)}"
    return elem.value

def _extract_annotation_subscript(annotation: ast.Subscript) -> ast.AST:
    """
    Extract the "str, bytes" part from annotations like  "Union[str, bytes]".
    """
    ann_slice = annotation.slice
    if isinstance(ann_slice, ast.Index):
        return ann_slice.value
    else:
        return ann_slice

def extract_final_subscript(annotation: ast.Subscript) -> ast.expr:
    """
    Extract the "str" part from annotations like  "Final[str]".

    @raises ValueError: If the "Final" annotation is not valid.
    """ 
    ann_slice = _extract_annotation_subscript(annotation)
    if isinstance(ann_slice, (ast.ExtSlice, ast.Slice, ast.Tuple)):
        raise ValueError("Annotation is invalid, it should not contain slices.")
    else:
        assert isinstance(ann_slice, ast.expr)
        return ann_slice

def unstring_annotation(node: ast.expr, ctx: 'ApiObject') -> ast.expr:
    """Replace all strings in the given expression by parsed versions.
    @return: The unstringed node. If parsing fails, an error is logged
        and the original node is returned.
    """
    try:
        expr = _AnnotationStringParser().visit(node)
    except SyntaxError as ex:
        ctx._warns(f'syntax error in annotation: {ex}')
        return node
    else:
        assert isinstance(expr, ast.expr), expr
        return expr

def infer_type(expr: ast.expr) -> Optional[ast.expr]:
    """Infer an expression's type.
    @param expr: The expression's AST.
    @return: A type annotation, or None if the expression has no obvious type.
    """
    try:
        value: object = ast.literal_eval(expr)
    except ValueError:
        return None
    else:
        ann = _annotation_for_value(value)
        if ann is None:
            return None
        else:
            return ast.fix_missing_locations(ast.copy_location(ann, expr))

def _annotation_for_value(value: object) -> Optional[ast.expr]:
    if value is None:
        return None
    name = type(value).__name__
    if isinstance(value, (dict, list, set, tuple)):
        ann_elem = _annotation_for_elements(value)
        if isinstance(value, dict):
            ann_value = _annotation_for_elements(value.values())
            if ann_value is None:
                ann_elem = None
            elif ann_elem is not None:
                ann_elem = ast.Tuple(elts=[ann_elem, ann_value])
        if ann_elem is not None:
            if name == 'tuple':
                ann_elem = ast.Tuple(elts=[ann_elem, ast.Ellipsis()])
            return ast.Subscript(value=ast.Name(id=name),
                                 slice=ast.Index(value=ann_elem))
    return ast.Name(id=name)

def _annotation_for_elements(sequence: Iterable[object]) -> Optional[ast.expr]:
    names = set()
    for elem in sequence:
        ann = _annotation_for_value(elem)
        if isinstance(ann, ast.Name):
            names.add(ann.id)
        else:
            # Nested sequences are too complex.
            return None
    if len(names) == 1:
        name = names.pop()
        return ast.Name(id=name)
    else:
        # Empty sequence or no uniform type.
        return None

class _AnnotationStringParser(ast.NodeTransformer):
    """Implementation of L{unstring_annotation()}.

    When given an expression, the node returned by L{ast.NodeVisitor.visit()}
    will also be an expression.
    If any string literal contained in the original expression is either
    invalid Python or not a singular expression, L{SyntaxError} is raised.
    """

    def _parse_string(self, value: str) -> ast.expr:
        statements = ast.parse(value).body
        if len(statements) != 1:
            raise SyntaxError("expected expression, found multiple statements")
        stmt, = statements
        if isinstance(stmt, ast.Expr):
            # Expression wrapped in an Expr statement.
            expr = self.visit(stmt.value)
            assert isinstance(expr, ast.expr), expr
            return expr
        else:
            raise SyntaxError("expected expression, found statement")

    def visit_Subscript(self, node: ast.Subscript) -> ast.Subscript:
        value = self.visit(node.value)
        if isinstance(value, ast.Name) and value.id == 'Literal':
            # Literal[...] expression; don't unstring the arguments.
            slice = node.slice
        elif isinstance(value, ast.Attribute) and value.attr == 'Literal':
            # typing.Literal[...] expression; don't unstring the arguments.
            slice = node.slice
        else:
            # Other subscript; unstring the slice.
            slice = self.visit(node.slice)
        return ast.copy_location(ast.Subscript(value, slice, node.ctx), node)

    # For Python >= 3.8:

    def visit_Constant(self, node: ast.Constant) -> ast.expr:
        value = node.value
        if isinstance(value, str):
            return ast.copy_location(self._parse_string(value), node)
        else:
            const = self.generic_visit(node)
            assert isinstance(const, ast.Constant), const
            return const

    # For Python < 3.8:

    def visit_Str(self, node: ast.Str) -> ast.expr:
        return ast.copy_location(self._parse_string(node.s), node)
