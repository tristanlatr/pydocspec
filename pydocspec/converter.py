"""
Convert L{docspec.Module} objects into a L{pydocspec.ApiObjectsRoot} containing all your objects.

This converter is supposed to be fully compatible with L{docspec_python}. 

Usage::

    import pydocspec
    from docspec_python import load_python_modules
    from pydocspec.converter import convert_docspec_modules
    root: pydocspec.ApiObjectsRoot = convert_docspec_modules(load_python_modules(...))

@note: It will transform the tree such that we have an actual hiearchy of packages. 
"""

from typing import List, Optional, Sequence

import attr

import docspec
import pydocspec
from pydocspec import dottedname, genericvisitor

def convert_docspec_modules(modules: List[docspec.Module], copy_ast_properties:bool=False) -> pydocspec.ApiObjectsRoot:
    """
    Convert a list of L{docspec.Module} instances into a L{ApiObjectsRoot}.  

    @param copy_ast_properties: 
        By default, the ast properties are computed on demand (creating ast nodes is expensive). 
        This behaviour is highly inefficient when you have already parsed the whole module's AST. 
        You can optimize the process by already setting all the ast properties beforehead on the 
        `docspec` objects and turn this option on. 
        
        Matching attributes that ends with "ast" will be transferred on new `pydocspec` objects. 

        List of AST properties:

        - Data.datatype_ast
        - Data.value_ast
        - Function.return_type_ast
        - Argument.datatype_ast
        - Argument.default_value_ast
        - Decoration.name_ast
        - Decoration.expr_ast
    """
    root = pydocspec.ApiObjectsRoot()
    converter = Converter(root, copy_ast_properties=copy_ast_properties)
    for mod in _nest_docspec_python_modules(modules):
        converter.process_module(mod)
    converter.post_process()
    return root

def _get_mod_by_name(relativeroots: List[docspec.Module], name: Sequence[str]) -> Optional[docspec.Module]:
    for r in relativeroots:
        if r.name == name[0]:
            if len(name) > 1:
                return _get_mod_by_name(r.members, name[1:])
            return r
    return None

def _nest_docspec_python_modules(modules: List[docspec.Module]) -> List[docspec.Module]:
    """Reparent modules to their respective parent packages such that we have an actual hiearchy of packages."""
    roots: List[docspec.Module] = []
    for mod in sorted(modules, key=lambda x: x.name):
        name = dottedname.DottedName(mod.name)
        container = name.container()
        if not container:
            roots.append(mod)
            continue
        pack = _get_mod_by_name(roots, container)
        assert pack is not None, f"Cannot find module named '{container}' in {roots!r}" 
        mod.name = name[-1]
        pack.members.append(mod)
    for r in roots:
        r.sync_hierarchy()
    return roots

