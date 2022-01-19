import pydocspec
from pydocspec.visitors import PrintVisitor, FilterVisitor
from .fixtures import root1, root3, root4
from . import CapSys

def test_visitors(capsys:CapSys, root1: pydocspec.TreeRoot) -> None:
    module = root1.root_modules[0]
    visitor = PrintVisitor(colorize=False)
    module.walk(visitor)
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
    module.walk(filter_visitor)

    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :6 - Function: __init__
"""

def test_visitors2(capsys: CapSys, root3: pydocspec.TreeRoot) -> None:
    module = root3.root_modules[0]
    visitor = PrintVisitor(colorize=False)
    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :4 - Data: _val
| | :5 - Data: _alias
| | :6 - Function: __init__
| :8 - Data: saila
"""
    # removes entries starting by one underscore that are not dunder methods, aka private API.
    predicate = lambda ob: not ob.name.startswith("_") or ob.name.startswith("__") and ob.name.endswith("__")
    filter_visitor = FilterVisitor(predicate)
    module.walk(filter_visitor)

    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :6 - Function: __init__
| :8 - Data: saila
"""

def test_visitors3(capsys: CapSys, root1: pydocspec.TreeRoot, root4:pydocspec.TreeRoot) -> None:
    module = root1.root_modules[0]
    visitor = PrintVisitor(colorize=False)
    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :2 - Class: foo
| | :4 - Data: val
| | :5 - Data: alias
| | :6 - Function: __init__
| :8 - Data: saila
"""
    assert module.expand_name('saila') == 'a.foo.val'

    # removes the foo class
    predicate = lambda ob: False if ob.name=="foo" else True
    filter_visitor = FilterVisitor(predicate)
    module.walk(filter_visitor)

    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :8 - Data: saila
"""
    assert module.expand_name('saila') == 'foo.alias'

    module.get_member('saila').add_siblings(root4.all_objects['a.f'])

    module.walk(visitor)
    captured = capsys.readouterr().out
    assert captured == """:0 - Module: a
| :1 - Indirection: Union
| :8 - Data: saila
| :-1 - Function: f
"""