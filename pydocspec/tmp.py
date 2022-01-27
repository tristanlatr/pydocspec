            # try:
            #     mod = self.builder.get_processed_module(modname, raise_on_cycles=True)
            #     if mod is None:
            #         # We don't have any information about the module, so we don't know
            #         # what names to import.
            #         self.current.module.warn(f"import * from unknown module: '{modname}'. Cannot trace all indirections.", 
            #                                 lineno_offset=node.lineno)
            #         return
                
                # for i in self._newIndirectionsFromWildcardImport(modname, lineno=node.lineno, is_type_guarged=is_type_guarged):
                #     self.add_object(i, push=False)
            
            # except CyclicImport as e:

            #     # TODO: Delete the whole thing because we can use astroid instead, or can we?

            #     # this is a lot of parameters...
            #     unresolved = UnresolvedImportAll(
            #         f'from_{e.module.full_name}_newIndirectionsFromWildcardImport',  #TODO: find a new name that is more explicit
            #         self.root.factory.Location(self.module.location.filename, node.lineno), 
            #         docstring=None, 
            #         target='*',
            #         is_type_guarged=is_type_guarged,
            #         state=self.state.mark(), 
            #         module_visitor=self, 
            #         from_module=e.module,)
            #     self.add_object(unresolved, push=False)


##################################

# class UnknownFieldValue:
#     ...
# class UnknownList(UnknownFieldValue, list):
#     ...

# @dataclasses.dataclass(repr=False)
# class UnknownObject(_model.ApiObject, abc.ABC):
#     # object placed to signify that something could not be resolved during the building.
#     # no UnknownObject should be left once the tree is built
#     state: basebuilder.TreeWalkingState.MarkedTreeWalkingState
#     module_visitor: 'BuilderVisitor'

#     def restore_vistitor_state(self) -> None:
#         self.module_visitor.state.restore(self.state)

#     @abc.abstractmethod
#     def resolve(self, is_last_iteration:bool) -> Optional[Union['_model.ApiObject', List['_model.ApiObject']]]:
#         """
#         returns None if cannot resolve
#         returns an empty list if resolved to nothing
#         returns a new ApiObject or a list of new ApiObjects, these will take the place of the UnknownObject.
#         """
#         ...

# @dataclasses.dataclass(repr=False)
# class UnresolvedImportAll(_model.Indirection, UnknownObject):
#     # unresolved "from mod import *" statement
    
#     from_module: _model.Module = cast(_model.Module, None) # must be passed at init time

#     def _is_safe_to_import_all_from(self, mod: _model.Module) -> Tuple[bool, List['UnresolvedImportAll']]:
#         # it's safe to import all from a module when all imports not in TYPE_CHECKING
#         # blocks are resolved.
#         class Vis(genericvisitor.Visitor[_model.ApiObject]):
#             def __init__(self) -> None:
#                 self.is_safe = True
#                 self.unresolved_imports = []
#             def unknown_visit(self, ob: _model.ApiObject) -> None: pass
#             def visit_UnresolvedImportAll(self, ob: UnresolvedImportAll) -> None:
#                 # take into account first level imports only
#                 if (not ob.is_type_guarged) and ob.parent is ob.module:
#                     self.is_safe = False
#                     self.unresolved_imports.append(ob)
#         v = Vis()
#         mod.walk(v)
#         return v.is_safe, v.unresolved_imports

#     def resolve(self, is_last_iteration:bool) -> Optional[Union['_model.ApiObject', List['_model.ApiObject']]]:
#         is_safe_to_process_imports, unresolved = self._is_safe_to_import_all_from(self.from_module)
#         if is_safe_to_process_imports or is_last_iteration:
#             # Could add a warning here to get more precise import processing failures.
#             return list(self.module_visitor._newIndirectionsFromWildcardImport(self.from_module, 
#                 lineno=self.location.lineno, 
#                 is_type_guarged=self.is_type_guarged))
#         else:
#             return None

# @attr.s
# class ResolvedField:
#     ob: _model.ApiObject = attr.ib()
#     field: str = attr.ib()
#     value: Any = attr.ib()

