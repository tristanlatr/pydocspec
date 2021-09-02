import pytest

import docspec
import pydocspec
from pydocspec import converter

_mod1 = module = docspec.Module('a', docspec.Location('test.py', 0), None, [
    docspec.Indirection('Union', docspec.Location('test.py', 1), None, 'typing.Union'),
    docspec.Class('foo', docspec.Location('test.py', 2), docspec.Docstring('This is class foo.', docspec.Location('test.py', 3)), None, None, None, [
      docspec.Data('val', docspec.Location('test.py', 4), None, 'Union[int, float]', '42'),
      docspec.Data('alias', docspec.Location('test.py', 5), None, None, 'val'),
      docspec.Function('__init__', docspec.Location('test.py', 6), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None)
      ], None, None),
    ]),
    docspec.Data('saila', docspec.Location('test.py', 8), None, None, 'foo.alias'),
  ])
_mod1.sync_hierarchy()

_mod2 = module = docspec.Module('a', docspec.Location('test.py', 0), None, [
    docspec.Indirection('Union', docspec.Location('test.py', 1), None, 'typing.Union'),
    docspec.Class('foo', docspec.Location('test.py', 2), docspec.Docstring('This is class foo.', docspec.Location('test.py', 3)), None, None, None, [
      docspec.Data('val', docspec.Location('test.py', 4), None, 'Union[int, float]', '42'),
      docspec.Data('alias', docspec.Location('test.py', 5), None, None, 'val'),
      docspec.Function('__init__', docspec.Location('test.py', 6), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None)
      ], None, None),
    ]),
    docspec.Class('foosub', docspec.Location('test.py', 8), docspec.Docstring('This is subclass of class foo.', docspec.Location('test.py', 9)), None, ['foo'], None, [
      docspec.Function('__init__', docspec.Location('test.py', 10), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None)
      ], None, None),
    ]),
    docspec.Data('saila', docspec.Location('test.py', 12), None, None, 'foo.alias'),
  ])
_mod2.sync_hierarchy()

_mod3 = module = docspec.Module('a', docspec.Location('test.py', 0), None, [
    docspec.Indirection('Union', docspec.Location('test.py', 1), None, 'typing.Union'),
    docspec.Class('foo', docspec.Location('test.py', 2), docspec.Docstring('This is class foo.', docspec.Location('test.py', 3)), None, None, None, [
      docspec.Data('_val', docspec.Location('test.py', 4), None, 'Union[int, float]', '42'),
      docspec.Data('_alias', docspec.Location('test.py', 5), None, None, '_val'),
      docspec.Function('__init__', docspec.Location('test.py', 6), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None)
      ], None, None),
    ]),
    docspec.Data('saila', docspec.Location('test.py', 8), None, None, 'foo.alias'),
  ])
_mod3.sync_hierarchy()

_mod4 = module = docspec.Module('a', docspec.Location('test.py', 0), None, [
    docspec.Function(
      name='f',
      location=None,
      docstring=docspec.Docstring('This uses annotations and keyword-only arguments.', docspec.Location('test.py', 2)),
      modifiers=None,
      args=[
        docspec.Argument('a', docspec.Argument.Type.Positional, None, 'int', None),
        docspec.Argument('c', docspec.Argument.Type.KeywordOnly, None, 'str', None),
        docspec.Argument('opts', docspec.Argument.Type.KeywordRemainder, None, 'Any', None),
      ],
      return_type='None',
      decorations=[],
    ),
    docspec.Class('foo', docspec.Location('test.py', 2), docspec.Docstring('This is class foo.', docspec.Location('test.py', 3)), None, None, None, [
      docspec.Function('__init__', docspec.Location('test.py', 6), None, None, [
        docspec.Argument('self', docspec.Argument.Type.Positional, None, None, None),
        docspec.Argument('port', docspec.Argument.Type.Positional, None, None, '8001'),
      ], None, None),
    ]),
  ])
_mod4.sync_hierarchy()

@pytest.fixture
def mod1() -> docspec.Module:
  return _mod1

@pytest.fixture
def root1() -> pydocspec.ApiObjectsRoot:
  return converter.convert_docspec_modules([_mod1], root=True)
@pytest.fixture
def root2() -> pydocspec.ApiObjectsRoot:
  return converter.convert_docspec_modules([_mod2], root=True)
@pytest.fixture
def root3() -> pydocspec.ApiObjectsRoot:
  return converter.convert_docspec_modules([_mod3], root=True)
@pytest.fixture
def root4() -> pydocspec.ApiObjectsRoot:
  return converter.convert_docspec_modules([_mod4], root=True)
