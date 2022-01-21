"""
Processes the half baked model created by the builder to populate buch of fancy attributes.
"""

from importlib import import_module
import logging
from typing import Any, Callable, Dict, Union

import attr
import pydocspec
from pydocspec import genericvisitor, _model, brains
from pydocspec import visitors

from . import class_attr, data_attr, func_attr, mod_attr

__all__ = ('class_attr', 'data_attr', 'func_attr', 'mod_attr', 'Processor', 'Process')

Process = Callable[[pydocspec.TreeRoot], None]
"""
A process is simply a function that modify/populate attributes of the objects in a `TreeRoot` instance.
"""

class _AstMroVisitor(visitors.ApiObjectVisitor):
    """
    Set Class.mro attribute based on astroid to be able to
    correctly populate the resolved_bases attribute."""
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None: ...
    def visit_Class(self, ob: pydocspec.Class) -> None:
        ob.mro = class_attr.mro_from_astroid(ob)

class _ProcessorVisitor1(visitors.ApiObjectVisitor):

    _default_location = _model.Location(filename='<unknown>', lineno=-1)

    def unknown_departure(self, obj: pydocspec.ApiObject) -> None:
        ...
    
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        # Make the location attribute non-optional, reduces annoyance.
        # TODO: Be smarter and use parents location when possible. Fill the filename attribute on object thatt have only the lineno.
        if ob.location is None:
            ob.location = self._default_location #type:ignore[unreachable]

    def visit_Function(self, ob: pydocspec.Function) -> None:
        self.unknown_visit(ob)
        ob.is_property = func_attr.is_property(ob)
        ob.is_property_setter = func_attr.is_property_setter(ob)
        ob.is_property_deleter = func_attr.is_property_deleter(ob)
        ob.is_async = func_attr.is_async(ob)
        ob.is_method = func_attr.is_method(ob)
        ob.is_classmethod = func_attr.is_classmethod(ob)
        ob.is_staticmethod = func_attr.is_staticmethod(ob)
        ob.is_abstractmethod = func_attr.is_abstractmethod(ob)
    
    def visit_Class(self, ob: pydocspec.Class) -> None:
        self.unknown_visit(ob)
        # .mro attribute is set in _AstMroVisitor()
        ob.resolved_bases = class_attr.resolved_bases(ob)
        ob.constructor_method = class_attr.constructor_method(ob)
    
    def visit_Data(self, ob: pydocspec.Data) -> None:
        self.unknown_visit(ob)
        ob.is_instance_variable = data_attr.is_instance_variable(ob)
        ob.is_class_variable = data_attr.is_class_variable(ob)
        ob.is_module_variable = data_attr.is_module_variable(ob)
        ob.is_alias = data_attr.is_alias(ob)
        ob.is_constant = data_attr.is_constant(ob)
    
    def visit_Indirection(self, ob: pydocspec.Indirection) -> None:
        self.unknown_visit(ob)
    
    def visit_Module(self, ob: pydocspec.Module) -> None:
        self.unknown_visit(ob)
        if not ob.dunder_all:
            ob.dunder_all = mod_attr.dunder_all(ob)
        ob.docformat = mod_attr.docformat(ob)
        if not ob.is_package:
            ob.is_package = mod_attr.is_package(ob)

class _ProcessorVisitor2(visitors.ApiObjectVisitor):
    # post-processor
    
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        ob.doc_sources = data_attr.doc_sources(ob)

    def visit_Class(self, ob: pydocspec.Class) -> None:
        self.unknown_visit(ob)
        
        # we don't need to re compute the MRO if the tree has beed created from astroid and there is
        # no extensions.
        ob.mro = class_attr.mro(ob)
        
        ob.is_exception = class_attr.is_exception(ob)
        class_attr.process_subclasses(ob) # Setup the `pydocspec.Class.subclasses` attribute.
    
    def visit_Function(self, ob: pydocspec.Function) -> None:
        self.unknown_visit(ob)

        # Ensures that property setter and deleters do not shadow the getter.
        if ob.is_property_deleter or \
           ob.is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, pydocspec.Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
    
        # TODO: same for overload functions, other instances of the issue ?

        # TODO: names defined in the __init__.py of a package should shadow the submodules with the same name in all_objects.

    def visit_Data(self, ob: pydocspec.Data) -> None:
        self.unknown_visit(ob)
        # Populate a list of aliases for each objects.
        data_attr.process_aliases(ob)

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
    Populate `pydocspec` attributes by applying processing to a newly created `pydocspec.TreeRoot` instance coming from the `astbuilder`. 

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