"""
Various bits of reusable code related to `astroid.nodes.NodeNG` node processing.
"""

import functools
import itertools
import sys
from typing import Any, Dict, Iterable, Iterator, Optional, List, TYPE_CHECKING, Tuple, Type, Union, cast, overload
import inspect
import re
import attr

import astroid.nodes
import astroid.builder
import astroid.exceptions

from pydocspec.dottedname import DottedName

if TYPE_CHECKING:
    from pydocspec import ApiObject, _model
    from typing_extensions import Protocol
    class _NodeConstructorMethod(Protocol): # for mypy
        def __call__(self, *args: Any, **kwargs:Any) -> astroid.nodes.NodeNG: ...

def iter_fields(node: astroid.nodes.NodeNG) -> Iterator[Tuple[str, Any]]:
    """Given a node, get the fields names and their values. We need the fields names in NodeTransformer."""
    for field in node._astroid_fields:
        try:
            yield field, getattr(node, field)
        except AttributeError:
            pass

def iter_values(node: astroid.nodes.NodeNG) -> Iterator[astroid.nodes.NodeNG]:
    for _, value in iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, astroid.nodes.NodeNG):
                    yield item
        elif isinstance(value, astroid.nodes.NodeNG):
            yield value

class NodeVisitor:
    """
    A node visitor base class that walks the abstract syntax tree and calls a
    visitor function for every node found.  This function may return a value
    which is forwarded by the `visit` method.
    This class is meant to be subclassed, with the subclass adding visitor
    methods.
    Per default the visitor functions for the nodes are ``'visit_'`` +
    class name of the node.  So a `ClassDef` node visit function would
    be `visit_ClassDef` or alternatively `visit_classdef`.  
    This behavior can be changed by overriding
    the `visit` method.  If no visitor function exists for a node
    (return value `None`) the `generic_visit` visitor is used instead.
    Don't use the `NodeVisitor` if you want to apply changes to nodes during
    traversing.  For this a special visitor exists (`NodeTransformer`) that
    allows modifications.

    .. note:: Barely adapted from Python standard's library `ast` module.
    """

    def visit(self, node: astroid.nodes.NodeNG) -> Any:
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, getattr(self, method.lower(), self.generic_visit))
        return visitor(node)

    def generic_visit(self, node: astroid.nodes.NodeNG) -> None:
        """Called if no explicit visitor function exists for a node."""
        for value in iter_values(node):
            self.visit(value)

class NodeTransformer(NodeVisitor):
    """
    A `NodeVisitor` subclass that walks the abstract syntax tree and
    allows modification of nodes.
    The `NodeTransformer` will walk the AST and use the return value of the
    visitor methods to replace or remove the old node.  If the return value of
    the visitor method is ``None``, the node will be removed from its location,
    otherwise it is replaced with the return value.  The return value may be the
    original node in which case no replacement takes place.
    Here is an example transformer that rewrites all occurrences of name lookups
    (``foo``) to ``data['foo']``::
       class RewriteName(NodeTransformer):
           def visit_Name(self, node):
               return Subscript(
                   value=Name(id='data', ctx=Load()),
                   slice=Constant(value=node.id),
                   ctx=node.ctx
               )
    Keep in mind that if the node you're operating on has child nodes you must
    either transform the child nodes yourself or call the :meth:`generic_visit`
    method for the node first.
    For nodes that were part of a collection of statements (that applies to all
    statement nodes), the visitor may also return a list of nodes rather than
    just a single node.
    Usually you use the transformer like this::
       node = YourTransformer().visit(node)
    
    .. note:: Barely adapted from Python standard's library `ast` module.
    """

    def generic_visit(self, node: astroid.nodes.NodeNG) -> astroid.nodes.NodeNG:
        for field, old_value in iter_fields(node):
            if isinstance(old_value, list):
                new_values = []
                for value in old_value:
                    if isinstance(value, astroid.nodes.NodeNG):
                        value = self.visit(value)
                        if value is None:
                            continue
                        elif not isinstance(value, astroid.nodes.NodeNG):
                            new_values.extend(value)
                            continue
                    new_values.append(value)
                old_value[:] = new_values
            elif isinstance(old_value, astroid.nodes.NodeNG):
                new_node = self.visit(old_value)
                if new_node is None:
                    delattr(node, field)
                else:
                    setattr(node, field, new_node)
        return node

