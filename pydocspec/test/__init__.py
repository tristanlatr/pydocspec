
from typing import TYPE_CHECKING
import sys
import io
import textwrap
import pytest
import docspec
import docspec_python

from pydocspec import (_model, converter,
    load_python_modules, 
    load_python_modules_with_docspec_python,
    builder_from_options)

if TYPE_CHECKING:
    import pydocspec
    from pydocspec import astbuilder

# Because pytest 6.1 does not yet export types for fixtures, we define
# approximations that are good enough for our test cases:

    from typing_extensions import Protocol

    class CaptureResult(Protocol):
        out: str
        err: str

    class CapSys(Protocol):
        def readouterr(self) -> CaptureResult: ...
    
    class ModFromTextFunction(Protocol):
        def __call__(text:str, modname:str='test') -> 'pydocspec.Module':
            ...
else:
    CapSys = object
    ModFromTextFunction = object

posonlyargs = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")
typecomment = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")

class _docspec_python:
    @staticmethod
    def mod_from_text(text:str, modname:str='test') -> 'pydocspec.Module':
        docspec_modules = list(docspec_python.load_python_modules(
            files=[ (modname, io.StringIO(textwrap.dedent(text))) ]))
        docspec_modules[0].location = docspec.Location('<fromtext>', 0)
        
        pydocspec_mod = converter.convert_docspec_modules(docspec_modules).root_modules.pop()
        return pydocspec_mod

class _default_astbuilder:
    @staticmethod
    def mod_from_text(text:str, modname:str='test') -> 'pydocspec.Module':
        """
        For testing only. 
        
        Should not be used when there is more than 
        one module to process.
        """
        builder = builder_from_options()
        builder.add_module_string(text, modname=modname, path='<fromtext>')
        builder.build_modules()
        return builder.root.all_objects[modname]

mod_from_text_param = pytest.mark.parametrize(
    'mod_from_text', (_docspec_python.mod_from_text, 
                      _default_astbuilder.mod_from_text,)
    )

getbuilder_param = pytest.mark.parametrize(
    'getbuilder', (builder_from_options, )
    )

load_python_modules_param = pytest.mark.parametrize(
    'load_python_modules', 
        (load_python_modules, 
         load_python_modules_with_docspec_python,)
    )

tree_repr = _model.tree_repr