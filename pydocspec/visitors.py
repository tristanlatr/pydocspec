"""
Useful visitors for `pydocspec.ApiObject` instances.
"""
try:
  from termcolor import colored as _colored
except ImportError as exc:
  def _colored(s, *args, **kwargs):  # type: ignore
    return str(s)

import dataclasses
import os
from pathlib import Path
import typing as t

# should not import pydocspec or _model

from . import genericvisitor

if t.TYPE_CHECKING:
  from ._model import ApiObject

def iter_fields(ob: 'ApiObject') -> t.Iterator[t.Tuple[str, t.Any]]:
  """
  Iter each values of the object fields. Fields are listed in the _spec_fields class varaible.
  """
  for f in getattr(ob, '_spec_fields', tuple()):
      assert hasattr(ob, f), f"No field {f!r} defined on {ob!r}"
      yield f, getattr(ob, f)

# visitors

class FilterVisitor(genericvisitor.Visitor['ApiObject']):
  """
  Visits *objects* applying the *predicate*. If the predicate returrns a ``False`` value, the object will be removed from it's containing list. 

  Usage::
    module: pydocspec.Module
    # removes entries starting by one underscore that are not dunder methods, aka private API.
    predicate = lambda ob: not ob.name.startswith("_") or ob.name.startswith("__") and ob.name.endswith("__")
    filter_visitor = FilterVisitor(predicate)
    module.walk(filter_visitor)
  """

  def __init__(self, predicate: t.Callable[['ApiObject'], bool]):
    self.predicate = predicate

  def unknown_visit(self, ob: 'ApiObject') -> None:
    # if we are visiting a object, it means it has not been filtered out.
    self.apply_predicate_on_members(ob)

  def unknown_departure(self, ob: 'ApiObject') -> None:
    pass

  def apply_predicate_on_members(self, ob: 'ApiObject') -> None:
    new_members = [m for m in ob._members() if bool(self.predicate(m))==True]
    deleted_members = [m for m in ob._members() if m not in new_members]

    # Remove the member from the TreeRoot as well
    for m in deleted_members:
      m.remove()

class ReprVisitor(genericvisitor.Visitor['ApiObject']):
  # for test purposes
  def __init__(self) -> None:
    self.repr: str = ''
  def unknown_visit(self, ob: 'ApiObject') -> None:
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

class PrintVisitor(genericvisitor.Visitor['ApiObject']):
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
        self.formatstr = formatstr
        self.colorize = colorize

  def unknown_visit(self, ob: 'ApiObject') -> None:
    depth = len(ob.path)-1
    tokens = dict(
      obj_type = _colored(type(ob).__name__, self._COLOR_MAP.get(type(ob).__name__)) if self.colorize else type(ob).__name__,
      obj_name = ob.name,
      obj_docstring = ob.docstring or "",
      obj_lineno = str(ob.location.lineno) if ob.location else 0,
      obj_filename = ob.location.filename or '' if ob.location else '',
      )
    print('| ' * depth + self.formatstr.format(**tokens))

  def unknown_departure(self, ob: 'ApiObject') -> None:
    pass