def literal_eval(node_or_string: Union[str, astroid.nodes.NodeNG]) -> Any:
    """
    Safely evaluate an expression node or a string containing a Python
    expression.  The string or node provided may only consist of the following
    Python literal structures: strings, bytes, numbers, tuples, lists, dicts,
    sets, booleans, and None.
    """
    if isinstance(node_or_string, str):
        _node = astroid.builder.parse(node_or_string.lstrip(" \t")).body
        if len(_node) != 1:
            raise ValueError(f'expected only one expression, found {len(_node)}')
        node_or_string = _node[0]
    if isinstance(node_or_string, astroid.nodes.Expr):
        node_or_string = node_or_string.value
    def _raise_malformed_node(node: astroid.nodes.NodeNG) -> None:
        msg = "malformed node or string"
        lno = node.lineno
        if lno:
            msg += f' on line {lno}'
        raise ValueError(msg + f': {node!r}')
    def _convert_num(node: astroid.nodes.NodeNG) -> Any:
        if not isinstance(node, astroid.nodes.Const) or type(node.value) not in (int, float, complex):
            _raise_malformed_node(node)
        return node.value
    def _convert_signed_num(node: astroid.nodes.NodeNG) -> Any:
        if isinstance(node, astroid.nodes.UnaryOp) and node.op in ("+", "-"):
            operand = _convert_num(node.operand)
            if node.op == "+":
                return + operand
            else:
                return - operand
        return _convert_num(node)
    def _convert(node:astroid.nodes.NodeNG) -> Any:
        if isinstance(node, astroid.nodes.Const):
            return node.value
        elif isinstance(node, astroid.nodes.Tuple):
            return tuple(map(_convert, node.elts))
        elif isinstance(node, astroid.nodes.List):
            return list(map(_convert, node.elts))
        elif isinstance(node, astroid.nodes.Set):
            return set(map(_convert, node.elts))
        elif (isinstance(node, astroid.nodes.Call) and isinstance(node.func, astroid.nodes.Name) and
              node.func.name == 'set' and node.args == node.keywords == []):
            return set()
        elif isinstance(node, astroid.nodes.Dict):
            return {_convert(k):_convert(v) for k,v in node.items}
        elif isinstance(node, astroid.nodes.BinOp) and node.op in ("+", "-"):
            left = _convert_signed_num(node.left)
            right = _convert_num(node.right)
            if isinstance(left, (int, float)) and isinstance(right, complex):
                if node.op == "+":
                    return left + right
                else:
                    return left - right
        return _convert_signed_num(node)
    return _convert(node_or_string)

def copy_location(new_node:astroid.nodes.NodeNG, old_node:astroid.nodes.NodeNG) -> astroid.nodes.NodeNG:
    """
    Copy source location (`lineno`, `col_offset`, `end_lineno`, and `end_col_offset`
    attributes) from *old_node* to *new_node* if possible, and return *new_node*.
    """
    for attr in 'lineno', 'col_offset', 'end_lineno', 'end_col_offset':
        value = getattr(old_node, attr, None)
        if value is not None:
            setattr(new_node, attr, value)
    return new_node

def fix_missing_locations(node:astroid.nodes.NodeNG) -> astroid.nodes.NodeNG:
    """
    When you compile a node tree with compile(), the compiler expects lineno and
    col_offset attributes for every node that supports them.  This is rather
    tedious to fill in for generated nodes, so this helper adds these attributes
    recursively where not already set, by setting them to the values of the
    parent node.  It works recursively starting at *node*.
    """
    def _fix(node:astroid.nodes.NodeNG, lineno:int, col_offset:int, end_lineno:int, end_col_offset:int) -> None:
        
        # a particularity in astroid is that Module instances are initiated with a linenumber of 0,
        # so we don't store linenumbers if equal to zero, we use default value which is 1.
        if node.lineno is None:
            node.lineno = lineno
        elif node.lineno!=0:
            lineno = node.lineno
    
        if node.end_lineno is None:
            node.end_lineno = end_lineno
        elif node.end_lineno!=0:
            end_lineno = node.end_lineno
    
        if node.col_offset is None:
            node.col_offset = col_offset
        else:
            col_offset = node.col_offset
    
        if node.end_col_offset is None:
            node.end_col_offset = end_col_offset
        else:
            end_col_offset = node.end_col_offset
            
        for child in node.get_children():
            _fix(child, lineno, col_offset, end_lineno, end_col_offset)
    _fix(node, 1, 0, 1, 0)
    return node

