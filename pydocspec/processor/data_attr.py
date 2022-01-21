"""
Helpers to populate attributes of `Data` instances. 
"""

from typing import List

import pydocspec
from pydocspec import _model, astroidutils

from . import helpers

def is_instance_variable(ob: _model.Data) -> bool:
    return _model.Data.Semantic.INSTANCE_VARIABLE in ob.semantic_hints

def is_class_variable(ob: _model.Data) -> bool:
    return _model.Data.Semantic.CLASS_VARIABLE in ob.semantic_hints

def is_module_variable(ob: _model.Data) -> bool:
    return isinstance(ob.parent, _model.Module)

def is_alias(ob: _model.Data) -> bool:
    return astroidutils.is_name(ob.value_ast)

def is_constant(ob: pydocspec.Data) -> bool: # still uses expand_name
    return ob.name.isupper() or helpers.is_using_typing_final(ob.datatype_ast, ob.parent)

def process_aliases(ob: pydocspec.Data) -> None:
    if ob.is_alias:
        assert ob.value is not None
        alias_to = ob.resolve_name(ob.value)
        if alias_to is not None:
            alias_to.aliases.append(ob)

def doc_sources(ob: pydocspec.ApiObject) -> List[pydocspec.ApiObject]:
    # must be called after mro()
    sources = [ob]
    if isinstance(ob, pydocspec.Inheritable): # type:ignore[unreachable]
        if isinstance(ob.parent, pydocspec.Class):
            for b in ob.parent.mro:
                base = b.get_member(ob.name)
                if base:
                    sources.append(base)
    return sources