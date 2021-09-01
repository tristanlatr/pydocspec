"""
Convert L{docspec} objects to their L{pydocspec} augmented version.

This converter is supposed to be fully compatible with L{docspec_python}. 

Usage::

    import pydocspec
    from docspec_python import load_python_modules
    from pydocspec.converter import convert_docspec_modules
    modules: List[pydocspec.Module] = convert_docspec_modules(load_python_modules(...))

@note: By default, the ast properties are computed on demand and cached with C{@cached_property} (creating ast nodes is expensive). 
        This behaviour is highly inefficient if we have already parsed the whole module's AST. 
        I should write an efficient builder soon. For now, we can use the C{convert_docspec_modules} function. 
"""

from typing import Iterable, Iterator, cast, List, Optional, Union, overload
try:
    from typing import Literal #type:ignore[attr-defined]
except ImportError:
    from typing_extensions import Literal #type:ignore[misc]

import attr

import docspec
import pydocspec
from pydocspec import dottedname, genericvisitor, specfactory, postprocessor, loader

@overload
def convert_docspec_modules(modules: Iterable[docspec.Module], root:Literal[True], additional_brain_modules:Optional[List[str]]=None) -> pydocspec.ApiObjectsRoot: ... # type:ignore[invalid-annotation]
@overload
def convert_docspec_modules(modules: Iterable[docspec.Module], root:Literal[False], additional_brain_modules:Optional[List[str]]=None) -> List[pydocspec.Module]: ... # type:ignore

def convert_docspec_modules(modules: Iterable[docspec.Module], root:bool=False, additional_brain_modules:Optional[List[str]]=None) -> Union[List[pydocspec.Module], pydocspec.ApiObjectsRoot]:
    """
    Convert a list of L{docspec.Module} instances into a list of L{pydocspec.Module}. 
    Alternatively, you can also request the L{ApiObjectsRoot} instance by passing C{root=True}. 

    @param modules: Modules to convert.
    @param root: Whether to return the L{ApiObjectsRoot} or the list of L{pydocspec.Module}. 
    @param additional_brain_modules: Custom brain modules to import into the system.
    @returns: A list of the root modules of the tree or the L{ApiObjectsRoot} instance if C{root=True}.
    @note: It will transform the tree such that we have an actual hiearchy of packages. 
    """
    factory = specfactory.Factory.default()
    post_processor = postprocessor.PostProcessor.default()
    
    if additional_brain_modules:
        for brain in additional_brain_modules:
            factory.import_mixins_from(brain)
            post_processor.import_post_processes_from(brain)
    
    new_root = factory.ApiObjectsRoot()

    converter = _Converter(new_root)
    converter.convert_docspec_modules(modules)
    
    post_processor.post_process(new_root)

    return new_root.root_modules if not root else new_root # type:ignore[bad-return-type]

class _ConverterVisitor(loader.Collector, genericvisitor.Visitor[docspec.ApiObject]):
    """
    Visit each C{docspec} objects of a module and create their C{pydocspec} augmented counterparts.
    """
    
    def unknown_departure(self, obj: docspec.ApiObject) -> None:
        obj_full_name = str(dottedname.DottedName(*(o.name for o in obj.path)))
        assert self._current is not None
        assert self._current.full_name == obj_full_name , f"{obj!r} is not {self._current!r}"
        self.pop(self._current)

    def visit_Function(self, function: docspec.Function) -> None:
        # this ignores the Argument.decorations, it does not exist in python.
        
        # convert arguments
        args: List[docspec.Argument] = []
        for a in function.args:
            new_arg = self.root.factory.Argument(name=a.name, type=a.type, 
                                        decorations=None, datatype=a.datatype, 
                                        default_value=a.default_value, )
            args.append(new_arg)
        
        # convert decorators
        if function.decorations is not None:
            decos: Optional[List[docspec.Decoration]] = []
            for d in function.decorations:
                new_deco = self.root.factory.Decoration(d.name, d.args)
                decos.append(new_deco) #type:ignore[union-attr]
        else:
            decos = None
            
        ob = self.root.factory.Function(name=function.name, location=function.location,
                                     docstring=function.docstring, 
                                     modifiers=function.modifiers,
                                     return_type=function.return_type,
                                     args=args,
                                     decorations=decos, )
        self.add_object(ob)
    
    def visit_Class(self, klass: docspec.Class) -> None:
        if klass.decorations is not None:
            decos: Optional[List[docspec.Decoration]] = []
            for d in klass.decorations:
                converted = self.root.factory.Decoration(d.name, d.args)
            decos.append(converted) #type:ignore[union-attr]
        else:
            decos = None
        ob = self.root.factory.Class(name=klass.name, 
            location=klass.location, 
            docstring=klass.docstring, 
            bases=klass.bases,
            decorations=decos,
            metaclass=klass.metaclass,
            members=[], )
        self.add_object(ob)
    
    def visit_Data(self, data: docspec.Data) -> None:
        ob = self.root.factory.Data(name=data.name, 
            location=data.location, 
            docstring=data.docstring, 
            datatype=data.datatype, 
            value=data.value, )
        self.add_object(ob)
    
    def visit_Indirection(self, indirection: docspec.Indirection) -> None:
        ob = self.root.factory.Indirection(name=indirection.name, 
            location=indirection.location, 
            docstring=indirection.docstring, 
            target=indirection.target, )
        self.add_object(ob)
    
    def visit_Module(self, module: docspec.Module) -> None:
        ob = self.root.factory.Module(name=module.name, 
            location=module.location,
            docstring=module.docstring, 
            members=[], )
        self.add_object(ob)


@attr.s(auto_attribs=True)
class _Converter:
    """
    Converts L{docspec} objects to their L{pydocspec} augmented version.
    """
    root: pydocspec.ApiObjectsRoot

    def convert_docspec_modules(self, modules: Iterable[docspec.Module]) -> None:
        """
        Convert L{docspec.Module}s to the L{ApiObjectsRoot} instance.
        """
        _modules = list(modules)
        for mod in _nest_docspec_python_modules(_modules) if len(_modules)>1 else _modules:
            new_mod = self._convert_docspec_module(mod)
            self.root.root_modules.append(new_mod)


    def _convert_docspec_module(self, mod: docspec.Module) -> pydocspec.Module:
        v = _ConverterVisitor(self.root, module=None)
        
        genericvisitor.walkabout(mod, v, 
            get_children=lambda ob: ob.members if isinstance(ob, docspec.HasMembers) else ())
        
        assert v.module is not None
        return v.module

#
# Code for nesting docspec modules
#


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