# end code copied from python

class _NodeFactory:
    """
    Easy create NodeNG instances. 

    Acts like every node arguments can be passed to the constructor method and calls `postinit` automatically with the required value.
    """

    _sig_cache: Dict[Type[astroid.nodes.NodeNG], inspect.Signature] = {}
    
    def __create_node(self, node_type: Type[astroid.nodes.NodeNG], *args: Any, **kwargs: Any) -> astroid.nodes.NodeNG:
        if node_type in self._sig_cache:
            sig = self._sig_cache[node_type]
        else:
            sig = inspect.signature(node_type.__init__)
            self._sig_cache[node_type] = sig
        
        init_args = args
        init_kwargs = {}
        for name in sig.parameters.keys():
            if name in kwargs:
                init_kwargs[name] = kwargs.pop(name)
        node = node_type(*init_args, **init_kwargs)
        if hasattr(node, 'postinit') and len(kwargs)>0:
            node.postinit(**kwargs)

        return node

    def __getattr__(self, name: str) -> '_NodeConstructorMethod':
        if not name in astroid.nodes.__dict__:
            raise AttributeError("unknown node {!r}".format(name))
        node_type = astroid.nodes.__dict__[name]
        assert issubclass(node_type, astroid.nodes.NodeNG), "not a node type {!r}".format(name)
        return functools.partial(self.__create_node, node_type)

nodefactory = _NodeFactory()
"""
Acts like every node arguments can be passed to the constructor method. 
"""

class ValueFormatter:
    """
    Formats values stored in AST expressions back to source code.
    Used for presenting default values of parameters and annotations. 

    :note: The default behaviour defers to `astroid.nodes.NodeNG.as_string`. 
        This should be overriden if you want more formatting functions, like outputing HTML tags. 
    """

    def __init__(self, value: astroid.nodes.NodeNG):
        self.value = value
    def __repr__(self) -> str:
        # Since astroid do not expose the typing information yet.
        try:
            return cast(str, self.value.as_string())
        except AttributeError:
            # Can raise AttributeError from node.as_string() as not all nodes have a visitor
            return '<ERROR>'

@attr.s(auto_attribs=True)
class SignatureBuilder:
    """
    Builds a signature, parameter by parameter, with customizable value formatter and signature classes.
    """
    signature_class: Type['inspect.Signature'] = attr.ib(default=inspect.Signature)
    value_formatter_class: Type['ValueFormatter'] = attr.ib(default=ValueFormatter)
    _parameters: List[inspect.Parameter] = attr.ib(factory=list, init=False)
    _return_annotation: Any = attr.ib(default=inspect.Signature.empty, init=False)

    def add_param(self, name: str, 
                  kind: inspect._ParameterKind, 
                  default: Optional[Any]=None,
                  annotation: Optional[Any]=None) -> None:
                    
        default_val = inspect.Parameter.empty if default is None else self.value_formatter_class(default)
        annotation_val = inspect.Parameter.empty if annotation is None else self.value_formatter_class(annotation)
        self._parameters.append(inspect.Parameter(name, kind, default=default_val, annotation=annotation_val))

    def set_return_annotation(self, annotation: Optional[Any]) -> None:
        self._return_annotation = inspect.Signature.empty if annotation is None else self.value_formatter_class(annotation)

    def get_signature(self) -> inspect.Signature:
        return self.signature_class(self._parameters, return_annotation=self._return_annotation)

def to_source(expr: astroid.nodes.NodeNG) -> str:
    """This function convert a node tree back into python sourcecode."""
    return repr(ValueFormatter(expr))

