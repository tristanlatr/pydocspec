"""
Convert `docspec` objects to their `pydocspec` augmented version.

This converter is supposed to be fully compatible with `docspec_python`. 

Usage::

    import pydocspec
    from docspec_python import load_python_modules
    from pydocspec.converter import convert_docspec_modules
    root: pydocspec.TreeRoot = convert_docspec_modules(load_python_modules(...))

TODO: Converter should not crash when calling unstring_annotation or exract_expr.

"""

import logging
from typing import Iterable, cast, List, Optional, Union, overload, TYPE_CHECKING
from pydocspec import visitors

import attr
import astroid.exceptions
import astroid.nodes

import docspec
import pydocspec
from pydocspec import dottedname, basebuilder, astroidutils
 
def convert_docspec_modules(modules: Iterable[docspec.Module], options: Optional[pydocspec.Options]=None) -> pydocspec.TreeRoot:
    """
    Convert a list of `docspec.Module` instances into a list of `pydocspec.Module`. 
    Alternatively, you can also request the `TreeRoot` instance by passing ``root=True``. 

    :param modules: Modules to convert.
    :return: The tree or the `TreeRoot` instance.
    :note: It will transform the tree such that we have an actual hiearchy of packages. 
    """    
    builder = pydocspec.builder_from_options(options)
    converter = _Converter(builder.root)
    converter.convert_docspec_modules(modules)
    builder._post_build()
    return builder.root

