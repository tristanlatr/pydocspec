"""
Submodules contains sets of mixin classes aplied to {ApiObject} in order to extends 
the functionalities for specific libraries. 
"""
from typing import Iterator
import sys

# On Python 3.7+, use importlib.resources from the standard library.
# On older versions, a compatibility package must be installed from PyPI.
if sys.version_info < (3, 7):
    import importlib_resources
else:
    import importlib.resources as importlib_resources

def get_all_brain_modules() -> Iterator[str]:
    """
    Get the full names of all the "brain" modules included in L{pydocspec}.
    """
    for name in importlib_resources.contents('pydocspec.brains'):
        if (not name.startswith('_') and importlib_resources.is_resource('pydocspec.brains', name)) and name.endswith('.py'):
            yield f"pydocspec.brains.{name.rstrip('.py')}"