@overload
def node2dottedname(node: Union[astroid.nodes.Attribute, astroid.nodes.Name, astroid.nodes.AssignName, astroid.nodes.AssignAttr]) -> List[str]: ...
@overload
def node2dottedname(node: Optional[astroid.nodes.NodeNG], strict:bool=False) -> Optional[List[str]]:...
def node2dottedname(node: Optional[astroid.nodes.NodeNG], strict:bool=False) -> Optional[List[str]]:
    """
    Resove expression composed by `astroid.nodes.Attribute` and `astroid.nodes.Name` nodes to a list of names. 

    :note: Supports variants `AssignAttr` and `AssignName`.
    :note: Strips the subscript slice, i.e. `Generic[T]` -> `Generic`, except if scrict=True.
    """
    parts = []
    if isinstance(node, astroid.nodes.Subscript) and not strict:
        node = node.value
    while isinstance(node, (astroid.nodes.Attribute, astroid.nodes.AssignAttr)):
        parts.append(node.attrname or '')
        node = node.expr
    if isinstance(node, (astroid.nodes.Name, astroid.nodes.AssignName)):
        parts.append(node.name or '')
    else:
        return None
    parts.reverse()
    return parts

def node2fullname(expr: Optional[astroid.nodes.NodeNG], ctx: 'ApiObject') -> Optional[str]:
    """
    Return ``ctx.expand_name(name)`` if ``expr`` is a valid name, or ``None``.
    """
    dottedname = node2dottedname(expr)
    if dottedname is None:
        return None
    return ctx.expand_name('.'.join(dottedname)) 

def is_name(value: Optional[astroid.nodes.NodeNG]) -> bool:
    """
    A name is an expression composed by `astroid.nodes.Attribute` and `astroid.nodes.Name` nodes
    :returns: `True` if value is a valid name.
    """
    return node2dottedname(value, strict=True) is not None

def is_type_guarded(node: Optional[astroid.nodes.NodeNG], ctx: '_model.ApiObject') -> bool:
    """Return True if one of the parent(s) of a node is a typing guard."""
    if getattr(ctx, 'is_type_guarded', None) is True:
        return True
    if node is None or isinstance(node, astroid.nodes.Module):
        return False
    maybe_ifstmt = node.parent
    type_guarded = is_type_guard(maybe_ifstmt)
    return type_guarded or is_type_guarded(maybe_ifstmt.parent, ctx)

def is_type_guard(node: astroid.nodes.If) -> bool:
    """Return True if the If statement is a typing guard."""
    ifstmt = node
    return isinstance(ifstmt, astroid.nodes.If) and isinstance(
            ifstmt.test, (astroid.nodes.Name, astroid.nodes.Attribute)
        ) and (node2dottedname(ifstmt.test)[-1]or(None,)) == "TYPE_CHECKING"

def bind_args(sig: inspect.Signature, call: astroid.nodes.Call) -> inspect.BoundArguments:
    """
    Binds the arguments of a function call to that function's signature.
    :raise TypeError: If the arguments do not match the signature.
    """
    # TODO: Se it we can infer **kwargs with astroid, maybe we can do something like kw.value.infer() when kw.arg is None -> Dict -> add them to kwargs variable.
    kwargs = {
        kw.arg: kw.value
        for kw in call.keywords
        # When keywords are passed using '**kwargs', the 'arg' field will
        # be None. We don't currently support keywords passed that way.
        if kw.arg is not None
        }
    return sig.bind(*call.args, **kwargs)

def extract_expr(expr: str, filename: Optional[str] = None, allow_stmt: bool = False) -> astroid.nodes.NodeNG:
    """
    Convert a python **expression** to ast. 

    Can raise `SyntaxError` if invalid python sytax or if got statements instead of expression.
    """
    try:
        statements = astroid.builder.parse(expr, path=filename or '<unknown>').body
    except astroid.exceptions.AstroidSyntaxError as e:
        raise SyntaxError(str(e)) from e
    if len(statements) != 1:
        raise SyntaxError("Expected expression, got multiple statements")
    stmt, = statements
    if isinstance(stmt, astroid.nodes.Expr):
        # Expression wrapped in an Expr statement.
        assert isinstance(stmt.value, astroid.nodes.NodeNG), stmt.value
        return stmt.value
    elif not allow_stmt:
        raise SyntaxError("Expected expression, got statement")
    else:
        return stmt

