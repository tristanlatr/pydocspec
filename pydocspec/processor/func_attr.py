"""
Helpers to populate attributes of `Function` instances. 
"""

import pydocspec
from pydocspec import _model, astroidutils


def is_property(ob: pydocspec.Function) -> bool:
    for deco in ob.decorations or ():
        name = astroidutils.node2fullname(deco.name_ast, ob.scope)
        if name and name.endswith(('property', 'Property')):
            return True
    return False

def is_property_setter(ob: _model.Function) -> bool:
    for deco in ob.decorations or ():
        name = astroidutils.node2dottedname(deco.name_ast)
        if name and len(name) == 2 and name[0]==ob.name and name[1] == 'setter':
            return True
    return False

def is_property_deleter(ob: _model.Function) -> bool:
    for deco in ob.decorations or ():
        name = astroidutils.node2dottedname(deco.name_ast)
        if name and len(name) == 2 and name[0]==ob.name and name[1] == 'deleter':
            return True
    return False

def is_async(ob: _model.Function) -> bool:
    return 'async' in (ob.modifiers or ())

def is_method(ob: _model.Function) -> bool:
    return isinstance(ob.scope, _model.Class)

def is_classmethod(ob: pydocspec.Function) -> bool:
    for deco in ob.decorations or ():
        if astroidutils.node2fullname(deco.name_ast, ob.scope) in ('classmethod', "abc.abstractclassmethod"):
            return True
    return False

def is_staticmethod(ob: pydocspec.Function) -> bool:
    for deco in ob.decorations or ():
        if astroidutils.node2fullname(deco.name_ast, ob.scope) in ('staticmethod', "abc.abstractstaticmethod"):
            return True
    return False

ABC_METHODS = {
    "abc.abstractproperty",
    "abc.abstractmethod",
    "abc.abstractclassmethod",
    "abc.abstractstaticmethod",
}

def is_abstractmethod(ob: pydocspec.Function) -> bool:
    for deco in ob.decorations or ():
        if astroidutils.node2fullname(deco.name_ast, ob.scope) in ABC_METHODS:
            return True
    return False