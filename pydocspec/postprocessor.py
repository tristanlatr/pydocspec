"""
Post processor and default post-processes. 
"""
from typing import Callable, Dict, Union, Any
from importlib import import_module
import attr

import docspec
import pydocspec
from pydocspec import genericvisitor, brains

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
        # TODO: Be smarter and use parents location when possible. Fill the filename attribute on object thatt have only the lineno.
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

# We should not need this anymore.
def set_root_post_process(root: pydocspec.ApiObjectsRoot) -> None:
    for mod in root.root_modules:
        mod.walk(_PostProcessVisitorFirst(root))

def generic_post_process(root: pydocspec.ApiObjectsRoot) -> None:
    for mod in root.root_modules:
        mod.walk(_PostProcessVisitorSecond())

@attr.s(auto_attribs=True)
class PostProcessor:
    """
    Apply post processing to a newly created L{pydocspec.ApiObjectsRoot} instance. 

    At the point of the post processing, the root L{pydocspec.Module} instances should have 
    already been added to the L{pydocspec.ApiObjectsRoot.root_modules} attribute.
    
    Post-processes are applied when there are no more unprocessed modules.

    Analysis of relations between documentables should be done in a post-process,
    without the risk of drawing incorrect conclusions because modules
    were not fully processed yet.
    """ 
    
    # TODO: handle duplicates.
    post_processes: Dict[float, 'PostProcess'] = attr.ib(factory=dict)
    """
    A post process is a function of the following form::

        (root: pydocspec.ApiObjectsRoot) -> None
    """

    @classmethod
    def default(cls) -> 'PostProcessor':
        processor = cls()

        processor.post_processes[0.0] = set_root_post_process
        processor.post_processes[0.1] = generic_post_process

        for mod in brains.get_all_brain_modules():
            processor.import_post_processes_from(mod)
        return processor

    def import_post_processes_from(self, module:Union[str, Any]) -> None:
        """
        Will look for the special mapping C{POST_PROCESSES} in the provided module.
        """
        if isinstance(module, str):
            mod = import_module(module)
        else:
            mod = module
        if hasattr(mod, 'POST_PROCESSES'):
            post_process_definitions = mod.POST_PROCESSES # type:ignore[attr-defined]
            assert isinstance(post_process_definitions, dict), f"{mod}.POST_PROCESSES should be a dict, not {type(post_process_definitions)}."
            if any(post_process_definitions.values()):
                self.post_processes.update(post_process_definitions)
                return

            import warnings
            warnings.warn(f"No post processes added for module {mod}, check the validity of the POST_PROCESSES attribute.")

    def post_process(self, root: pydocspec.ApiObjectsRoot) -> None:
        """
        Apply post process on newly created L{pydocspec} tree. This is required.

        .. python::

            root: pydocspec.ApiObjectsRoot
            postprocessor.PostProcessor.default().post_process(root)

        @note: If you are creating a tree manually, you should run this on your tree as well. 
        """
        for priority in sorted(self.post_processes.keys()):
            process = self.post_processes[priority]
            process(root)

PostProcess = Callable[[pydocspec.ApiObjectsRoot], None]
"""
A post process is a function of the following form::

    (root: pydocspec.ApiObjectsRoot) -> None
"""