def extract_final_subscript(annotation: astroid.nodes.Subscript) -> astroid.nodes.NodeNG:
    """
    Extract the "str" part from annotations like  "Final[str]".

    @raises ValueError: If the "Final" annotation is not valid.
    """ 
    ann_slice = annotation.slice
    if isinstance(ann_slice, (astroid.nodes.ExtSlice, astroid.nodes.Slice, astroid.nodes.Tuple)):
        raise ValueError("Annotation is invalid, it should not contain slices.")
    else:
        assert isinstance(ann_slice, astroid.nodes.NodeNG)
        return ann_slice

def unstring_annotation(node: astroid.nodes.NodeNG) -> astroid.nodes.NodeNG:
    """Replace all strings in the given expression by parsed versions.
    :return: The unstringed node. If parsing fails, an error is logged
        and the original node is returned.
    
    :raises SyntaxError: if the annotation is invalid.
    """
    try:
        expr = _AnnotationStringParser().visit(node)
    except (SyntaxError,) as ex:
        raise SyntaxError(f'error in annotation: {ex}') from ex
    else:
        assert isinstance(expr, astroid.nodes.NodeNG), expr
        return expr

def infer_type_annotation(expr: Optional[astroid.nodes.NodeNG]) -> Optional[astroid.nodes.NodeNG]:
    """Infer an expression's type.
    :param expr: The expression's AST.
    :return: A type annotation, or None if the expression has no obvious type.
    """
    if expr is None:
        return None
    try:
        value: object = literal_eval(expr)
    except ValueError:
        # TODO: Use astroid pytype()
        return None
    else:
        ann = _annotation_for_value(value)
        if ann is None:
            return None
        else:
            return fix_missing_locations(copy_location(ann, expr))

def _annotation_for_value(value: object) -> Optional[astroid.nodes.NodeNG]:
    if value is None:
        return None
    name = type(value).__name__
    
    if isinstance(value, (dict, list, set, tuple, frozenset)):
        ann_elem = _annotation_for_elements(value)
        
        if isinstance(value, dict):
            ann_value = _annotation_for_elements(value.values())
            if ann_value is None:
                ann_elem = None
            elif ann_elem is not None:
                ann_elem = nodefactory.Tuple(elts=[ann_elem, ann_value])
        
        if ann_elem is not None:
            if name == 'tuple':
                ann_elem = nodefactory.Tuple(elts=[ann_elem, astroid.nodes.Const(value=...)])
            
            return nodefactory.Subscript(value=astroid.nodes.Name(name=name),
                                 slice=ann_elem)

    return astroid.nodes.Name(name=name)

def _annotation_for_elements(sequence: Iterable[object]) -> Optional[astroid.nodes.NodeNG]:
    names = set()
    for elem in sequence:
        ann = _annotation_for_value(elem)
        if isinstance(ann, astroid.nodes.Name):
            names.add(ann.name)
        elif isinstance(ann, astroid.nodes.Subscript):
            # Nested sequences.
            names.add(cast(astroid.nodes.Name, ann.value).name)
    if len(names) == 1:
        name = names.pop()
        return astroid.nodes.Name(name=name)
    else:
        # Empty sequence or no uniform type.
        return None

