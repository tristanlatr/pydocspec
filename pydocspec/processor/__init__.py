"""
Processes the half baked model created by the builder to populate buch of fancy attributes.
"""

from importlib import import_module
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

import attr
import pydocspec
from pydocspec import _model, brains, visitors

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
    when = visitors.ApiObjectVisitorExt.When.BEFORE
    def unknown_visit(self, ob: pydocspec.Class) -> None:
        pass
    def visit_Class(self, ob: pydocspec.Class) -> None:
        # This can set Class.mro attr to NotImplemented, we take of it in the regular post build visitor.
        ob.mro = class_attr.mro_from_astroid(ob)

class _DuplicateWhoShadowsWhoHandling(visitors.ApiObjectVisitorExt):
    # Duplicate objects handling: (in post-build)
    # - For duplicate Data object (pretty common), we unify the information present in all Data objects
    #   under a single object. Information denifed after wins, but we only keep the first object created.
    #   If an instance varaible shadows a class variable, it will be considered as instance variable.

    # - In a class, a Data definition sould not shadow another object that is not a Data, 
    #       even if the object is inherited. So if that happens, it's most probably a bound method,
    #       it will simply be ignored (we can leave a warning).
    # - A submodule can be shadowed by a another name by the same name in the package's __int__.py file.
    # - In a class, functions with the same name might be properties/overloaded function, so we should unify them under a single Function object
    when = visitors.ApiObjectVisitorExt.When.BEFORE
    
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
    when = visitors.ApiObjectVisitorExt.When.AFTER
    def unknown_depart(self, ob: pydocspec.ApiObject) -> None:
        ob.doc_sources = data_attr.doc_sources(ob)

class _DefaultLocationSetter(visitors.ApiObjectVisitorExt):
    when = visitors.ApiObjectVisitorExt.When.BEFORE
    _default_location = _model.Location(filename='<unknown>', lineno=0)
    def unknown_visit(self, ob: _model.ApiObject) -> None:
        # Location attribute should be always set from the builder, though.
        # Make the location attribute non-optional, reduces annoyance for modules 
        # comming from c-extensions.
        if ob.location is None:
            ob.location = ob.root.factory.Location(None, lineno=0)
        if ob.location.lineno is None:
            ob.location.lineno = 0
        if ob.location.filename is None:
            ob.location.filename = ob.module.location.filename
        if ob.location.filename is None:
            ob.location.filename = '<unknown>'


class PostBuildVisitor1(visitors.ApiObjectVisitor):

    def visit_Module(self, ob: pydocspec.Module) -> None:
        if not ob.dunder_all:
            ob.dunder_all = mod_attr.dunder_all(ob)
        ob.docformat = mod_attr.docformat(ob)
        if not ob.is_package:
            ob.is_package = mod_attr.is_package(ob)
    
    def visit_Class(self, ob: pydocspec.Class) -> None:
        ob.resolved_bases = class_attr.resolved_bases(ob)        
        # we don't need to re compute the MRO if the tree has beed created from astroid,
        # so this why we compute it only if it's marked as NotImplemented (from mro_from_astroid()).
        if ob.mro == NotImplemented:
            ob.mro = class_attr.mro(ob)

        ob.is_exception = class_attr.is_exception(ob)
        ob.constructor_method = class_attr.constructor_method(ob)
        ob.inherited_members = class_attr.inherited_members(ob)
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

@attr.s(auto_attribs=True)
class Processor:
    """
    Populate `pydocspec` attributes by applying processing to a newly created `pydocspec.TreeRoot` instance coming from the `astbuilder`. 

    At the point of the post processing, the root `pydocspec.Module` instances should have 
    already been added to the `pydocspec.TreeRoot.root_modules` attribute.
    
    Post-build is done when there are no more unprocessed modules.

    Analysis of relations between documentables should be done in post-build,
    without the risk of drawing incorrect conclusions because modules
    were not fully processed yet.

    Attributes:
        post_build_visitor: visitors.ApiObjectVisitor
    """ 

    visitor_extensions: Set[Union['visitors.ApiObjectVisitorExt', Type['visitors.ApiObjectVisitorExt']]] = attr.ib(factory=set)
    """
    Post-build visitor extensions.
    """

    def post_build(self, root: pydocspec.TreeRoot) -> None:
        """
        Apply post-build process on the tree. This is required. Called automatically when using `astbuilder.Builder`.

        .. python::

            root: pydocspec.TreeRoot
            pp = processor.Processor()
            pp.visitor_extensions.add(MyCustomVisitor)
            pp.post_build(root)

        :note: If you are creating a tree manually, you should run this on your tree as well. 
        """

        # do some warnings

        if len(root.root_modules) != len(set(id(m) for m in root.root_modules)):
            logging.getLogger('pydocspec').warning(
                f"Duplicate root module in : {', '.join(m.full_name for m in root.root_modules)}")

        # init visitors 

        _post_build_visitor0 = PostBuildVisitor0()

        _post_build_visitor0.extensions.add(_DefaultLocationSetter, 
                                            _DuplicateWhoShadowsWhoHandling, 
        # order is important here other wise we can get a Type error 
        # when warning in stuff that don't have a lineno, 
        # namely classes comming from c-extensions.
                                            _MroFromAstroidSetter, )
        
        post_build_visitor = PostBuildVisitor1()
        post_build_visitor.extensions.add(_DocSourcesSetter)

        # add extensions

        post_build_visitor.extensions.add(*self.visitor_extensions)

        # run visitors

        for mod in root.root_modules: 
            mod.walk(_post_build_visitor0)

        for mod in root.root_modules: 
            mod.walk(post_build_visitor)