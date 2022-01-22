"""
Helpers to populate attributes of `Data` instances. 
"""

from typing import List

import pydocspec
from pydocspec import _model, astroidutils

from . import helpers

def is_instance_variable(ob: _model.Data) -> bool:
    """INSTANCE_VARIABLE in ob.semantic_hints?"""
    return _model.Data.Semantic.INSTANCE_VARIABLE in ob.semantic_hints

def is_class_variable(ob: _model.Data) -> bool:
    """CLASS_VARIABLE in semantic_hints?"""
    return _model.Data.Semantic.CLASS_VARIABLE in ob.semantic_hints

def is_module_variable(ob: _model.Data) -> bool:
    """check if the parent of this data is a module."""
    return isinstance(ob.parent, _model.Module)

def is_alias(ob: _model.Data) -> bool:
    """check if the value of this data is an alias to another name."""
    return astroidutils.is_name(ob.value_ast)

def is_constant(ob: pydocspec.Data) -> bool: # still uses expand_name
    """a constant is a all caps varaible or if using Final qualifier, uses name resolution."""
    return ob.name.isupper() or helpers.is_using_typing_final(ob.datatype_ast, ob.parent)

def process_aliases(ob: pydocspec.Data) -> None:
    """if the data is an alias, try to resolve it to an apiobject and add `ob` to the 
    list of aliases of the targeted object, uses name resolution."""
    if ob.is_alias:
        assert ob.value is not None
        alias_to = ob.resolve_name(ob.value)
        if alias_to is not None and ob not in alias_to.aliases:
            alias_to.aliases.append(ob)

def doc_sources(ob: pydocspec.ApiObject) -> List[pydocspec.ApiObject]:
    """all sources of documentation for this data/function, including self and others coming from superclasses. 
    must be called after mro"""
    sources = [ob]
    if isinstance(ob, pydocspec.Inheritable): # type:ignore[unreachable]
        if isinstance(ob.parent, pydocspec.Class):
            for b in ob.parent.mro:
                base = b.get_member(ob.name)
                if base:
                    sources.append(base)
    return sources