class _AnnotationStringParser(NodeTransformer):
    """Implementation of `unstring_annotation`.

    When given an expression, the node returned by `visit()` will also be an expression.
    If any string literal contained in the original expression is either
    invalid Python or not a singular expression, `SyntaxError` or `astroid.exceptions.AstroidError` is raised.
    """

    def visit_Subscript(self, node: astroid.nodes.Subscript) -> astroid.nodes.Subscript:
        value = self.visit(node.value)
        if isinstance(value, astroid.nodes.Name) and value.name == 'Literal':
            # Literal[...] expression; don't unstring the arguments.
            slice = node.slice
        elif isinstance(value, astroid.nodes.Attribute) and value.attrname == 'Literal':
            # typing.Literal[...] expression; don't unstring the arguments.
            slice = node.slice
        else:
            # Other subscript; unstring the slice.
            slice = self.visit(node.slice)
        return copy_location(nodefactory.Subscript(value=value, slice=slice), node)

    def visit_Const(self, node: astroid.nodes.Const) -> astroid.nodes.NodeNG:
        value = node.value
        if isinstance(value, str):
            return copy_location(extract_expr(value), node)
        else:
            const = self.generic_visit(node)
            assert isinstance(const, astroid.nodes.Const), const
            return const

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def resolve_import_alias(name:str, import_names:Iterable[Tuple[str, Union[str,None]]]) -> str:
    """Resolve a name from an aliased import to its original name.

    :param name: The potentially aliased name to resolve.
    :param import_names: The pairs of original names and aliases
        from the import.
    :returns: The original name.
    """
    resolved_name = name

    for import_name, imported_as in import_names:
        if import_name == name:
            break
        if imported_as == name:
            resolved_name = import_name
            break

    return resolved_name

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def get_full_import_name(import_from:astroid.nodes.ImportFrom, name:str) -> str:
    """Get the full path of a name from a ``from x import y`` statement.

    :param import_from: The astroid node to resolve the name of.
    :param name:
    :returns: The full import path of the name.
    """
    partial_basename = resolve_import_alias(name, import_from.names)

    module_name = import_from.modname
    if import_from.level:
        module = import_from.root()
        assert isinstance(module, astroid.nodes.Module)
        module_name = module.relative_to_absolute_name(
            import_from.modname, level=import_from.level
        )

    return "{}.{}".format(module_name, partial_basename)

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def resolve_qualname(
        ctx: astroid.nodes.NodeNG, 
        basename: str) -> str:
    """
    Resolve a basename to get its fully qualified name.

    :param ctx: The node representing the base name.
    :param basename: The partial base name to resolve.
    :returns: The fully resolved base name.
    """
    full_basename = basename

    top_level_name = DottedName(re.sub(r"\(.*\)", "", basename))[0]
    
    # re.sub(r"\(.*\)", "", basename).split(".", 1)[0]
    # Disable until pylint uses astroid 2.7
    if isinstance(
        ctx, astroid.nodes.node_classes.LookupMixIn  # pylint: disable=no-member
    ):
        lookup_node = ctx
    else:
        lookup_node = ctx.scope()

    assigns = lookup_node.lookup(top_level_name)[1]

    for assignment in assigns:
        if isinstance(assignment, astroid.nodes.ImportFrom):
            import_name = get_full_import_name(assignment, top_level_name)
            full_basename = basename.replace(top_level_name, import_name, 1)
            break
        if isinstance(assignment, astroid.nodes.Import):
            import_name = resolve_import_alias(top_level_name, assignment.names)
            full_basename = basename.replace(top_level_name, import_name, 1)
            break
        if isinstance(assignment, astroid.nodes.ClassDef):
            full_basename = assignment.qname()
            break
        if isinstance(assignment, astroid.nodes.AssignName):
            full_basename = "{}.{}".format(assignment.scope().qname(), assignment.name)

    full_basename = re.sub(r"\(.*\)", "()", full_basename)

    if full_basename.startswith("builtins."):
        return full_basename[len("builtins.") :]

    if full_basename.startswith("__builtin__."):
        return full_basename[len("__builtin__.") :]

    return full_basename

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def _is_ellipsis(node:astroid.nodes.NodeNG) -> bool:
    if sys.version_info < (3, 8):
        return isinstance(node, astroid.Ellipsis)

    return isinstance(node, astroid.Const) and node.value == Ellipsis #type:ignore[unreachable]

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def _iter_args(args: List[astroid.nodes.AssignName], 
               annotations: List[astroid.nodes.AssignName], 
               defaults: List[astroid.nodes.AssignName]) -> Iterator[Tuple[str, 
                                           Optional[astroid.nodes.NodeNG], 
                                           Optional[astroid.nodes.NodeNG]]]:
    
    default_offset = len(args) - len(defaults)
    packed = itertools.zip_longest(args, annotations)
    for i, (arg, annotation) in enumerate(packed):
        default = None
        if defaults is not None and i >= default_offset:
            if defaults[i - default_offset] is not None:
                default = defaults[i - default_offset]
        name = arg.name
        yield (name, annotation, default)

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def merge_annotations(annotations: Iterable[Optional[astroid.nodes.NodeNG]], 
                      comment_annotations: Iterable[Optional[astroid.nodes.NodeNG]]) -> Iterator[Optional[astroid.nodes.NodeNG]]:
    for ann, comment_ann in itertools.zip_longest(annotations, comment_annotations):
        if ann and not _is_ellipsis(ann):
            yield ann
        elif comment_ann and not _is_ellipsis(comment_ann):
            yield comment_ann
        else:
            yield None

