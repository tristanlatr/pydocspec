import pytest

import pydocspec
from pydocspec import _docspec

if _docspec.upstream.docspec is not None:
  import docspec
  from pydocspec import converter

  _mod1 = docspec.Module(name='a', location=docspec.Location('test.py', 0), docstring=None, members=[
      docspec.Indirection(name='Union', location=docspec.Location('test.py', 1), docstring=None, target='typing.Union'),
      docspec.Class(name='foo', location=docspec.Location('test.py', 2), 
        docstring=docspec.Docstring(content='This is class foo.', location=docspec.Location('test.py', 3)), 
        metaclass=None, bases=None, decorations=None, members=[
        docspec.Variable(name='val', location=docspec.Location('test.py', 4), 
          docstring=None, datatype='Union[int, float]', value='42'),
        docspec.Variable(name='alias', location=docspec.Location('test.py', 5), docstring=None, datatype=None, value='val'),
        docspec.Function(name='__init__', location=docspec.Location('test.py', 6), docstring=None, modifiers=None, args=[
          docspec.Argument(name='self', location=docspec.Location('test.py', 6), 
            type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value=None)
        ], return_type=None, decorations=None),
      ]),
      docspec.Variable(name='saila', location=docspec.Location('test.py', 8), docstring=None, datatype=None, value='foo.alias'),
    ])
  _mod1.sync_hierarchy()

  _mod2 = docspec.Module(name='a', location=docspec.Location('test.py', 0), docstring=None, members=[
      docspec.Indirection(name='Union', location=docspec.Location('test.py', 1), docstring=None, target='typing.Union'),
      docspec.Class(name='foo', location=docspec.Location('test.py', 2), 
        docstring=docspec.Docstring(content='This is class foo.', location=docspec.Location('test.py', 3)), 
        metaclass=None, bases=None, decorations=None, members=[
        docspec.Variable(name='val', location=docspec.Location('test.py', 4), 
          docstring=None, datatype='Union[int, float]', value='42'),
        docspec.Variable(name='alias', location=docspec.Location('test.py', 5), docstring=None, datatype=None, value='val'),
        docspec.Function(name='__init__', location=docspec.Location('test.py', 6), docstring=None, modifiers=None, args=[
          docspec.Argument(name='self', location=docspec.Location('test.py', 6), 
            type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value=None)
        ], return_type=None, decorations=None),
      ]),
      docspec.Class(name='foosub', location=docspec.Location('test.py', 8), 
        docstring=docspec.Docstring(content='This is subclass of class foo.', location=docspec.Location('test.py', 9)), 
        metaclass=None, bases=['foo'], decorations=None, members=[
        docspec.Function(name='__init__', location=docspec.Location('test.py', 10), docstring=None, modifiers=None, args=[
          docspec.Argument(name='self', location=docspec.Location('test.py', 10), 
            type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value=None)
        ], return_type=None, decorations=None),
      ]),
      docspec.Variable(name='saila', location=docspec.Location('test.py', 12), docstring=None, datatype=None, value='foo.alias'),
    ])
  _mod2.sync_hierarchy()

  _mod3 = docspec.Module(name='a', location=docspec.Location('test.py', 0), docstring=None, members=[
      docspec.Indirection(name='Union', location=docspec.Location('test.py', 1), docstring=None, target='typing.Union'),
      docspec.Class(name='foo', location=docspec.Location('test.py', 2), 
        docstring=docspec.Docstring(content='This is class foo.', location=docspec.Location('test.py', 3)), 
        metaclass=None, bases=None, decorations=None, members=[
        docspec.Variable(name='_val', location=docspec.Location('test.py', 4), docstring=None, datatype='Union[int, float]', value='42'),
        docspec.Variable(name='_alias', location=docspec.Location('test.py', 5), docstring=None, datatype=None, value='_val'),
        docspec.Function(name='__init__', location=docspec.Location('test.py', 6), docstring=None, modifiers=None, args=[
          docspec.Argument(name='self', location=docspec.Location('test.py', 6), 
            type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value=None)
      ], return_type=None, decorations=None),
      ]),
      docspec.Variable(name='saila', location=docspec.Location('test.py', 8), docstring=None, datatype=None, value='foo.alias'),
    ])

  _mod3.sync_hierarchy()

  _mod4 = docspec.Module(name='a', location=docspec.Location('test.py', 0), docstring=None, members=[
      docspec.Function(
        name='f',
        location=docspec.Location('test.py', 2),
        docstring=docspec.Docstring(content='This uses annotations and keyword-only arguments.', location=docspec.Location('test.py', 2)),
        modifiers=None,
        args=[
          docspec.Argument(name='a', location=docspec.Location('test.py', 2), type=docspec.Argument.Type.Positional, decorations=None, datatype='int', default_value=None),
          docspec.Argument(name='c', location=docspec.Location('test.py', 2), type=docspec.Argument.Type.KeywordOnly, decorations=None, datatype='str', default_value=None),
          docspec.Argument(name='opts', location=docspec.Location('test.py', 2), type=docspec.Argument.Type.KeywordRemainder, decorations=None, datatype='Any', default_value=None),
        ],
        return_type='None',
        decorations=[],
      ),
      docspec.Class(name='foo', location=docspec.Location('test.py', 2), 
        docstring=docspec.Docstring(content='This is class foo.', location=docspec.Location('test.py', 3)), 
        metaclass=None, bases=None, decorations=None, members=[
        docspec.Function(name='__init__', location=docspec.Location('test.py', 6), docstring=None, modifiers=None, args=[
          docspec.Argument(name='self', location=docspec.Location('test.py', 6), type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value=None),
          docspec.Argument(name='port', location=docspec.Location('test.py', 6), type=docspec.Argument.Type.Positional, decorations=None, datatype=None, default_value='8001'),
        ], return_type=None, decorations=None),
      ]),
    ])
  _mod4.sync_hierarchy()

  @pytest.fixture
  def mod1() -> docspec.Module:
    return _mod1

  @pytest.fixture
  def root1() -> pydocspec.TreeRoot:
    return converter.convert_docspec_modules([_mod1])
  @pytest.fixture
  def root2() -> pydocspec.TreeRoot:
    return converter.convert_docspec_modules([_mod2])
  @pytest.fixture
  def root3() -> pydocspec.TreeRoot:
    return converter.convert_docspec_modules([_mod3])
  @pytest.fixture
  def root4() -> pydocspec.TreeRoot:
    return converter.convert_docspec_modules([_mod4])