class _ConverterVisitor(basebuilder.Collector, visitors._docspecApiObjectVisitor):
    """
    Visit each ``docspec`` objects of a module and create their ``pydocspec`` augmented counterparts.
    """
    
    def unknown_departure(self, obj: docspec.ApiObject) -> None:
        obj_full_name = str(dottedname.DottedName(*(o.name for o in obj.path)))
        assert self.current is not None
        assert self.current.full_name == obj_full_name , f"{obj!r} is not {self.current!r}"
        self.pop(self.current)

    def visit_Function(self, function: docspec.Function) -> None:
        # this ignores the Argument.decorations, it does not exist in python.
        
        # convert arguments
        args: List[docspec.Argument] = []
        for a in function.args:
            
            new_arg = self.root.factory.Argument(name=a.name, type=a.type, 
                                        decorations=None, datatype=a.datatype, 
                                        default_value=a.default_value,
                                        datatype_ast=astroidutils.unstring_annotation(astroidutils.extract_expr(a.datatype)) if a.datatype else None,
                                        default_value_ast=astroidutils.extract_expr(a.default_value) if a.default_value else None)
            args.append(new_arg)
        
        # convert decorators
        if function.decorations is not None:
            
            decos: Optional[List[pydocspec.Decoration]] = []
            for d in function.decorations:
                decos.append(self._convert_Decoration(d)) #type:ignore[union-attr]
        else:
            decos = None
    
        ob = self.root.factory.Function(name=function.name, 
                                     location=self._convert_Location(function.location),
                                     docstring=self._convert_Docstring(function.docstring), 
                                     modifiers=function.modifiers,
                                     return_type=function.return_type,
                                     args=args,
                                     decorations=decos, 
                                     return_type_ast=astroidutils.unstring_annotation(astroidutils.extract_expr(function.return_type)) if function.return_type else None)
        self.add_object(ob)
    
    def visit_Class(self, klass: docspec.Class) -> None:

        if klass.decorations is not None:
            decos: Optional[List[docspec.Decoration]] = []
            for d in klass.decorations:
                decos.append(self._convert_Decoration(d)) #type:ignore[union-attr]
        else:
            decos = None
        ob = self.root.factory.Class(name=klass.name, 
            location=self._convert_Location(klass.location),
            docstring=self._convert_Docstring(klass.docstring), 
            bases=klass.bases,
            decorations=decos,
            metaclass=klass.metaclass,
            members=[], 
            bases_ast=[astroidutils.unstring_annotation(astroidutils.extract_expr(str_base)) for str_base in klass.bases] if klass.bases else None)
        self.add_object(ob)
    
    def visit_Data(self, data: docspec.Data) -> None:

        ob = self.root.factory.Data(name=data.name, 
            
            location=self._convert_Location(data.location),
            docstring=self._convert_Docstring(data.docstring), 
            datatype=data.datatype, 
            value=data.value, 
            datatype_ast=astroidutils.unstring_annotation(astroidutils.extract_expr(data.datatype)) if data.datatype else None,
            value_ast=astroidutils.extract_expr(data.value) if data.value else None
            )
        self.add_object(ob)
    
    def visit_Indirection(self, indirection: docspec.Indirection) -> None:
        ob = self.root.factory.Indirection(name=indirection.name, 
            location=self._convert_Location(indirection.location),
            docstring=self._convert_Docstring(indirection.docstring),
            target=indirection.target, )
        self.add_object(ob)
    
    def visit_Module(self, module: docspec.Module) -> None:
        ob = self.root.factory.Module(name=module.name, 
            location=self._convert_Location(module.location),
            docstring=self._convert_Docstring(module.docstring), 
            members=[], )
        self.add_object(ob)
    
    def _convert_Decoration(self, decoration: docspec.Decoration) ->  pydocspec.Decoration:
        expr_ast = None
        # Uses the name and args/arglist to compute the expr_ast variable.
        flat_arglist = ''
        if decoration.arglist:
            flat_arglist = f"({', '.join(decoration.arglist)})"
        elif decoration.args:
            flat_arglist = decoration.args
        decorator_text = f"{decoration.name}{flat_arglist}"
        try:
            expr_ast = astroidutils.extract_expr(decorator_text)
        except (SyntaxError, ):
            lineno = getattr(decoration.location, 'lineno', None) or self.current.location.lineno
            self.current.module.warn(f"Invalid decorator expression: {decorator_text!r}", 
                lineno_offset=lineno)
        else:
            # we compute the arglist if not present
            if not decoration.arglist and isinstance(expr_ast, astroid.nodes.Call):
                decoration.arglist = [astroidutils.to_source(n) for n in expr_ast.args] + \
                        [f"{(n.arg+'=') if n.arg else '**'}{astroidutils.to_source(n.value) if n.value else ''}" for n in expr_ast.keywords]

        new_deco = self.root.factory.Decoration(name=decoration.name, 
                            location=self._convert_Location(decoration.location),
                            arglist=decoration.arglist, 
                            name_ast=astroidutils.extract_expr(decoration.name),
                            expr_ast=expr_ast,
                            ) 
        
        return new_deco
    
    def _convert_Location(self, location: Optional[docspec.Location]) -> Optional[pydocspec.Location]:
        if not location: return None
        loc = self.root.factory.Location(
                filename=location.filename, 
                lineno=location.lineno,
                endlineno=location.endlineno)
        if not loc.filename:
            loc.filename = self.current.module.location.filename
        return loc

    def _convert_Docstring(self, docstring: Optional[docspec.Docstring]) -> Optional[pydocspec.Docstring]:
        if not docstring: return None
        return self.root.factory.Docstring(
                content=docstring.content,
                location=self._convert_Location(docstring.location),
                )

@attr.s(auto_attribs=True)
class _Converter:
    """
    Converts `docspec` objects to their `pydocspec` augmented version.
    """
    root: pydocspec.TreeRoot

    def convert_docspec_modules(self, modules: Iterable[docspec.Module]) -> None:
        """
        Convert `docspec.Module`s to the `TreeRoot` instance.
        """
        _modules = list(modules)
        for mod in _nest_docspec_python_modules(_modules) if len(_modules)>1 else _modules:
            self._convert_docspec_module(mod)

    def _convert_docspec_module(self, mod: docspec.Module) -> None:
        v = _ConverterVisitor(self.root)
        
        v.walkabout(mod)
        
        assert v.module is not None
        assert v.module in self.root.root_modules


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
