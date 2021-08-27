"""
Useful visitors for L{pydocspec.ApiObject} instances.
"""
try:
  from termcolor import colored as _colored
except ImportError as exc:
  def _colored(s, *args, **kwargs):  # type: ignore
    return str(s)

import typing as t

from pydocspec import ApiObject, HasMembers

from . import genericvisitor

# visitors

class FilterVisitor(genericvisitor.Visitor[ApiObject]):
  """
  Visits *objects* applying the *predicate*. If the predicate returrns a C{False} value, the object will be removed from it's containing list. 

  Usage::
    module: pydocspec.Module
    # removes entries starting by one underscore that are not dunder methods, aka private API.
    predicate = lambda ob: not ob.name.startswith("_") or ob.name.startswith("__") and ob.name.endswith("__")
    filter_visitor = FilterVisitor(predicate)
    module.walk(filter_visitor)
  """

  def __init__(self, predicate: t.Callable[[ApiObject], bool]):
    self.predicate = predicate

  def unknown_visit(self, ob: ApiObject) -> None:
    # if we are visiting a object, it means it has not been filtered out.
    self.apply_predicate_on_members(ob)

  def unknown_departure(self, ob: ApiObject) -> None:
    pass

  def apply_predicate_on_members(self, ob: ApiObject) -> None:
    if not isinstance(ob, HasMembers):
      return

    new_members = [m for m in ob.members if bool(self.predicate(m))==True]
    deleted_members = [m for m in ob.members if m not in new_members]

    # Remove the member from the ApiObjectsRoot as well
    for m in deleted_members:
      ob.root.all_objects.rmvalue(m.full_name, m)
    
    ob.members[:] = new_members


class PrintVisitor(genericvisitor.Visitor[ApiObject]):
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

  def unknown_visit(self, ob: ApiObject) -> None:
    depth = len(ob.path)-1
    tokens = dict(
      obj_type = _colored(type(ob).__name__, self._COLOR_MAP.get(type(ob).__name__)) if self.colorize else type(ob).__name__,
      obj_name = ob.name,
      obj_docstring = ob.docstring or "",
      obj_lineno = str(ob.location.lineno) if ob.location else 0,
      obj_filename = ob.location.filename or '' if ob.location else '',
      )
    print('| ' * depth + self.formatstr.format(**tokens))

  def unknown_departure(self, ob: ApiObject) -> None:
    pass
