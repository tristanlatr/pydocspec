

import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, TextIO, Tuple, Union, overload
import sys
import io
import json
import textwrap
import pytest

import pydocspec
from pydocspec import (_model, converter, Options, _docspec, 
    load_python_modules, 
    load_python_modules_with_docspec_python,
    builder_from_options, _setup_stdout_logger)

if TYPE_CHECKING:

    import docspec
    
    # Because pytest 6.1 does not yet export types for fixtures, we define
    # approximations that are good enough for our test cases:

    from typing_extensions import Protocol

    class CaptureResult(Protocol):
        out: str
        err: str

    class CapSys(Protocol):
        def readouterr(self) -> CaptureResult: 
            ...
    class CapLog(Protocol):
        text:str
        def set_level(self, level:str, logger:str) -> None:
            ...
    
    class ModFromTextFunction(Protocol):
        # @overload
        # def __call__(text:str) -> 'pydocspec.Module': ...
        # @overload
        # def __call__(text:str, modname:str) -> 'pydocspec.Module': ... 
        # fixes mypy error: 'No overload variant of "__call__" of "ModFromTextFunction" matches argument types "str", "str"  [call-overload]'
        def __call__(*args:Any, **kwargs:Any) -> 'pydocspec.Module': ...

else:
    CapLog = object
    CapSys = object
    ModFromTextFunction = object

posonlyargs = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")
typecomment = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")

class _docspec_python:

    @staticmethod
    def load_python_modules(
        files: Sequence[Tuple[Optional[str], Union[TextIO, str]]],
        options: Any = None,
        encoding: Optional[str] = None,
        ) -> Iterable['docspec.Module']:
        # This function supports loading modules from StringIO
        # https://github.com/NiklasRosenstein/docspec/issues/75
        files = list(files) if files else []
        assert _docspec.upstream.docspec_python is not None
        for module_name, f in files:
            yield _docspec.upstream.docspec_python.parse_python_module(f, filename='<fromtext>', 
                module_name=module_name, options=options, encoding=encoding)

    @staticmethod
    def mod_from_text(text:str, modname:str='test') -> 'pydocspec.Module':
        assert _docspec.upstream.docspec is not None
        docspec_modules = list(_docspec_python.load_python_modules(
            files=[ (modname, io.StringIO(textwrap.dedent(text))) ]))
        docspec_modules[0].location = _docspec.upstream.docspec.Location('<fromtext>', 0)
        
        pydocspec_mod = converter.convert_docspec_modules(docspec_modules).root_modules[0]
        return pydocspec_mod

class _default_astbuilder:
    @staticmethod
    def mod_from_text(text:str, modname:str='test', options:Optional[Options]=None) -> 'pydocspec.Module':
        """
        For testing only. 
        
        Should not be used when there is more than 
        one module to process.
        """
        builder = builder_from_options(options)
        builder.add_module_string(text, modname=modname, path='<fromtext>')
        builder.build_modules()

        _mod = builder.root.all_objects[modname]
        assert isinstance(_mod, pydocspec.Module)
        return _mod

class _optional_extensions_enabled:
    @staticmethod
    def mod_from_text(text:str, modname:str='test') -> 'pydocspec.Module':
        return _default_astbuilder.mod_from_text(text, modname, Options(load_optional_extensions=True))

class _back_converter_round_trip1:
    @staticmethod
    def mod_from_text(text:str, modname:str='test') -> 'pydocspec.Module':
        """
        For testing only.
        """
        assert _docspec.upstream.docspec is not None

        _setup_stdout_logger('pydocspec', quiet=True)
        mod = _default_astbuilder.mod_from_text(text, modname)
        _setup_stdout_logger('pydocspec')

        docspec_mods = converter.back_convert_modules((mod,))
        raw_docspec_json: Dict[str, List[Any] ] = {'modules': []}
        for m in docspec_mods:
            raw_docspec_json['modules'].append(_docspec.upstream.docspec.dump_module(m))
        
        tmp = tempfile.gettempdir() + os.sep + '_docspec_modules.json'
        
        with open(tmp, 'w') as f:
            json.dump(raw_docspec_json, f)
        
        new_docspec_mods: List['docspec.Module'] = []

        with open(tmp, 'r') as f:
            data = json.load(f)
            new_docspec_mods.extend(_docspec.upstream.docspec.load_modules(data['modules']))
        
        os.remove(tmp)

        new_root = converter.convert_docspec_modules(new_docspec_mods)
        _mod = new_root.all_objects[modname]
        assert isinstance(_mod, pydocspec.Module)
        return _mod

mod_from_text_functions = [_default_astbuilder.mod_from_text, _optional_extensions_enabled.mod_from_text]
load_python_modules_param_functions = [load_python_modules]

if _docspec.upstream.docspec_python is not None:
    mod_from_text_functions.extend([_docspec_python.mod_from_text, ])
    # _back_converter_round_trip1.mod_from_text, # TODO: fix the converter semantic hints !
    load_python_modules_param_functions.extend([load_python_modules_with_docspec_python])

mod_from_text_param = pytest.mark.parametrize(
    'mod_from_text', mod_from_text_functions )

getbuilder_param = pytest.mark.parametrize(
    'getbuilder', (builder_from_options, 
            lambda: builder_from_options(Options(load_optional_extensions=True)))
    )

load_python_modules_param = pytest.mark.parametrize(
    'load_python_modules', load_python_modules_param_functions)

tree_repr = _model.tree_repr

