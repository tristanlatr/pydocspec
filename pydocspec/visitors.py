"""
Useful visitors for AST and `pydocspec.ApiObject` instances.
"""
try:
  from termcolor import colored as _colored
except ImportError as exc:
  def _colored(s, *args, **kwargs):  # type: ignore
    return str(s)

import os
from pathlib import Path
import typing as t

import astroid.nodes
import docspec

# should not import pydocspec or _model

from . import genericvisitor, astroidutils
import pydocspec

if t.TYPE_CHECKING:
  from ._model import ApiObject
  import pydocspec

# AST visitors

class AstVisitor(genericvisitor.PartialVisitor[astroid.nodes.NodeNG], 
                 genericvisitor.CustomizableVisitor[astroid.nodes.NodeNG]):
  get_children = lambda _,ob: astroidutils.iter_values(ob)

  # def get_children(self, node: astroid.nodes.NodeNG) -> None:
  #     """
  #     Visit the nested nodes in the body of a node.
  #     """
  #     body: t.Optional[t.Sequence[astroid.nodes.NodeNG]] = getattr(node, 'body', None)
  #     if body is not None:
  #         for child in body:
  #             yield child

class AstVisitorExt(genericvisitor.VisitorExtension[astroid.nodes.NodeNG]):
  get_children = lambda _,ob: astroidutils.iter_values(ob)

def iter_fields(ob: 'pydocspec.ApiObject') -> t.Iterator[t.Tuple[str, t.Any]]:
  """
  Iter each values of the API object fields. Fields are listed in the _spec_fields class varaible.
  """
  for f in getattr(ob, '_spec_fields', tuple()):
      assert hasattr(ob, f), f"No field {f!r} defined on {ob!r}"
      yield f, getattr(ob, f)

# ApiObject visitors

class _docspecApiObjectVisitor(genericvisitor.Visitor[docspec.ApiObject]):
  # adapter for docspec
  def get_children(cls, ob: docspec.ApiObject) -> t.Iterable[docspec.ApiObject]:
      if isinstance(ob, (docspec.Class, docspec.Module)):
        return ob.members
      else:
        return ()

class ApiObjectVisitor(genericvisitor.CustomizableVisitor['pydocspec.ApiObject']):
  get_children = lambda _,ob: ob._members()

class ApiObjectVisitorExt(genericvisitor.VisitorExtension['pydocspec.ApiObject']):
  get_children = lambda _,ob: ob._members()

class FilterVisitor(ApiObjectVisitor):
  """
  Visits *objects* applying the *predicate*. If the predicate returrns a ``False`` value, the object will be removed from it's containing list. 

  Usage::
    module: pydocspec.Module
    # removes entries starting by one underscore that are not dunder methods, aka private API.
    predicate = lambda ob: not ob.name.startswith("_") or ob.name.startswith("__") and ob.name.endswith("__")
    filter_visitor = FilterVisitor(predicate)
    filter_visitor.walk(module)
  """

  def __init__(self, predicate: t.Callable[['pydocspec.ApiObject'], bool]):
    super().__init__()
    self.predicate = predicate

  def unknown_visit(self, ob: 'pydocspec.ApiObject') -> None:
    # if we are visiting a object, it means it has not been filtered out.
    self.apply_predicate_on_members(ob)

  def unknown_departure(self, ob: 'pydocspec.ApiObject') -> None:
    pass

  def apply_predicate_on_members(self, ob: 'pydocspec.ApiObject') -> None:
    new_members = [m for m in ob._members() if bool(self.predicate(m))==True]
    deleted_members = [m for m in ob._members() if m not in new_members]

    # Remove the member from the TreeRoot as well
    for m in deleted_members:
      m.remove()

class ReprVisitor(ApiObjectVisitor):
  # for test purposes
  def __init__(self) -> None:
    super().__init__()
    self.repr: str = ''
  def unknown_visit(self, ob: 'pydocspec.ApiObject') -> None:
    depth = len(ob.path)-1
    # dataclasses.asdict(ob) can't work on cycles references, so we iter the fields
    other_fields = dict(list(iter_fields(ob)))
    other_fields.pop('name')
    other_fields.pop('location')
    other_fields.pop('docstring')
    try: other_fields.pop('members')
    except KeyError: pass
    other_fields_repr = ""
    for k,v in other_fields.items():
      if k.endswith('_ast'): # ignore ast fields
        continue
      if v: # not None, not empty list
        other_fields_repr += ", "
        _repr = repr(v) if isinstance(v, (str, bool)) else str(v)
        if isinstance(v, Path):
          _repr = f"{_repr.split(os.sep)[-1]}"
        other_fields_repr += k + ": " + _repr
    tokens = dict(
      type = type(ob).__name__,
      name = ob.name,
      lineno = str(ob.location.lineno) if ob.location else 0,
      filename = ob.location.filename or '' if ob.location else '',
      other = other_fields_repr)
    self.repr += '| ' * depth + "- {type} '{name}' at l.{lineno}{other}".format(**tokens) + "\n"

class PrintVisitor(ApiObjectVisitor):
  """
  Visit objects and print each object with the defined format string. 
  Available substitutions are: 
    - "{obj_type}" (colored)
    - "{obj_name}"
    - "{obj_docstring}"
    - "{obj_lineno}"
    - "{obj_filename}"
  The default format string is: ":{obj_lineno} - {obj_type}: {obj_name}"

  Usage::
    module: pydocspec.Module
    module.walk(PrintVisitor())
  """

  _COLOR_MAP = {
    'Module': 'magenta',
    'Class': 'cyan',
    'Function': 'yellow',
    'Data': 'blue',
    'Indirection': 'dark_blue',
  }

  def __init__(self, formatstr: str = ":{obj_lineno} - {obj_type}: {obj_name}", 
               colorize: bool = True):
        super().__init__()
        self.formatstr = formatstr
        self.colorize = colorize

  def unknown_visit(self, ob: 'pydocspec.ApiObject') -> None:
    depth = len(ob.path)-1
    tokens = dict(
      obj_type = _colored(type(ob).__name__, self._COLOR_MAP.get(type(ob).__name__)) if self.colorize else type(ob).__name__,
      obj_name = ob.name,
      obj_docstring = ob.docstring or "",
      obj_lineno = str(ob.location.lineno) if ob.location else 0,
      obj_filename = ob.location.filename or '' if ob.location else '',
      )
    print('| ' * depth + self.formatstr.format(**tokens))

  def unknown_departure(self, ob: 'pydocspec.ApiObject') -> None:
    pass
