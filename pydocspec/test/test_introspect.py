import os
from pathlib import Path
import sys
import subprocess
from pydocspec import Options, load_python_modules
import pydocspec
import pytest
from . import tree_repr

testpackages = Path(__file__).parent / 'testpackages'

@pytest.mark.skipif(sys.platform == "win32", reason="does not run on windows")
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
        #assert "building 'mymodule.base_class' extension" in outstr

        options=Options(introspect_c_modules=True)

        root = load_python_modules([package_path], options=options)

        base = root.all_objects['mymodule.base_class.BaseClass']
        derived = root.all_objects['mymodule.derived_class.DerivedClass']

        assert isinstance(base, pydocspec.Class)
        assert isinstance(derived, pydocspec.Class)

        assert base in derived.resolved_bases
        assert derived in base.subclasses

        # assert tree_repr(root.all_objects['mymodule']) == """"""

    finally:
        # cleanup
        subprocess.getoutput(f'rm -f {package_path}/*.so')
        subprocess.getoutput(f'rm -f {package_path}/*.c')



    