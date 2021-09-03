
from typing import TYPE_CHECKING
import sys
import pytest

from pydocspec import specfactory

posonlyargs = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")
typecomment = pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python 3.8")

default_factory = specfactory.Factory.default()
no_brain_factory = specfactory.Factory.default(load_brains=False)
rootcls_param = pytest.mark.parametrize(
    'rootcls', (no_brain_factory.ApiObjectsRoot, default_factory.ApiObjectsRoot)
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

