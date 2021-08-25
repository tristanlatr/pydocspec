import pydocspec
from pydocspec.visitors import PrintVisitor, FilterVisitor, walk_ApiObject
from .fixtures import root1

def test_visitors(capsys, root1: pydocspec.ApiObjectsRoot) -> None:
    module = root1.root_modules[0]
    visitor = PrintVisitor(colorize=False)
    walk_ApiObject(module, visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :4 - Data: val
| | :5 - Data: alias
| | :6 - Function: __init__
| :8 - Data: saila
"""

    predicate = lambda ob: not isinstance(ob, pydocspec.Data) # removes any Data entries

    filter_visitor = FilterVisitor(predicate)
    walk_ApiObject(module, filter_visitor)
    walk_ApiObject(module, visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :6 - Function: __init__
"""
