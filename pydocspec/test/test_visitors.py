import pydocspec
from pydocspec import visitors
from pydocspec import genericvisitor
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
| :0 - Function: f
"""

def test_CustomizableVisitor(capsys: CapSys, root1: pydocspec.TreeRoot) -> None:

    def _unknown_visit(self, ob: 'pydocspec.ApiObject') -> None:
        name = self.__class__.__name__ + ' '*(20-len(self.__class__.__name__))
        print(f'{name}.visit({ob.full_name})')
    def _unknown_departure(self, ob: 'pydocspec.ApiObject') -> None:
        name = self.__class__.__name__ + ' '*(20-len(self.__class__.__name__))
        print(f'{name}.depart({ob.full_name})')

    class MainVistor(visitors.ApiObjectVisitor):
        unknown_visit=_unknown_visit
        unknown_departure=_unknown_departure

    class Before(visitors.ApiObjectVisitorExt):
        when = genericvisitor.When.BEFORE
        unknown_visit=_unknown_visit
        unknown_departure=_unknown_departure
    
    class After(visitors.ApiObjectVisitorExt):
        when = genericvisitor.When.AFTER
        unknown_visit=_unknown_visit
        unknown_departure=_unknown_departure
    
    
    module = root1.root_modules[0]
    ext = genericvisitor.VisitorExtensionList()
    ext.add(Before(), After())
    module.walkabout(MainVistor(ext))
    captured = capsys.readouterr().out

    # Module hierarchy:
    # :0 - Module: a
    # | :1 - Indirection: Union
    # | :2 - Class: foo
    # | | :4 - Data: val
    # | | :5 - Data: alias
    # | | :6 - Function: __init__
    # | :8 - Data: saila

    assert captured == """\
Before              .visit(a)
MainVistor          .visit(a)
After               .visit(a)
Before              .visit(a.Union)
MainVistor          .visit(a.Union)
After               .visit(a.Union)
After               .depart(a.Union)
MainVistor          .depart(a.Union)
Before              .depart(a.Union)
Before              .visit(a.foo)
MainVistor          .visit(a.foo)
After               .visit(a.foo)
Before              .visit(a.foo.val)
MainVistor          .visit(a.foo.val)
After               .visit(a.foo.val)
After               .depart(a.foo.val)
MainVistor          .depart(a.foo.val)
Before              .depart(a.foo.val)
Before              .visit(a.foo.alias)
MainVistor          .visit(a.foo.alias)
After               .visit(a.foo.alias)
After               .depart(a.foo.alias)
MainVistor          .depart(a.foo.alias)
Before              .depart(a.foo.alias)
Before              .visit(a.foo.__init__)
MainVistor          .visit(a.foo.__init__)
After               .visit(a.foo.__init__)
After               .depart(a.foo.__init__)
MainVistor          .depart(a.foo.__init__)
Before              .depart(a.foo.__init__)
After               .depart(a.foo)
MainVistor          .depart(a.foo)
Before              .depart(a.foo)
Before              .visit(a.saila)
MainVistor          .visit(a.saila)
After               .visit(a.saila)
After               .depart(a.saila)
MainVistor          .depart(a.saila)
Before              .depart(a.saila)
After               .depart(a)
MainVistor          .depart(a)
Before              .depart(a)
"""