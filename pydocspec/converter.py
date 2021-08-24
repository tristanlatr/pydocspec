from typing import List, Optional

import attr

import docspec
import pydocspec
from pydocspec import Function, dottedname, genericvisitor

def to_pydocspec(modules: List[docspec.Module]) -> pydocspec.ApiObjectsRoot:
    root = pydocspec.ApiObjectsRoot()
    converter = Converter(root)
    for mod in modules:
        converter.process_module(mod)
    return root

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
        args = [self.converter.Argument(name=a.name, type=a.type, 
                                        decorations=None, datatype=a.datatype, 
                                        default_value=a.default_value, ) for a in function.args]
        if function.decorations is not None:
            decos: Optional[List[pydocspec.Decoration]] = [self.converter.Decoration(d.name, d.args) for d in function.decorations]
        else:
            decos = None
        ob = self.converter.Function(name=function.name, location=function.location,
                                     docstring=function.docstring, 
                                     modifiers=function.modifiers,
                                     return_type=function.return_type,
                                     args=args,
                                     decorations=decos, )
        self.enter_object(ob)
    
    def visit_Class(self, klass: docspec.Class) -> None:
        if klass.decorations is not None:
            decos: Optional[List[pydocspec.Decoration]] = [self.converter.Decoration(d.name, d.args) for d in klass.decorations]
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
    
    def visit_Data(self, data: docspec.Data) -> None:
        ob = self.converter.Data(name=data.name, 
            location=data.location, 
            docstring=data.docstring, 
            datatype=data.datatype, 
            value=data.value, )
        self.enter_object(ob)
    
    def visit_Indirection(self, indirection: docspec.Indirection) -> None:
        ob = self.converter.Indirection(name=indirection.name, 
            location=indirection.location, 
            docstring=indirection.docstring, 
            target=indirection.target, )
        self.enter_object(ob)
    
    def visit_Module(self, module: docspec.Module) -> None:
        ob = self.converter.Module(name=module.name, 
            location=module.location,
            docstring=module.docstring, 
            members=[], )
        self.enter_object(ob)

class PostProcessVisitor(genericvisitor.Visitor[pydocspec.ApiObject]):
    
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        pass
    def unknown_departure(self, ob: pydocspec.ApiObject) -> None:
        pass

    def visit_Function(self, ob: pydocspec.Function) -> None:

        # property setters and deleters should not shadow the property object
        if ob.is_property_deleter or ob.is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
        
        # TODO: same for overload functions

@attr.s(auto_attribs=True)
class Converter:

    root: pydocspec.ApiObjectsRoot

    converted_modules: List[pydocspec.Module] = attr.ib(factory=list, init=False)

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
        self.converted_modules.append(v.converted_module)
    
    def post_process(self) -> None:
        for mod in self.converted_modules:
            genericvisitor.walkabout(mod, self.PostProcessVisitor(), 
                get_children=lambda ob: ob.members if isinstance(ob, docspec.HasMembers) else ())
        
