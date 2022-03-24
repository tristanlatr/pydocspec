from typing import Any, List

import astroid.nodes
import astroid.util
import astroid.inference
import astroid.helpers

from pydocspec import _model, astroidutils, ext, visitors
from pydocspec.processor import helpers

class Infer__all__Operations(visitors.AstVisitor):
    """
    Walks the module level ast tree and infer list operations results to ``self.names``. 
    """

    SUPPORTED_OPS = set(('append', 'extend', 'remove'))

    def __init__(self, names: List[str], mod: _model.ApiObject) -> None:
        super().__init__(extensions=None)
        self.names = names
        self.mod = mod

    def _skip(self, o:Any) -> None:
        raise self.SkipNode()

    # Ignore operations inside functions, classes and comprehensions.
    visit_ClassDef = _skip
    visit_Lambda = _skip
    visit_FunctionDef = _skip
    visit_AsyncFunctionDef = _skip
    visit_DictComp = _skip
    visit_GeneratorExp = _skip
    visit_ListComp = _skip
    visit_SetComp = _skip
    
    def visit_Call(self, node: astroid.nodes.Call) -> None:
        
        call_func = astroidutils.node2dottedname(node.func, strict=True)
        
        if not call_func or len(call_func) != 2 or call_func[0] != '__all__':
            # Not a call to __all__.something()
            return
        
        meth = call_func[1]
        if meth not in self.SUPPORTED_OPS :
            self.mod.warn(f"Can't infer result of call to '__all__.{meth}()'.", 
                          lineno_offset=node.lineno)
            return
        
        # All supported operations only take one positional argument 
        # so we don't need to validate args with astroidutils.bind_args()
        if len(node.args)!=1:
            self.mod.warn(f"Invalid call to '__all__.{meth}()'.", 
                          lineno_offset=node.lineno)
            return

        # Infer argument value
        ivalue = astroid.helpers.safe_infer(node.args[0]) # Safe inference.
        if ivalue in (astroid.util.Uninferable, None):
            self.mod.warn(f"Can't infer '__all__.{meth}()' argument value.", 
                          lineno_offset=node.lineno)
            return
        
        try:
            value = astroidutils.literal_eval(ivalue)
        except ValueError as e:
            self.mod.warn(f"Can't infer '__all__.{meth}()' argument value. {e}", 
                          lineno_offset=node.lineno)
            return

        if meth == 'append':
            if not isinstance(value, (str,)):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be a str, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            self.names.append(value)
        elif meth == 'extend':
            if not hasattr(value, '__iter__'):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be an iterable, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            for i, name in enumerate(value):
                if not isinstance(name, str):
                    self.mod.warn(f"Element {i} of the iterable passed to '__all__.{meth}()' has an invalid type, should be a str, not {name!r}.", 
                          lineno_offset=node.lineno)
                    continue
                self.names.append(name)
        elif meth == 'remove':
            if not isinstance(value, (str,)):
                self.mod.warn(f"Argument passed to '__all__.{meth}()' has an invalid type, should be a str, not {value!r}.", 
                          lineno_offset=node.lineno)
                return
            try:
                self.names.remove(value)
            except ValueError:
                self.mod.warn(f"Argument passed to '__all__.{meth}()' is invalid, {value!r} is not present in __all__.", 
                          lineno_offset=node.lineno)
                return

class InferenceTip__all__Variable(ext.AstroidInferenceTip):
    """
    Infernce tip for the __all__ variable.
    Accounts for module level modifications of the __all__ `list`.
    """
    node_class = astroid.nodes.AssignName

    def predicate(self, node: astroid.nodes.AssignName) -> bool:
        return node.name == '__all__' and isinstance(node.frame(future=True), 
                # do not process assigments to __all__ inside functions
                (astroid.nodes.Module,))

    def inference_tip(self, node: astroid.nodes.AssignName, ctx: Any) -> 'astroid.nodes.NodeNG':
        for ivalue in astroid.inference.infer_assign(node, ctx):
            if ivalue == astroid.util.Uninferable:
                yield ivalue
                # Value is Uninferable
                continue
            try:
                names = astroidutils.literal_eval(ivalue)
            except ValueError:
                yield ivalue
                # Value is not a literal, there is no point to go forward.
                continue
            
            if not isinstance(names, list):
                yield ivalue
                # Not a list, maybe tuple? 
                # Anyway, we only infer list operations for now.
                continue

            mod = helpers.ast2apiobject(self.root, node.root())
            if mod is None:
                yield ivalue
                # Only process __all__ variables on modules in the system.
                continue
            
            # Walks module level calls to __all__.something() and infer supported operations.
            Infer__all__Operations(names, mod).walk(mod._ast)

            # Create inferred result as nodes.
            ivalue = astroidutils.nodefactory.List(
                elts=[astroidutils.nodefactory.Const(n) for n in names]
            )

            yield ivalue
        
def setup_extension(r:ext.ExtRegistrar) -> None:
    r.register_astroid_transforms(InferenceTip__all__Variable)