# The MIT License (MIT)
# Copyright (c) 2015 Read the Docs, Inc
def build_signature(func: Union[astroid.nodes.AsyncFunctionDef, 
                            astroid.nodes.FunctionDef]) -> inspect.Signature:
    """
    Builds `inspect.Signature` representing this function's parameters and return value.

    :raises ValueError: If the function has invalid parameters.
    """
    args_node: astroid.nodes.Arguments = func.args
    result: List[inspect.Parameter] = []
    positional_only_defaults: List[astroid.nodes.NodeNG] = []
    positional_or_keyword_defaults = args_node.defaults
    if args_node.defaults:
        args = args_node.args or []
        positional_or_keyword_defaults = args_node.defaults[-len(args) :]
        positional_only_defaults = args_node.defaults[
            : len(args_node.defaults) - len(args)
        ]

    plain_annotations = args_node.annotations or ()
    func_comment_annotations = func.type_comment_args or ()
    comment_annotations = args_node.type_comment_posonlyargs
    comment_annotations += args_node.type_comment_args or []
    comment_annotations += args_node.type_comment_kwonlyargs
    annotations = list(
        merge_annotations(
            plain_annotations,
            merge_annotations(func_comment_annotations, comment_annotations),
        )
    )
    annotation_offset = 0

    if args_node.posonlyargs:
        posonlyargs_annotations = args_node.posonlyargs_annotations
        if not any(args_node.posonlyargs_annotations):
            num_args = len(args_node.posonlyargs)
            posonlyargs_annotations = annotations[
                annotation_offset : annotation_offset + num_args
            ]

        for arg, annotation, default in _iter_args(
            args_node.posonlyargs, posonlyargs_annotations, positional_only_defaults
        ):
            result.append(inspect.Parameter(name=arg, 
                kind=inspect.Parameter.POSITIONAL_ONLY,
                default=default or inspect.Parameter.empty,
                annotation=annotation or inspect.Parameter.empty, ))

        if not any(args_node.posonlyargs_annotations):
            annotation_offset += num_args

    if args_node.args:
        num_args = len(args_node.args)
        for arg, annotation, default in _iter_args(
            args_node.args,
            annotations[annotation_offset : annotation_offset + num_args],
            positional_or_keyword_defaults,
        ):
            result.append(inspect.Parameter(name=arg, 
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default or inspect.Parameter.empty,
                annotation=annotation or inspect.Parameter.empty, ))

        annotation_offset += num_args

    if args_node.vararg:
        annotation = None
        if args_node.varargannotation:
            annotation = args_node.varargannotation
        elif len(annotations) > annotation_offset and annotations[annotation_offset]:
            annotation = annotations[annotation_offset]
            annotation_offset += 1
        result.append(inspect.Parameter(name=args_node.vararg, 
                kind=inspect.Parameter.VAR_POSITIONAL,
                default=inspect.Parameter.empty,
                annotation=annotation or inspect.Parameter.empty, ))

    if args_node.kwonlyargs:
        kwonlyargs_annotations = args_node.kwonlyargs_annotations
        if not any(args_node.kwonlyargs_annotations):
            num_args = len(args_node.kwonlyargs)
            kwonlyargs_annotations = annotations[
                annotation_offset : annotation_offset + num_args
            ]

        for arg, annotation, default in _iter_args(
            args_node.kwonlyargs,
            kwonlyargs_annotations,
            args_node.kw_defaults,
        ):
            result.append(inspect.Parameter(name=arg, 
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default or inspect.Parameter.empty,
                annotation=annotation or inspect.Parameter.empty, ))

        if not any(args_node.kwonlyargs_annotations):
            annotation_offset += num_args

    if args_node.kwarg:
        annotation = None
        if args_node.kwargannotation:
            annotation = args_node.kwargannotation
        elif len(annotations) > annotation_offset and annotations[annotation_offset]:
            annotation = annotations[annotation_offset]
            annotation_offset += 1
        result.append(inspect.Parameter(name=args_node.kwarg, 
                kind=inspect.Parameter.VAR_KEYWORD,
                default=inspect.Parameter.empty,
                annotation=annotation or inspect.Parameter.empty, ))
    
    return inspect.Signature(result, return_annotation=func.returns if func.returns else inspect.Signature.empty)
