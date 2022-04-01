from pathlib import Path
from typing import Callable, Sequence, Type
import logging

import pydocspec
from pydocspec import visitors
from . import CapLog, load_python_modules_param, CapSys

import astroid.builder
import astroid.manager
import astroid.transforms
testpackages = Path(__file__).parent / 'testpackages'

def test_astroid_test_wildcard() -> None:
    builder = astroid.builder.AstroidBuilder()

    b = builder.file_build(
        testpackages / 'cyclic_imports_all' / 'b.py', 
        'cyclic_imports_all.b')
    a = builder.file_build(
        testpackages / 'cyclic_imports_all' / 'a.py', 
        'cyclic_imports_all.a')
    top = builder.file_build(
        testpackages / 'cyclic_imports_all' / '__init__.py', 
        'cyclic_imports_all')

    assert b.wildcard_import_names() == ['B']
    assert a.wildcard_import_names() == ['A', 'B']

    builder._manager.clear_cache()

    mod = builder.string_build("""\
__all__=['_f']
class _f:
    pass
""", modname='mod')
    mod2 = builder.string_build("""\
from mod import *
i = _f()
""", modname='mod2')

    # assert mod2.locals.get('_f') is not None

# TODO: Adjust the rest of the tests once the builder is finished. 

# def test_relative_import() -> None:
#     system = root_from_testpackage("relativeimporttest")
#     cls = system.allobjects['relativeimporttest.mod1.C']
#     assert isinstance(cls, model.Class)
#     assert cls.bases == ['relativeimporttest.mod2.B']

# def test_package_docstring() -> None:
#     system = root_from_testpackage("relativeimporttest")
#     assert system.allobjects['relativeimporttest'].docstring == "DOCSTRING"

# def test_modnamedafterbuiltin() -> None:
#     # well, basically the test is that this doesn't explode:
#     system = root_from_testpackage("modnamedafterbuiltin")
#     # but let's test _something_
#     dict_class = system.allobjects['modnamedafterbuiltin.mod.Dict']
#     assert isinstance(dict_class, model.Class)
#     assert dict_class.baseobjects == [None]

# def test_nestedconfusion() -> None:
#     system = root_from_testpackage("nestedconfusion")
#     A = system.allobjects['nestedconfusion.mod.nestedconfusion.A']
#     assert isinstance(A, model.Class)
#     C = system.allobjects['nestedconfusion.mod.C']
#     assert A.baseobjects[0] is C

# def test_importingfrompackage() -> None:
#     system = root_from_testpackage("importingfrompackage")
#     system.getProcessedModule('importingfrompackage.mod')
#     submod = system.allobjects['importingfrompackage.subpack.submod']
#     assert isinstance(submod, model.Module)
#     assert submod.state is model.ProcessingState.PROCESSED

# def test_allgames() -> None:
#     """
#     Test reparenting of documentables.
#     A name which is defined in module 1, but included in __all__ of module 2
#     that it is imported into, should end up in the documentation of module 2.
#     """

#     system = root_from_testpackage("allgames")
#     mod1 = system.allobjects['allgames.mod1']
#     assert isinstance(mod1, model.Module)
#     mod2 = system.allobjects['allgames.mod2']
#     assert isinstance(mod2, model.Module)
#     # InSourceAll is not moved into mod2, but NotInSourceAll is.
#     assert 'InSourceAll' in mod1.contents
#     assert 'NotInSourceAll' in mod2.contents
#     # Source paths must be unaffected by the move, so that error messages
#     # point to the right source code.
#     moved = mod2.contents['NotInSourceAll']
#     assert isinstance(moved, model.Class)
#     assert moved.source_path is not None
#     assert moved.source_path.parts[-2:] == ('allgames', 'mod1.py')
#     assert moved.parentMod is mod2
#     assert moved.parentMod.source_path is not None
#     assert moved.parentMod.source_path.parts[-2:] == ('allgames', 'mod2.py')

@load_python_modules_param
def test_cyclic_imports(load_python_modules: Callable[[Sequence[Path]], pydocspec.TreeRoot]) -> None:
    """
    Test whether names are resolved correctly when we have import cycles.
    The test package contains module 'a' that defines class 'A' and module 'b'
    that defines class 'B'; each module imports the other. Since the test data
    is symmetrical, we will at some point be importing a module that has not
    been fully processed yet, no matter which module gets processed first.
    """

    system = load_python_modules([testpackages / 'cyclic_imports'])
    assert isinstance(system.all_objects['cyclic_imports'], pydocspec.Module)

    mod_a = system.all_objects['cyclic_imports.a']

    assert mod_a.expand_name('B') == 'cyclic_imports.b.B'
    mod_b = system.all_objects['cyclic_imports.b']
    assert mod_b.expand_name('A') == 'cyclic_imports.a.A'

