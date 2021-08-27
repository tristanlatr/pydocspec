"""
Convert L{docspec} objects to their L{pydocspec} augmented version.

This converter is supposed to be fully compatible with L{docspec_python}. 

Usage::

    import pydocspec
    from docspec_python import load_python_modules
    from pydocspec.converter import convert_docspec_modules
    modules: List[pydocspec.Module] = convert_docspec_modules(load_python_modules(...))

This module also provides utility to arrange a manually created C{pydocspec} tree, see L{Converter}.

@note: By default, the ast properties are computed on demand and cached with C{@cached_property} (creating ast nodes is expensive). 
        This behaviour is highly inefficient if we have already parsed the whole module's AST. 
        I should write an efficient builder soon. For now, we can use the C{convert_docspec_modules} function. 
"""

from typing import Iterable, cast, List, Optional, Union, overload
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal #type:ignore[misc]

import attr

import docspec
import pydocspec
from pydocspec import ApiObjectsRoot, dottedname, genericvisitor

@overload
def convert_docspec_modules(modules: List[docspec.Module], root:Literal[True]) -> ApiObjectsRoot: ... # type:ignore[invalid-annotation]
@overload
def convert_docspec_modules(modules: List[docspec.Module], root:Literal[False]) -> List[pydocspec.Module]: ... # type:ignore[invalid-annotation]

def convert_docspec_modules(modules: List[docspec.Module], root:bool=False) -> Union[List[pydocspec.Module], ApiObjectsRoot]:
    """
    Convert a list of L{docspec.Module} instances into a list of L{pydocspec.Module}. 
    Alternatively, you can also request the L{ApiObjectsRoot} instance by passing C{root=True}. 

    @returns: A list of the root modules of the tree or the L{ApiObjectsRoot} instance if C{root=True}.
    @note: It will transform the tree such that we have an actual hiearchy of packages. 

    """
    new_root = pydocspec.ApiObjectsRoot()
    converter = Converter(new_root)
    converter.add_docspec_modules(modules)
    converter.post_process()
    return new_root.root_modules if not root else new_root # type:ignore[bad-return-type]

@attr.s(auto_attribs=True)
class _ConverterVisitor(genericvisitor.Visitor[docspec.ApiObject]):
    """
    Visit each C{docspec} objects of a module and create their C{pydocspec} augmented counterparts.
    """
    converter: 'Converter'

    converted_module: pydocspec.Module = attr.ib(default=None, init=False)
    """
    The new converted module.
    """

    _current : pydocspec.ApiObject = attr.ib(default=None, init=False)
    _stack: List[pydocspec.ApiObject] = attr.ib(factory=list, init=False)

    def push(self, ob: pydocspec.ApiObject) -> None:
        self._stack.append(self._current)
        self._current = ob

    def pop(self, ob: pydocspec.ApiObject) -> None:
        self._current = self._stack.pop()
    
    def enter_object(self, ob: pydocspec.ApiObject) -> None:

        if self._current:
            assert isinstance(self._current, pydocspec.HasMembers)
            self._current.members.append(ob)
            self._current.sync_hierarchy(self._current.parent)
        else:
            assert isinstance(ob, pydocspec.Module)
            self.converted_module = ob
        
        self.push(ob)
    
    def unknown_departure(self, obj: docspec.ApiObject) -> None:
        obj_full_name = str(dottedname.DottedName(*(o.name for o in obj.path)))
        assert self._current.full_name == obj_full_name , f"{obj!r} is not {self._current!r}"
        self.pop(self._current)

    def visit_Function(self, function: docspec.Function) -> None:
        # this ignores the Argument.decorations, it does not exist in python.
        
        # convert arguments
        args: List[docspec.Argument] = []
        for a in function.args:
            new_arg = self.converter.Argument(name=a.name, type=a.type, 
                                        decorations=None, datatype=a.datatype, 
                                        default_value=a.default_value, )
            args.append(new_arg)
        
        # convert decorators
        if function.decorations is not None:
            decos: Optional[List[docspec.Decoration]] = []
            for d in function.decorations:
                new_deco = self.converter.Decoration(d.name, d.args)
                decos.append(new_deco) #type:ignore[union-attr]
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
            decos: Optional[List[docspec.Decoration]] = []
            for d in klass.decorations:
                converted = self.converter.Decoration(d.name, d.args)
            decos.append(converted) #type:ignore[union-attr]
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

@attr.s(auto_attribs=True)
class _PostProcessVisitorFirst(genericvisitor.Visitor[pydocspec.ApiObject]):
    """
    Visitor responsible to set the L{pydocspec.ApiObject.root} attribute on all objects and register 
    them in the {pydocspec.ApiObjectsRoot.all_objects} mapping. Which is the core to the name resolving system.

    @note: This should be run first after creating a new L{pydocspec} tree, then L{_PostProcessVisitorSecond}.
    """

    root: pydocspec.ApiObjectsRoot

    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:        
        ob.root = self.root
        self.root.all_objects[ob.full_name] = ob
    
    def unknown_departure(self, ob: pydocspec.ApiObject) -> None:
        pass

