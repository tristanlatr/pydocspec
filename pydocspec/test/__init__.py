
from typing import TYPE_CHECKING
import sys
import pytest

from pydocspec import (specfactory, 
    load_python_modules, 
    load_python_modules_with_docspec_python,
    _model,
    visitors)

posonlyargs = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")
typecomment = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")

default_factory = specfactory.Factory.default()
with_brain_factory = specfactory.Factory.default(load_brains=True)
rootcls_param = pytest.mark.parametrize(
    'rootcls', (with_brain_factory.TreeRoot, default_factory.TreeRoot)
    )
builderfunc_param = pytest.mark.parametrize(
    'builderfunc', (load_python_modules, load_python_modules_with_docspec_python)
    )
# Because pytest 6.1 does not yet export types for fixtures, we define
# approximations that are good enough for our test cases:

if TYPE_CHECKING:
    from typing_extensions import Protocol

    class CaptureResult(Protocol):
        out: str
        err: str

    class CapSys(Protocol):
        def readouterr(self) -> CaptureResult: ...
else:
    CapSys = object


def tree_repr(obj: _model.ApiObject) -> str:
    _repr_vis = visitors.ReprVisitor()
    obj.walk(_repr_vis)
    return _repr_vis.repr.strip()