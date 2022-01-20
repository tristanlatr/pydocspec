"""
Build an `ApiObject` tree from live objects. 

Used to inspect c-extentions only.
"""
from typing import Mapping, Tuple, Type, Any, Optional, cast
import types
import importlib.util
from pathlib import Path
import inspect

from .basebuilder import Collector
from . import _model

import docspec

# Declare the types that we consider as functions (also when they are coming
# from a C extension)
func_types: Tuple[Type[Any], ...] = (types.BuiltinFunctionType, types.FunctionType)
if hasattr(types, "MethodDescriptorType"):
    # This is Python >= 3.7 only
    func_types += (types.MethodDescriptorType, )
else:
    func_types += (type(str.join), )
if hasattr(types, "ClassMethodDescriptorType"):
    # This is Python >= 3.7 only
    func_types += (types.ClassMethodDescriptorType, )
else:
    func_types += (type(dict.__dict__["fromkeys"]), )

def introspect_module(root: _model.TreeRoot, path: Path,
            module_name: str,
            parent: Optional[_model.Module]) -> _model.Module:
    """
    Introspect a python module. 
    """
    _builder = _IntrospectModuleBuilder(root, path, module_name, parent=parent)
    return _builder.introspect_py_module()

def _import_module(path: Path, module_full_name:str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_full_name, path)
    if spec is None: 
        raise RuntimeError(f"Cannot find spec for module {module_full_name} at {path}")
    py_mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert isinstance(loader, importlib.abc.Loader), loader
    loader.exec_module(py_mod)
    return py_mod

class _IntrospectModuleBuilder(Collector):
    """
    One instance of this class should be used per module, it does not recurse in submodules. 
    """

    def __init__(self, root: _model.TreeRoot, path: Path, module_name:str, parent: Optional[_model.Module]) -> None:
        super().__init__(root, module=None)
        # set required current attribute for Collector.add_object() 
        # method to work as expected. 
        self.current = cast(_model.ApiObject, parent) # it's ok to initiate the stack with a None value.

        self.path = path
        self.module_name = module_name
        self.parent = parent

        if self.parent is None:
            module_full_name = self.module_name
        else:
            module_full_name = f'{self.parent.full_name}.{self.module_name}'
        
        self.py_mod = _import_module(self.path, module_full_name)
    

    def _parameter2argument(self, param: inspect.Parameter) -> _model.Argument:
        kindmap = {
            inspect.Parameter.POSITIONAL_ONLY: docspec.Argument.Type.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD: docspec.Argument.Type.POSITIONAL,
            inspect.Parameter.VAR_POSITIONAL: docspec.Argument.Type.POSITIONAL_REMAINDER,
            inspect.Parameter.KEYWORD_ONLY: docspec.Argument.Type.KEYWORD_ONLY,
            inspect.Parameter.VAR_KEYWORD: docspec.Argument.Type.KEYWORD_REMAINDER,
        }
        return self.root.factory.Argument(name=param.name, 
            type=kindmap[param.kind], 
            datatype=str(param.annotation), 
            default_value=str(param.default),
            datatype_ast=None,
            default_value_ast=None, )

    def _introspect_thing(self, thing: object, parent: _model.ApiObject) -> None:
        
        for k, v in thing.__dict__.items():
            if (isinstance(v, func_types)
                    # In PyPy 7.3.1, functions from extensions are not
                    # instances of the abstract types in func_types
                    or (hasattr(v, "__class__") and v.__class__.__name__ == 'builtin_function_or_method')):
                
                try:
                    sig = inspect.Signature.from_callable(v)
                except ValueError:
                    # function either has an invalid text signature or no signature
                    # at all. We distinguish between the two by looking at the
                    # __text_signature__ attribute
                    if getattr(v, "__text_signature__", None) is not None:
                        parent.warn("Cannot parse signature of {0.name}.{1}".format(parent, k))
                    sig = inspect.Signature(
                            [inspect.Parameter("...", 
                                inspect.Parameter.POSITIONAL_ONLY)])
                
                args = []

                for param in sig.parameters.values():
                    args.append(self._parameter2argument(param))
                rtype = None if sig.return_annotation is inspect.Signature.empty else str(sig.return_annotation)
                
                f = self.root.factory.Function(k, None, 
                        self.root.factory.Docstring(v.__doc__, None), 
                        modifiers=None, 
                        args=args, 
                        return_type = rtype,
                        return_type_ast = None, 
                        decorations = None,)

                self.add_object(f, push=False)
            
            elif isinstance(v, type):
                c = self.root.factory.Class(name=k, 
                        location=None, 
                        docstring=self.root.factory.Docstring(v.__doc__, None),
                        metaclass=None, bases=[], decorations=[],
                        members=[],
                        )
                
                self.add_object(c)
                self._introspect_thing(v, c)
                self.pop(c)
    
    def introspect_py_module(self) -> _model.Module:
        is_package = self.py_mod.__package__ == self.py_mod.__name__

        module = self.root.factory.Module(
            name=self.module_name, 
            location=self.root.factory.Location(str(self.path), 0),
            docstring=self.root.factory.Docstring(self.py_mod.__doc__, None), 
            is_package=is_package,
            members=[])
        
        self.add_object(module)
        self._introspect_thing(self.py_mod, module)
        self.pop(module)
        return module