class _PostProcessVisitorSecond(genericvisitor.Visitor[pydocspec.ApiObject]):
    """
    Apply various required processing to new pydocspec trees.

    - Setup the L{pydocspec.Class.sub_classes} attribute.
    - Ensures that property setter and deleters do not shadow the getter.
    - Make the location attribute non-optional, reduces annoyance.
    """

    _default_location = docspec.Location(filename='<unknown>', lineno=-1)
    
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        if ob.location is None:
            ob.location = self._default_location #type:ignore[unreachable]

    def unknown_departure(self, ob: pydocspec.ApiObject) -> None:
        pass
    
    def visit_Class(self, ob: pydocspec.Class) -> None:
        self.unknown_visit(ob)
        
        # Populate the sub_classes attribute
        for b in ob.resolved_bases:
            if isinstance(b, pydocspec.Class):
                b.sub_classes.append(ob)

    def visit_Function(self, ob: pydocspec.Function) -> None:
        self.unknown_visit(ob)

        # property setters and deleters should not shadow the property object (getter).
        if ob.is_property_deleter or ob.is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, pydocspec.Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
        
        # TODO: same for overload functions, other instances of the issue ?

        # TODO: Populate a list of aliases for each objects.

@attr.s(auto_attribs=True)
class Converter:
    """
    Converter and post-processor, actually. 
    
    Convert C{docpsec} modules and add them in a L{pydocspec.ApiObjectsRoot} instance

    @param root: A newly created L{ApiObjectsRoot} instance that will be setup with the new objects.
    """

    root: pydocspec.ApiObjectsRoot

    ConverterVisitor = _ConverterVisitor
    PostProcessVisitorFirst = _PostProcessVisitorFirst
    PostProcessVisitorSecond = _PostProcessVisitorSecond
    
    Class = pydocspec.Class
    Data = pydocspec.Data
    Function = pydocspec.Function
    Indirection = pydocspec.Indirection
    Argument = pydocspec.Argument
    Decoration = pydocspec.Decoration
    Module = pydocspec.Module
    ApiObjectsRoot = pydocspec.ApiObjectsRoot

    def add_docspec_modules(self, modules: Iterable[docspec.Module]) -> None:
        """
        Convert and add L{docspec.Module}s to the L{ApiObjectsRoot} instance.
        """
        for mod in _nest_docspec_python_modules(modules):
            self._add_docspec_module(mod)

    def _add_docspec_module(self, mod: docspec.Module) -> None:
        v = self.ConverterVisitor(self)
        genericvisitor.walkabout(mod, v, 
            get_children=lambda ob: ob.members if isinstance(ob, docspec.HasMembers) else ())
        self.add_pydocspec_module(v.converted_module)
    
    def add_pydocspec_module(self, mod: pydocspec.Module) -> None:
        """
        Add a C{pydocspec} module to the L{ApiObjectsRoot} instance.
        """
        self.root.root_modules.append(mod)
    
    def post_process(self) -> None:
        """
        Apply post process on newly created L{pydocspec} tree. This is required.

        @note: If you are creating a tree manually, you should run this on your tree as well. 
        """
        for mod in self.root.root_modules:
            mod.walk(self.PostProcessVisitorFirst(root=self.root))
        for mod in self.root.root_modules:
            mod.walk(self.PostProcessVisitorSecond())
        
def _get_object_by_name(relativeroots: Iterable[docspec.ApiObject], name: dottedname.DottedName) -> Optional[docspec.ApiObject]:
    for r in relativeroots:
        if r.name == name[0]:
            if len(name) > 1:
                ob_full_name = str(dottedname.DottedName(*(o.name for o in r.path)))
                assert isinstance(r, docspec.HasMembers), f"The object '{ob_full_name}' is not a docspec.HasMembers instance, cannot find name '{name}'"
                return _get_object_by_name(r.members, name[1:]) # type:ignore[arg-type]
            return r
    return None

def _nest_docspec_python_modules(modules: Iterable[docspec.Module]) -> List[docspec.Module]:
    """Reparent modules to their respective parent packages such that we have an actual hiearchy of packages."""
    roots: List[docspec.Module] = []
    for mod in sorted(modules, key=lambda x: x.name):
        name = dottedname.DottedName(mod.name)
        container = name.container()
        if not container:
            roots.append(mod)
            continue
        pack = _get_object_by_name(roots, container)
        assert isinstance(pack, docspec.Module), f"Cannot find package named '{container}' in {roots!r}" 
        mod.name = name[-1]
        cast(List[docspec.Module], pack.members).append(mod)
        pack.sync_hierarchy(pack.parent)
    return roots