@attr.s(auto_attribs=True)
class ConverterVisitor(genericvisitor.Visitor[docspec.ApiObject]):
    converter: 'Converter'

    converted_module: pydocspec.Module = attr.ib(default=None, init=False)
    current : pydocspec.ApiObject = attr.ib(default=None, init=False)

    _stack: List[pydocspec.ApiObject] = attr.ib(factory=list, init=False)

    def push(self, ob: pydocspec.ApiObject) -> None:
        self._stack.append(self.current)
        self.current = ob

    def pop(self, ob: pydocspec.ApiObject) -> None:
        self.current = self._stack.pop()
    
    def enter_object(self, ob: pydocspec.ApiObject) -> None:
        ob.root = self.converter.root

        if self.current:
            assert isinstance(self.current, docspec.HasMembers)
            self.current.members.append(ob)
            self.converted_module.sync_hierarchy()
        
        else:
            assert isinstance(ob, pydocspec.Module)
            self.converted_module = ob
            self.converter.root.root_modules.append(ob)
        
        self.converted_module.root.all_objects[ob.full_name] = ob
        self.push(ob)
    
    def unknown_departure(self, obj: docspec.ApiObject) -> None:
        obj_full_name = str(dottedname.DottedName(*(o.name for o in obj.path)))
        assert self.current.full_name == obj_full_name , f"{obj!r} is not {self.current!r}"
        self.pop(self.current)

    def visit_Function(self, function: docspec.Function) -> None:
        # this ignores the Argument.decorations, it does not exist in python.
        
        # convert arguments
        args: List[pydocspec.Argument] = []
        for a in function.args:
            converted = self.converter.Argument(name=a.name, type=a.type, 
                                        decorations=None, datatype=a.datatype, 
                                        default_value=a.default_value, )
            if self.converter.copy_ast_properties:
                self.copy_ast_props(a, converted)
            args.append(converted)
        
        # convert decorators
        if function.decorations is not None:
            decos: Optional[List[pydocspec.Decoration]] = []
            for d in function.decorations:
                converted = self.converter.Decoration(d.name, d.args)
                if self.converter.copy_ast_properties:
                    self.copy_ast_props(d, converted)
                decos.append(converted)
        else:
            decos = None
            
        ob = self.converter.Function(name=function.name, location=function.location,
                                     docstring=function.docstring, 
                                     modifiers=function.modifiers,
                                     return_type=function.return_type,
                                     args=args,
                                     decorations=decos, )
        self.enter_object(ob)
        if self.converter.copy_ast_properties:
            self.copy_ast_props(function, ob)
    
    def visit_Class(self, klass: docspec.Class) -> None:
        if klass.decorations is not None:
            decos: Optional[List[pydocspec.Decoration]] = []
            for d in klass.decorations:
                converted = self.converter.Decoration(d.name, d.args)
                if self.converter.copy_ast_properties:
                    self.copy_ast_props(d, converted)
            decos.append(converted)
        else:
            decos = None
        ob = self.converter.Class(name=klass.name, 
            location=klass.location, 
            docstring=klass.docstring, 
            bases=klass.bases,
            decorations=decos,
            metaclass=klass.metaclass,
            members=[], )
        self.enter_object(ob)
        if self.converter.copy_ast_properties:
            self.copy_ast_props(klass, ob)
    
    def visit_Data(self, data: docspec.Data) -> None:
        ob = self.converter.Data(name=data.name, 
            location=data.location, 
            docstring=data.docstring, 
            datatype=data.datatype, 
            value=data.value, )
        self.enter_object(ob)
        if self.converter.copy_ast_properties:
            self.copy_ast_props(data, ob)
    
    def visit_Indirection(self, indirection: docspec.Indirection) -> None:
        ob = self.converter.Indirection(name=indirection.name, 
            location=indirection.location, 
            docstring=indirection.docstring, 
            target=indirection.target, )
        self.enter_object(ob)
        if self.converter.copy_ast_properties:
            self.copy_ast_props(indirection, ob)
    
    def visit_Module(self, module: docspec.Module) -> None:
        ob = self.converter.Module(name=module.name, 
            location=module.location,
            docstring=module.docstring, 
            members=[], )
        self.enter_object(ob)
        if self.converter.copy_ast_properties:
            self.copy_ast_props(module, ob)
    
    @staticmethod
    def copy_ast_props(ob: docspec.ApiObject, pydocspecob: pydocspec.ApiObject) -> None:
        for name,v in ob.__dict__.items():
            if name.endswith("ast"):
                if name in pydocspecob.__class__.__dict__:
                    setattr(pydocspecob, name, v)

class PostProcessVisitor(genericvisitor.Visitor[pydocspec.ApiObject]):
    
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        pass
    def unknown_departure(self, ob: pydocspec.ApiObject) -> None:
        pass

    def visit_Function(self, ob: pydocspec.Function) -> None:

        # property setters and deleters should not shadow the property object
        if ob.is_property_deleter or ob.is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, pydocspec.Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
        
        # TODO: same for overload functions

@attr.s(auto_attribs=True)
class Converter:

    root: pydocspec.ApiObjectsRoot

    copy_ast_properties: bool = False

    ConverterVisitor = ConverterVisitor
    PostProcessVisitor = PostProcessVisitor
    Class = pydocspec.Class
    Data = pydocspec.Data
    Function = pydocspec.Function
    Indirection = pydocspec.Indirection
    Argument = pydocspec.Argument
    Decoration = pydocspec.Decoration
    Module = pydocspec.Module
    ApiObjectsRoot = pydocspec.ApiObjectsRoot

    def process_module(self, mod: docspec.Module) -> None:
        v = self.ConverterVisitor(self)
        genericvisitor.walkabout(mod, v, 
            get_children=lambda ob: ob.members if isinstance(ob, docspec.HasMembers) else ())
        
        self.root.root_modules.append(v.converted_module)
    
    def post_process(self) -> None:
        for mod in self.root.root_modules:
            genericvisitor.walkabout(mod, self.PostProcessVisitor(), 
                get_children=lambda ob: ob.members if isinstance(ob, docspec.HasMembers) else ())
        