# @attr.s
# class UnknownFieldResolver(abc.ABC):
#     ob: _model.ApiObject = attr.ib()

#     field: ClassVar[str] = cast(str, NotImplemented) # must be set on subclasses
#     klass: ClassVar[str] = cast(str, NotImplemented) # must be set on subclasses

#     @abc.abstractmethod
#     def resolve(self, is_last_iteration:bool) -> Optional[ResolvedField]:
#         # returns None if cannot resolve
#         # returns ResolvedField otherwise
#         ...

# class ResolvedBasesResolver(UnknownFieldResolver):
#     klass = 'Class'
#     field = 'resolved_bases'

#     def resolve(self, is_last_iteration:bool) -> Optional[ResolvedField]:
#         ...

# @attr.s(auto_attribs=True)
# class UnknownResolver:

#     root: '_model.TreeRoot'
#     not_sure: List['_model.ApiObject'] = attr.ib(factory=list)
#     unresolved: List['_model.ApiObject'] = attr.ib(factory=list)
#     _MAX_ITERATIONS = 10

#     class UnknownResolverVisitor(genericvisitor.Visitor[_model.ApiObject]):
#         def __init__(self, is_last_iteration:bool) -> None:
#             self.resolved = []
#             self.unresolved = []
#             self.is_last_iteration = is_last_iteration
#         @property
#         def nb_resolved(self) -> int:
#             return len(self.resolved)
#         @property
#         def nb_unresolved(self)->int:
#             return len(self.unresolved)
        
#         def unknown_visit(self, ob: _model.ApiObject) -> None:
#             if isinstance(ob, UnknownObject):
#                 self._resolve_ob(ob)
#             # else:
#             #     self._resolve_fields(ob)

#         def _resolve_fields(self, ob: _model.ApiObject) -> None:
#             for field_name, value in iter_fields(ob):
#                 if isinstance(value, _model.UnknownFieldValue):
#                     ...
        
#         def _resolve_ob(self, ob: UnknownObject) -> None:
#             ob.restore_vistitor_state()
#             resolved = ob.resolve(self.is_last_iteration)
#             if resolved is not None:
#                 self.resolved.append(ob)
#                 ob.replace(resolved)
#             else:
#                 self.unresolved.append(ob)
#                 if self.is_last_iteration:
#                     ob.remove()

#     def process(self) -> None:
#         _next_iteraration_is_last = False
#         for i in range(1, self._MAX_ITERATIONS+1):

#             is_last_iteration = (i==self._MAX_ITERATIONS) or _next_iteraration_is_last
#             resolver = self.UnknownResolverVisitor(is_last_iteration)
#             for mod in self.root.root_modules: 
#                 # change the order of processing on each iterations
#                 if i%2==0: genericvisitor.walk(mod, resolver, _model.ApiObject._members)
#                 else: genericvisitor.walk(mod, resolver, lambda ob: reversed(ob._members()))
            
#             if resolver.nb_resolved==0:
#                 if resolver.nb_unresolved==0:
#                     # logging.getLogger('pydocspec').info(
#                     #   f"Resolved all unknown nodes after {i} iterations")
#                     break
#                 _next_iteraration_is_last = True
#                 logging.getLogger('pydocspec').info(
#                   f"Blocked resolving unknown nodes after {i} iterations")
#                 # doing a last iteration with is_last_iteration=True
            
#             elif is_last_iteration:
#                 self.not_sure.extend(resolver.resolved)
            
#             if is_last_iteration:
#                 logging.getLogger('pydocspec').warning(
#                     "Incomplete analysis, "
#                     "probably due to import cycles.")
#                 break
        
#         # if self.not_sure:
#         #     logging.getLogger('pydocspec').info(f"Unsure of the values of {', '.join(o.full_name for o in self.not_sure)}")
#         # if self.unresolved:
#         #     logging.getLogger('pydocspec').info(f"Could not resolve values of {', '.join(o.full_name for o in self.unresolved)}")
    