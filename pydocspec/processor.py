"""
Processes the half baked model created by the builder to populate buch of fancy attributes.

:note: The code in the module should use as little as possible the features offered by `pydocspec`.* classes. 
    This is why the code is annotated with `_model`.* classes and `cast` is used when necessary.
"""

from importlib import import_module
import logging
from typing import Any, Callable, Dict, Iterable, Iterator, Sequence, cast, List, Optional, Union, Tuple, overload
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal #type:ignore[misc]

import attr

import astroid.nodes
import pydocspec
from pydocspec import genericvisitor, _model, astroidutils, brains, mro

Process = Callable[[pydocspec.TreeRoot], None]
"""
A process is simply a function that modify/populate attributes of the objects in a `TreeRoot` instance.
"""

# PROCESSING FUNCTION HELPERS

@overload
def _ast2apiobject(root: pydocspec.TreeRoot, node: 'astroid.nodes.ClassDef') -> Optional['pydocspec.Class']:
    ...
@overload
def _ast2apiobject(root: pydocspec.TreeRoot, node: 'astroid.nodes.Module') -> Optional['pydocspec.AnyModule']:
    ...
def _ast2apiobject(root: pydocspec.TreeRoot, node: Union['astroid.nodes.ClassDef', 
                                        'astroid.nodes.Module']) -> Optional[Union['pydocspec.Class', 'pydocspec.Module']]:
    values = root.all_objects.getall(node.qname())
    if not values: 
        return None
    for sameloc in filter(
        lambda ob: ob.location is not None \
            and ob.location.lineno is not None \
                and ob.location.lineno==node.lineno, values):
        return sameloc
    return None

class _ast_helpers:
    @staticmethod
    def is_using_typing_final(expr: Optional[astroid.nodes.NodeNG], ctx: _model.ApiObject) -> bool:
        return _ast_helpers.is_using_annotations(expr, 
                ("typing.Final", "typing_extensions.Final"), 
                cast(pydocspec.ApiObject, ctx))
    @staticmethod
    def is_using_annotations(expr: Optional[astroid.nodes.NodeNG], annotations:Sequence[str], ctx: pydocspec.ApiObject) -> bool:
        """
        Detect if this expr is firstly composed by one of the specified annotation(s)' full name.
        """
        full_name = astroidutils.node2fullname(expr, ctx)
        if full_name in annotations:
            return True
        if isinstance(expr, astroid.nodes.Subscript):
            # Final[...] or typing.Final[...] expressions
            if isinstance(expr.value, (astroid.nodes.Name, astroid.nodes.Attribute)):
                value = expr.value
                full_name = astroidutils.node2fullname(value, ctx)
                if full_name in annotations:
                    return True
        return False

