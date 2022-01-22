"""
Processes the half baked model created by the builder to populate buch of fancy attributes.
"""

from importlib import import_module
import logging
from typing import Any, Callable, Dict, Optional, Union

import attr
import pydocspec
from pydocspec import _model, brains, visitors, genericvisitor

from . import class_attr, data_attr, func_attr, mod_attr

__all__ = ('class_attr', 'data_attr', 'func_attr', 'mod_attr', 'Processor', 'Process')

Process = Callable[[pydocspec.TreeRoot], None]
"""
A process is simply a function that modify/populate attributes of 
the objects in a `TreeRoot` instance.
"""

class PostBuildVisitor0(visitors.ApiObjectVisitor):
    # pre-post-processor ;)
    # featured by extensions.
    def unknown_visit(self, ob: _model.ApiObject) -> None:
        ...
    def unknown_departure(self, ob: _model.ApiObject) -> None:
        ...

class _MroFromAstroidSetter(visitors.ApiObjectVisitorExt):
    """
    Set Class.mro attribute based on astroid to be able to
    correctly populate the resolved_bases attribute.
    """
    when = genericvisitor.When.BEFORE
    def unknown_visit(self, ob: pydocspec.Class) -> None:
        pass
    def visit_Class(self, ob: pydocspec.Class) -> None:
        ob.mro = class_attr.mro_from_astroid(ob)

class _DuplicateWhoShadowsWhoHandling(visitors.ApiObjectVisitorExt):
    # Duplicate objects handling: (in processor)
    # - For duplicate Data object (pretty common), we unify the information present in all Data objects
    #   under a single object. Information denifed after wins.
    #   If an instance varaible shadows a class variable, it will be considered as instance variable.
    # - In a class, a Data definition sould not shadow another object that is not a Data, 
    #       even if the object is inherited. So if that happens it will simply be ignored.
    # - A submodule can be shadowed by a another name by the same name in the package's __int__.py file.
    # - In a class, functions with the same name might be properties/overloaded function, so we should unify them under a single Function object
    when = genericvisitor.When.BEFORE
    
    # names defined in the __init__.py of a package should shadow the 
    # submodules with the same name in all_objects.
    def visit_Module(self, ob: pydocspec.Module) -> None:
        # is this submodule shadowed by another name in the package ?
        if ob.parent is not None:
            for dup in ob.root.all_objects.getall(ob.full_name):
                if dup is not ob:
                    dup.warn(f"This object shadows the module {ob.full_name!r} at {ob.source_path.as_posix()!r}")
                    # there is another object by the same name, place it first in the all_objects stack.
                    ob.root.all_objects[ob.full_name] = dup
    
    def visit_Function(self, ob: pydocspec.Function) -> None:
        # Ensures that property setter and deleters do not shadow the getter.
        if ob.is_property_deleter or \
           ob.is_property_setter:
            for dup in ob.root.all_objects.getdup(ob.full_name):
                if isinstance(dup, pydocspec.Function) and dup.is_property:
                    ob.root.all_objects[ob.full_name] = dup
    
    # TODO: same for overload functions, other instances of the issue ?

class _DocSourcesSetter(visitors.ApiObjectVisitorExt):
    # TODO: this will be correct at the moment where we're using astorid to load AST from 
    # c-extensions. For now, it works with pure-python.
    when = genericvisitor.When.AFTER
    def unknown_depart(self, ob: pydocspec.ApiObject) -> None:
        ob.doc_sources = data_attr.doc_sources(ob)

class _DefaultLocationSetter(visitors.ApiObjectVisitorExt):
    when = genericvisitor.When.BEFORE
    _default_location = _model.Location(filename='<unknown>', lineno=0)
    def unknown_visit(self, ob: _model.ApiObject) -> None:
        # Location attribute should be always set from the builder, though.
        # Make the location attribute non-optional, reduces annoyance.
        # TODO: Be smarter and use parents location when possible. 
        # Fill the filename attribute on object that have only the lineno.
        if ob.location is None:
            ob.location = self._default_location #type:ignore[unreachable]    

class PostBuildVisitor1(visitors.ApiObjectVisitor):

    def visit_Module(self, ob: pydocspec.Module) -> None:
        if not ob.dunder_all:
            ob.dunder_all = mod_attr.dunder_all(ob)
        ob.docformat = mod_attr.docformat(ob)
        if not ob.is_package:
            ob.is_package = mod_attr.is_package(ob)
    
    def visit_Class(self, ob: pydocspec.Class) -> None:
        ob.resolved_bases = class_attr.resolved_bases(ob)        
        # we don't need to re compute the MRO if the tree has beed created from astroid and there is
        # no c-extensions.
        ob.mro = class_attr.mro(ob)

        ob.is_exception = class_attr.is_exception(ob)
        ob.constructor_method = class_attr.constructor_method(ob)

        class_attr.process_subclasses(ob) # Setup the `pydocspec.Class.subclasses` attribute.
    
    def visit_Function(self, ob: pydocspec.Function) -> None:
        ob.is_property = func_attr.is_property(ob)
        ob.is_property_setter = func_attr.is_property_setter(ob)
        ob.is_property_deleter = func_attr.is_property_deleter(ob)
        ob.is_async = func_attr.is_async(ob)
        ob.is_method = func_attr.is_method(ob)
        ob.is_classmethod = func_attr.is_classmethod(ob)
        ob.is_staticmethod = func_attr.is_staticmethod(ob)
        ob.is_abstractmethod = func_attr.is_abstractmethod(ob)
    
    def visit_Data(self, ob: pydocspec.Data) -> None:
        ob.is_instance_variable = data_attr.is_instance_variable(ob)
        ob.is_class_variable = data_attr.is_class_variable(ob)
        ob.is_module_variable = data_attr.is_module_variable(ob)
        ob.is_alias = data_attr.is_alias(ob)
        ob.is_constant = data_attr.is_constant(ob)
        # Populate a list of aliases for each objects.
        # TODO: this will be correct at the moment where we're using astorid to laod AST from 
        # c-extensions. For now, it works with pure-python.
        data_attr.process_aliases(ob)

    def unknown_visit(self, ob: _model.ApiObject) -> None:
        ...
    def unknown_departure(self, ob: _model.ApiObject) -> None:
        ...

post_build_visitor0 = PostBuildVisitor0()
post_build_visitor0.extensions.add(_DuplicateWhoShadowsWhoHandling,
                                   _MroFromAstroidSetter,)
post_build_visitor1 = PostBuildVisitor1()
post_build_visitor1.extensions.add(_DefaultLocationSetter,
                                  _DocSourcesSetter,)

def post_build(root: pydocspec.TreeRoot) -> None:
    for mod in root.root_modules: 
        mod.walk(post_build_visitor0)

    for mod in root.root_modules: 
        mod.walk(post_build_visitor1)

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
        processor = cls(processes={0: post_build})
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