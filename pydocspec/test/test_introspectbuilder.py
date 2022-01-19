import os
from pathlib import Path
from re import A
import subprocess
from pydocspec import astbuilder, introspect, specfactory, Options, load_python_modules
import pydocspec
from . import tree_repr

factory = specfactory.Factory.default()
testpackages = Path(__file__).parent / 'testpackages'

def test_introspec_functions_classes() -> None:
    root = factory.TreeRoot()

    mod = introspect.introspect_module(root, 
        testpackages / 'introspec_regular_python' / 'mod.py', 
        'mod', 
        None)

    treerepr = tree_repr(mod)

    assert "Module 'mod' at l.0" in treerepr, treerepr
    assert "Class 'MyClass'" in treerepr, treerepr
    assert "Function 'load'" in treerepr, treerepr
    assert "Function 'dump'" in treerepr, treerepr
    assert "Function 'my_utility_func'" in treerepr, treerepr

    assert str(root.all_objects['mod.my_utility_func'].signature()) == '(a, b)' # missing: -> float'

def test_build_and_introspec_cython_based_C_extension_with_python_suclass() -> None:

    c_extension_base_class_path = testpackages / 'c_extension_base_class'
    setup_path = c_extension_base_class_path / 'setup.py'
    package_path = c_extension_base_class_path / 'mymodule'
    
    # build extension
    try:
        cwd = os.getcwd()
        code, outstr = subprocess.getstatusoutput(f'cd {c_extension_base_class_path} && python3 setup.py build_ext --inplace')
        os.chdir(cwd)
        
        assert code==0, outstr
        assert "building 'mymodule.base_class' extension" in outstr

        options=Options(introspect_c_modules=True)

        root = load_python_modules([package_path], options=options)

        base = root.all_objects['mymodule.base_class.BaseClass']
        derived = root.all_objects['mymodule.derived_class.DerivedClass']

        assert isinstance(base, pydocspec.Class)
        assert isinstance(derived, pydocspec.Class)

        assert base in derived.resolved_bases
        assert derived in base.subclasses

    finally:
        # cleanup
        subprocess.getoutput(f'rm -f {package_path}/*.so')
        subprocess.getoutput(f'rm -f {package_path}/*.c')



    