class _function_helper:
    @staticmethod
    def is_property(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            name = astroidutils.node2fullname(deco.name_ast, cast(pydocspec.ApiObject, ob.parent))
            if name and name.endswith(('property', 'Property')):
                return True
        return False
    @staticmethod
    def is_property_setter(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            name = astroidutils.node2dottedname(deco.name_ast)
            if name and len(name) == 2 and name[0]==ob.name and name[1] == 'setter':
                return True
        return False
    @staticmethod
    def is_property_deleter(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            name = astroidutils.node2dottedname(deco.name_ast)
            if name and len(name) == 2 and name[0]==ob.name and name[1] == 'deleter':
                return True
        return False
    @staticmethod
    def is_async(ob: _model.Function) -> bool:
        return 'async' in (ob.modifiers or ())
    @staticmethod
    def is_method(ob: _model.Function) -> bool:
        return isinstance(ob.parent, _model.Class)
    @staticmethod
    def is_classmethod(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            if astroidutils.node2fullname(deco.name_ast, cast(pydocspec.ApiObject, ob.parent)) == 'classmethod':
                return True
        return False
    @staticmethod
    def is_staticmethod(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            if astroidutils.node2fullname(deco.name_ast, cast(pydocspec.ApiObject, ob.parent)) == 'staticmethod':
                return True
        return False
    @staticmethod
    def is_abstractmethod(ob: _model.Function) -> bool:
        for deco in ob.decorations or ():
            if astroidutils.node2fullname(deco.name_ast, cast(pydocspec.ApiObject, ob.parent)) in ['abc.abstractmethod', 'abc.abstractproperty']:
                return True
        return False

class MRO(mro.GenericMRO[_model.Class]):
    def bases(self, cls: _model.Class) -> List[_model.Class]:
        return [b for b in cast(pydocspec.Class, cls).resolved_bases if isinstance(b, _model.Class)]

class _class_helpers:
    # List of exceptions class names in the standard library, Python 3.8.10
    _exceptions = ('ArithmeticError', 'AssertionError', 'AttributeError', 
        'BaseException', 'BlockingIOError', 'BrokenPipeError', 
        'BufferError', 'BytesWarning', 'ChildProcessError', 
        'ConnectionAbortedError', 'ConnectionError', 
        'ConnectionRefusedError', 'ConnectionResetError', 
        'DeprecationWarning', 'EOFError', 
        'EnvironmentError', 'Exception', 'FileExistsError', 
        'FileNotFoundError', 'FloatingPointError', 'FutureWarning', 
        'GeneratorExit', 'IOError', 'ImportError', 'ImportWarning', 
        'IndentationError', 'IndexError', 'InterruptedError', 
        'IsADirectoryError', 'KeyError', 'KeyboardInterrupt', 'LookupError', 
        'MemoryError', 'ModuleNotFoundError', 'NameError', 
        'NotADirectoryError', 'NotImplementedError', 
        'OSError', 'OverflowError', 'PendingDeprecationWarning', 'PermissionError', 
        'ProcessLookupError', 'RecursionError', 'ReferenceError', 
        'ResourceWarning', 'RuntimeError', 'RuntimeWarning', 'StopAsyncIteration', 
        'StopIteration', 'SyntaxError', 'SyntaxWarning', 'SystemError', 
        'SystemExit', 'TabError', 'TimeoutError', 'TypeError', 
        'UnboundLocalError', 'UnicodeDecodeError', 'UnicodeEncodeError', 
        'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning', 'UserWarning', 
        'ValueError', 'Warning', 'ZeroDivisionError')
    @staticmethod
    def is_exception(ob: _model.Class) -> bool: 
        # must be set after resolved_bases
        for base in cast(pydocspec.Class, ob).ancestors(True):
            if base in _class_helpers._exceptions:
                return True
        return False
    
    @staticmethod
    def mro_from_astroid(ob: _model.Class) -> List[_model.Class]:
        # this does not support objects loaded from other places than astroid, 
        # for instance coming from introspection of a c-module.  
        # This is why we need to re-compute the MRO after.
        # But it does the job for the first iteration 
        # This should not rely on Class.resolved_bases, since resolved_bases relies 
        # on Class.find() which relies on Class.mro attribute.
        # The result from this function is used temporarly to compute the resolved_bases attribute
        # then .mro attribute is re-computed with mro() function below.
        if ob._ast is None:
            return []
        try:
            node_mro = ob._ast.mro()
            return [o for o in (_ast2apiobject(ob.root, node) for node in node_mro) if o]
        except Exception:
            node_mro = ob._ast.ancestors()
            return [o for o in (_ast2apiobject(ob.root, node) for node in node_mro) if o]
    
    @staticmethod # must be set after resolved_bases
    def mro(ob: _model.Class) -> List[_model.Class]:
        # we currently process the MRO twice for objects comming from ast
        try: 
            return MRO().mro(ob)
        except ValueError as e:
            ob.warn(str(e))
            return list(
                filter(lambda ob: isinstance(ob, _model.Class), 
                    cast(pydocspec.Class, ob).ancestors(True)))

    @staticmethod
    def resolved_bases(ob: _model.Class) -> List[Union['pydocspec.ApiObject', 'str']]: 
        # Uses the name resolving feature, but the name resolving feature also depends on Class.find, wich depends on resolved_bases.
        # So this is a source of potentially subtle bugs in the name resolving when there is a base class that is actually defined 
        # in the base class of another class accessed with the subclass name.
        # Example (in this example, to be correct, the resolved_bases attr of the class Foo must be set before the class bar, leading
        # to inconsistencies due to the random order of the module processing. 
        # The situation gets even more complicated when there are cyclic imports):
        # mod1.py
        # class _Base:
        #   class barbase(str):
        #       ...
        # class Foo(_Base):
        #   ...
        # mod2.py
        # from . import mod1
        # class bar(mod1.Foo.barbase):
        #   ...
        # SOLUTION: Populate the Class.mro attribute from astroid 
        # OR use this utility method from sphinx-autoapi resolve_qualname(ctx: NodeNG, name:str) -> str
        # https://github.com/readthedocs/sphinx-autoapi/blob/71c6ceebe0b02c34027fcd3d56c8641e9b94c7af/autoapi/mappers/python/astroid_utils.py#L64
        objs = []
        for base in ob.bases or ():
            # it makes 
            # resolve_qualname() is an alternative for expand_name() that is only based on astroid
            # resolved = astroidutils.resolve_qualname(ob.scope._ast, base)
            # resolved_obj = ob.root.all_objects.get(resolved)
            # it looks like resolved_obj can be an Indirection + 
            # need to create a separate function because it breaks the converter since ob.scope._ast is None for objects comming from the converter.
            # if resolved_obj:
            #     objs.append(resolved_obj)
            # else:
            #     objs.append(resolved)
            objs.append(cast(pydocspec.ApiObject, ob.parent).resolve_name(base) or \
                cast(pydocspec.ApiObject, ob.parent).expand_name(base))
        return objs
    @staticmethod
    def process_subclasses(ob: _model.Class) -> None:
        # for all resolved_bases classes, add ob to the subclasses list
        for b in cast(pydocspec.Class, ob).resolved_bases:
            if isinstance(b, pydocspec.Class):
                b.subclasses.append(cast(pydocspec.Class, ob))
    @staticmethod
    def constructor_method(ob: _model.Class) -> Optional['_model.Function']:
        init_method = ob.get_member('__init__')
        if isinstance(init_method, _model.Function):
            return init_method
        else:
            return None

class _data_helpers:
    @staticmethod
    def is_instance_variable(ob: _model.Data) -> bool:
        ...
    @staticmethod
    def is_class_variable(ob: _model.Data) -> bool:
        ...
    @staticmethod
    def is_module_variable(ob: _model.Data) -> bool:
        return isinstance(ob.parent, _model.Module)
    @staticmethod
    def is_alias(ob: _model.Data) -> bool:
        return astroidutils.is_name(ob.value_ast)
    @staticmethod
    def is_constant(ob: _model.Data) -> bool: # uses the name resolving feature
        return ob.name.isupper() or _ast_helpers.is_using_typing_final(ob.datatype_ast, ob)
    @staticmethod
    def process_aliases(ob: _model.Data) -> None:
        if cast(pydocspec.Data, ob).is_alias:
            assert ob.value is not None
            alias_to = cast(pydocspec.ApiObject, ob).resolve_name(ob.value)
            if alias_to is not None:
                alias_to.aliases.append(cast(pydocspec.Data, ob))

class _module_helpers:
    @staticmethod
    def dunder_all(ob: _model.Module) -> Optional[List[str]]:
        var = ob.get_member('__all__')
        if not var or not isinstance(var, _model.Data) or not var.value_ast:
            return None
        value = var.value_ast

        #TODO: use astroid infer()
        if not isinstance(value, (astroid.nodes.List, astroid.nodes.Tuple)):
            var.warn('Cannot parse value assigned to "__all__", must be a list or tuple.')
            return None

        names = []
        for idx, item in enumerate(value.elts):
            try:
                name: object = astroidutils.literal_eval(item)
            except ValueError:
                var.warn(f'Cannot parse element {idx} of "__all__"')
            else:
                if isinstance(name, str):
                    names.append(name)
                else:
                    var.warn(f'Element {idx} of "__all__" has '
                        f'type "{type(name).__name__}", expected "str"')

        return names

    @staticmethod
    def docformat(ob: _model.Module) -> Optional[str]:
        var = ob.get_member('__all__')
        if not var or not isinstance(var, _model.Data) or not var.value_ast:
            return None
        #TODO: use astroid infer()
        try:
            value = astroidutils.literal_eval(var.value_ast)
        except ValueError:
            var.warn('Cannot parse value assigned to "__docformat__": not a string')
            return None
        
        if not isinstance(value, str):
            var.warn('Cannot parse value assigned to "__docformat__": not a string')
            return None
            
        if not value.strip():
            var.warn('Cannot parse value assigned to "__docformat__": empty value')
            return None
        
        return value

    @staticmethod
    def is_package(ob: _model.Module) -> bool:

        return ob.is_package or any(isinstance(o, _model.Module) for o in ob.members)

    @staticmethod
    def public_names(ob: _model.Module) -> List[str]:
        """
        A name is public if it does not start by an underscore. 
        Submodules are not imported when wildcard importing a module, 
        so they are not listed as part of the public names. 

        :note: This is used to resolve wildcard imports when no `__all__` variable is
            defined.
        """
        return [name for name in (m.name for m in ob.members if \
            not ((isinstance(m, _model.Indirection) and m.is_type_guarged) \
                or isinstance(m, _model.Module)) )
                if not name.startswith('_')]

class _apiobject_helpers:
    
    @staticmethod
    def doc_sources(ob: _model.ApiObject) -> List[pydocspec.ApiObject]:
        # must be called after mro()
        sources = [ob]
        if isinstance(ob, _model.Inheritable):
            if isinstance(ob.parent, _model.Class):
                for b in cast(pydocspec.Class, ob.parent).mro:
                    base = b.get_member(ob.name)
                    if base:
                        sources.append(base)
        return cast(List[pydocspec.ApiObject], sources)

class _AstMroVisitor(genericvisitor.Visitor[_model.ApiObject]):
    """
    Set Class.mro attribute based on astroid to be able to
    correctly populate the resolved_bases attribute."""
    def unknown_visit(self, ob: _model.ApiObject) -> None: ...
    def visit_Class(self, ob: _model.Class) -> None:
        cast(pydocspec.Class, ob).mro = _class_helpers.mro_from_astroid(ob)

class _ProcessorVisitor1(genericvisitor.Visitor[_model.ApiObject]):

    _default_location = _model.Location(filename='<unknown>', lineno=-1)

    def unknown_departure(self, obj: _model.ApiObject) -> None:
        ...
    
    def unknown_visit(self, ob: _model.ApiObject) -> None:
        # Make the location attribute non-optional, reduces annoyance.
        # TODO: Be smarter and use parents location when possible. Fill the filename attribute on object thatt have only the lineno.
        if ob.location is None:
            ob.location = self._default_location #type:ignore[unreachable]

    def visit_Function(self, ob: _model.Function) -> None:
        self.unknown_visit(ob)
        cast(pydocspec.Function, ob).is_property = _function_helper.is_property(ob)
        cast(pydocspec.Function, ob).is_property_setter = _function_helper.is_property_setter(ob)
        cast(pydocspec.Function, ob).is_property_deleter = _function_helper.is_property_deleter(ob)
        cast(pydocspec.Function, ob).is_async = _function_helper.is_async(ob)
        cast(pydocspec.Function, ob).is_method = _function_helper.is_method(ob)
        cast(pydocspec.Function, ob).is_classmethod = _function_helper.is_classmethod(ob)
        cast(pydocspec.Function, ob).is_staticmethod = _function_helper.is_staticmethod(ob)
        cast(pydocspec.Function, ob).is_abstractmethod = _function_helper.is_abstractmethod(ob)
    
    def visit_Class(self, ob: _model.Class) -> None:
        self.unknown_visit(ob)
        # .mro attribute is set in _AstMroVisitor()
        cast(pydocspec.Class, ob).resolved_bases = _class_helpers.resolved_bases(ob)
        cast(pydocspec.Class, ob).constructor_method = cast(pydocspec.Function, _class_helpers.constructor_method(ob))
    
    def visit_Data(self, ob: _model.Data) -> None:
        self.unknown_visit(ob)
        cast(pydocspec.Data, ob).is_instance_variable = _data_helpers.is_instance_variable(ob)
        cast(pydocspec.Data, ob).is_class_variable = _data_helpers.is_class_variable(ob)
        cast(pydocspec.Data, ob).is_module_variable = _data_helpers.is_module_variable(ob)
        cast(pydocspec.Data, ob).is_alias = _data_helpers.is_alias(ob)
        cast(pydocspec.Data, ob).is_constant = _data_helpers.is_constant(ob)
    
    def visit_Indirection(self, ob: _model.Indirection) -> None:
        self.unknown_visit(ob)
    
    def visit_Module(self, ob: _model.Module) -> None:
        self.unknown_visit(ob)
        if not ob.dunder_all:
            cast(pydocspec.Module, ob).dunder_all = _module_helpers.dunder_all(ob)
        cast(pydocspec.Module, ob).docformat = _module_helpers.docformat(ob)
        cast(pydocspec.Module, ob).is_package = _module_helpers.is_package(ob)

class _ProcessorVisitor2(genericvisitor.Visitor[_model.ApiObject]):
    # post-processor
    
    def unknown_departure(self, ob: _model.ApiObject) -> None:
        ...
    
    def unknown_visit(self, ob: _model.ApiObject) -> None:
        cast(pydocspec.ApiObject, ob).doc_sources = _apiobject_helpers.doc_sources(ob)

    def visit_Class(self, ob: _model.Class) -> None:
        self.unknown_visit(ob)
        
        # we don't need to re compute the MRO if the tree has beed created from astroid and there is
        # no extensions.
        cast(pydocspec.Class, ob).mro = _class_helpers.mro(ob)
        
        cast(pydocspec.Class, ob).is_exception = _class_helpers.is_exception(ob)
        _class_helpers.process_subclasses(ob) # Setup the `pydocspec.Class.subclasses` attribute.
    
    def visit_Function(self, ob: _model.Function) -> None:
        self.unknown_visit(ob)

        # Ensures that property setter and deleters do not shadow the getter.
        if cast(pydocspec.Function, ob).is_property_deleter or \
           cast(pydocspec.Function, ob).is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, pydocspec.Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
    
        # TODO: same for overload functions, other instances of the issue ?

        # TODO: names defined in the __init__.py of a package should shadow the submodules with the same name in all_objects.

    def visit_Data(self, ob: _model.Data) -> None:
        self.unknown_visit(ob)
        # Populate a list of aliases for each objects.
        _data_helpers.process_aliases(ob)

def process0(root: pydocspec.TreeRoot) -> None:
    return
    #UnknownResolver(root).process()

def process1(root: pydocspec.TreeRoot) -> None:
    for mod in root.root_modules: mod.walk(_AstMroVisitor())
    for mod in root.root_modules: mod.walk(_ProcessorVisitor1())

def process2(root: pydocspec.TreeRoot) -> None:
    for mod in root.root_modules: mod.walk(_ProcessorVisitor2()) 

@attr.s(auto_attribs=True)
class Processor:
    """
    Populate `pydocspec` attributes by applying processing to a newly created `pydocspec.TreeRoot` instance. 

    At the point of the post processing, the root `pydocspec.Module` instances should have 
    already been added to the `pydocspec.TreeRoot.root_modules` attribute.
    
    Processes are applied when there are no more unprocessed modules.

    Analysis of relations between documentables should be done in a process,
    without the risk of drawing incorrect conclusions because modules
    were not fully processed yet.
    """ 
    
    # TODO: handle duplicates.
    processes: Dict[float, 'Process'] = attr.ib(factory=dict)
    """
    A post process is a function of the following form::

        (root: pydocspec.TreeRoot) -> None
    """

    @classmethod
    def default(cls, load_brains:bool=False) -> 'Processor':
        processor = cls(processes={ -2000: process0, 
                                    -1000: process1, 
                                    -990:  process2})
        if load_brains:
            for mod in brains.get_all_brain_modules():
                processor.import_processes_from(mod)
        return processor

    def import_processes_from(self, module:Union[str, Any]) -> None:
        """
        Will look for the special mapping ``pydocspec_processes`` in the provided module.
        """
        if isinstance(module, str):
            mod = import_module(module)
        else:
            mod = module
        if hasattr(mod, 'pydocspec_processes'):
            process_definitions = mod.pydocspec_processes
            assert isinstance(process_definitions, dict), f"{mod}.pydocspec_processes should be a dict, not {type(process_definitions)}."
            if any(process_definitions.values()):
                self.processes.update(process_definitions)
                return
            logging.getLogger('pydocspec').warning(f"No post processes added for module {mod}, check the validity of the pydocspec_processes attribute.")

    def process(self, root: pydocspec.TreeRoot) -> None:
        """
        Apply processes on the tree. This is required.

        .. python::

            root: pydocspec.TreeRoot
            processor.Processor.default().process(root)

        :note: If you are creating a tree manually, you should run this on your tree as well. 
        """
        for priority in sorted(self.processes.keys()):
            process = self.processes[priority]
            process(root)
