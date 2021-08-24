
import pydocspec
import pytest

import docspec
import pydocspec

@pytest.fixture
def mod1() -> pydocspec.Module:
  module = docspec.Module('a', docspec.Location('test.py', 0), None, [
    docspec.Indirection('Union', docspec.Location('test.py', 1), None, 'typing.Union'),
    docspec.Class('foo', docspec.Location('test.py', 2), 'This is class foo.', None, None, None, [
      docspec.Data('val', docspec.Location('test.py', 4), None, 'Union[int, float]', '42'),
      docspec.Data('alias', docspec.Location('test.py', 5), None, None, 'val'),
      docspec.Function('__init__', docspec.Location('test.py', 6), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None)
      ], None, None),
    ]),
    docspec.Data('saila', docspec.Location('test.py', 8), None, None, 'foo.alias'),
  ])
  module.sync_hierarchy()
  return module
