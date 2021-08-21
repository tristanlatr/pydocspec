"""
Extends docspec for python specific usages.
"""

from typing import Iterator, List, Mapping, Optional
import ast

from cached_property import cached_property

import docspec

# __all__ = [
#   'Location',
#   'Decoration',
#   'Argument',
#   'ApiObject',
#   'Data',
#   'Function',
#   'Class',
#   'Module',
#   'load_module',
#   'load_modules',
#   'dump_module',
#   'filter_visit',
#   'visit',
#   'ReverseMap',
#   'get_member',
# ]

class ApiObject(docspec.ApiObject):

    @cached_property
    def full_name(self) -> str:
        return '.'.join(ob.name for ob in self.path)
    
    @cached_property
    def doc_sources(self) -> List['ApiObject']:
        ...
    
    @cached_property
    def module(self) -> 'Module':
        ...

    def resolve_name(self, name: str) -> Optional['ApiObject']:
        ...

    def expand_name(self, name: str) -> str:
        ...

class Data(docspec.Data):

    @cached_property
    def datatype_ast(self) -> ast.expr:
        ...
    
    @cached_property
    def value_ast(self) -> ast.expr:
        ...

    @cached_property
    def is_attrs_attribute(self) -> bool:
        ...
    
    @cached_property
    def is_alias(self) -> bool:
        ...

class Class(docspec.Class):

    def all_bases(self, include_self: bool = False) -> Iterator['Class']:
        ...

    def find(self, name: str) -> Optional[ApiObject]:
        ...
    
    @cached_property
    def constructor_params(self) -> Mapping[str, Optional[ast.expr]]:
        ...

    @cached_property
    def is_exception(self) -> bool:
        ...

    @cached_property
    def uses_attrs(self) -> bool:
        ...

    @cached_property
    def uses_attrs_auto_attribs(self) -> bool:
        ...

class Function(docspec.Function):
    
    @cached_property
    def return_type_ast(self) -> Optional[ast.expr]:
        ...

    @cached_property
    def is_property(self) -> bool:
        ...
    
    @cached_property
    def is_async(self) -> bool:
        ...
    
    @cached_property
    def is_method(self) -> bool:
        ...
    
    @cached_property
    def is_classmethod(self) -> bool:
        ...
    
    @cached_property
    def is_staticmethod(self) -> bool:
        ...

class Argument(docspec.Argument):

    @cached_property
    def datatype_ast(self) -> Optional[ast.expr]:
        ...

    @cached_property
    def default_value_ast(self) -> Optional[ast.expr]:
        ...

class Decoration(docspec.Decoration):
    
    @cached_property
    def ast(self) -> ast.expr:
        ...

class Module(docspec.Module):

    @cached_property
    def is_package(self) -> bool:
        ...

    @cached_property
    def all(self) -> Optional[List[str]]:
        ...
    
    @cached_property
    def docformat(self) -> Optional[str]:
        ...