# Wildcard-import rationale
# 
# Wilcard import from Modules:
# The asterisk when used in from <module_name> import *. 
# will import everything inside the module if we are talking 
# about a single module(a single file something like tools.py). 
# this kind of module does not have sub_modules.
# 
# Wilcard import from Packages:
# However, dealing with packages, calling from <package_name> import * 
# will import everything inside the __init__.py file of 
# the package but by default it will not import other sub_modules 
# inside the package unless you define a __all__ list and include 
# inside it the name of the sub_modules, objects and sub_packages 
# you would like to be exported by the sub_package
# 
# Wilcard import from Classes:
# No wildcard imports.
# 
# We don't even try to resolve wildcard imports in the case of a cycle,
# the value is deffered to astroid.

def test_cyclic_imports_all(caplog: CapLog) -> None:
    """
    Test whether names are resolved correctly when we have import cycles.
    The test package contains module 'a' that defines class 'A' and module 'b'
    that defines class 'B'; each module imports the other. Since the test data
    is symmetrical, we will at some point be importing a module that has not
    been fully processed yet, no matter which module gets processed first.
    """

    caplog.set_level('WARNING', 'pydocspec')

    system = pydocspec.load_python_modules([testpackages / 'cyclic_imports_all'])
    assert "Can't resolve cyclic wildcard imports" in caplog.text, caplog.text
    assert len(caplog.text.strip().split('\n')) == 1
    
    assert isinstance(system.all_objects['cyclic_imports_all'], pydocspec.Module)
    repr_vis = visitors.ReprVisitor(fields=['datatype', 'target', 'semantic_hints'])

    mod_a = system.all_objects['cyclic_imports_all.a']
    mod_b = system.all_objects['cyclic_imports_all.b']

    mod_b.walk(repr_vis)
    mod_a.walk(repr_vis)

    assert repr_vis.repr == """\
| - Module 'b' at l.0
| | - Indirection 'A' at l.1, target: 'cyclic_imports_all.a.A'
| | - Class 'B' at l.3
| | | - Variable 'a' at l.4, datatype: 'A', semantic_hints: [<VariableSemantic.CLASS_VARIABLE: 1>]
| - Module 'a' at l.0
| | - Indirection 'A' at l.1, target: 'cyclic_imports_all.b.A'
| | - Indirection 'B' at l.1, target: 'cyclic_imports_all.b.B'
| | - Class 'A' at l.3
| | | - Variable 'b' at l.4, datatype: 'B', semantic_hints: [<VariableSemantic.CLASS_VARIABLE: 1>]
"""
    assert mod_a.expand_name('B') == 'cyclic_imports_all.b.B'
    assert mod_b.expand_name('A') == 'cyclic_imports_all.a.A'

    # assert that Class 'B' exists
    assert isinstance(mod_b["B"], pydocspec.Class)

# Works only with pydocspec.astbuilder
def test_imports_all_many_level(caplog: CapLog) -> None:
    caplog.set_level('WARNING', 'pydocspec')
    system = pydocspec.load_python_modules([testpackages / 'imports_all_many_levels'])
    # assert not caplog.text, caplog.text
    assert len(caplog.text.strip().split('\n')) == 1 # because we can't resolve builtin types for now.
    assert isinstance(system.all_objects['imports_all_many_levels'], pydocspec.Module)
    repr_vis = visitors.ReprVisitor(fields=['is_package', 'target'])

    pack = system.all_objects['imports_all_many_levels']

    pack.walk(repr_vis)

    assert repr_vis.repr == """\
- Module 'imports_all_many_levels' at l.0, is_package: True
| - Module 'level1' at l.0, is_package: True
| | - Module 'level2' at l.0, is_package: True
| | | - Class 'l2' at l.1
| | - Indirection 'l2' at l.1, target: 'imports_all_many_levels.level1.level2.l2'
| | - Class 'l1' at l.3
| - Indirection 'l2' at l.1, target: 'imports_all_many_levels.level1.l2'
| - Indirection 'l1' at l.1, target: 'imports_all_many_levels.level1.l1'
"""
    assert pack.expand_name('l2') == 'imports_all_many_levels.level1.level2.l2'

# Works only with pydocspec.astbuilder
def test_cyclic_imports_all_many_level(caplog: CapLog) -> None:

    system = pydocspec.load_python_modules([testpackages / 'cyclic_imports_all_many_levels'])
    assert isinstance(system.all_objects['cyclic_imports_all_many_levels'], pydocspec.Module)
    repr_vis = visitors.ReprVisitor(fields=['is_package', 'target'])

    pack = system.all_objects['cyclic_imports_all_many_levels']

    pack.walk(repr_vis)

    assert repr_vis.repr == """\
- Module 'cyclic_imports_all_many_levels' at l.0, is_package: True
| - Module 'level1' at l.0, is_package: True
| | - Module 'level2' at l.0, is_package: True
| | | - Class 'l2' at l.2
| | - Indirection 'l2' at l.1, target: 'cyclic_imports_all_many_levels.level1.level2.l2'
| | - Class 'l1' at l.3
| - Indirection 'l2' at l.1, target: 'cyclic_imports_all_many_levels.level1.l2'
| - Indirection 'l1' at l.1, target: 'cyclic_imports_all_many_levels.level1.l1'
"""
    assert pack.expand_name('l2') == 'cyclic_imports_all_many_levels.level1.level2.l2'
