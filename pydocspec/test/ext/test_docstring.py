from pydocspec.ext.opt.docstring import HasParsedDocstring
from pydocspec.test import _optional_extensions_enabled

def test_docstring() -> None:
    mod = _optional_extensions_enabled.mod_from_text(
        """
        import attr
        import typing
        
        class a:
            '''
            Docstring
            '''
        
        def b():
            '''
            Re docstring
            '''
        
        c = True
        '''
        Inline docstring
        '''
        """
    )
    a = mod['a']
    # b = mod['b']
    c = mod['c']

    assert isinstance(a, HasParsedDocstring)
    # assert isinstance(b, HasParsedDocstring)
    assert isinstance(c, HasParsedDocstring)

    assert a.parsed_docstring is not None
    assert c.parsed_docstring is not None
