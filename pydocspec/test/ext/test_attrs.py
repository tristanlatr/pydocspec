from pydocspec.ext.opt.attrs import AttrsClassMixin, AttrsDataMixin
from pydocspec.test import _optional_extensions_enabled

def test_attrs_class() -> None:
    mod = _optional_extensions_enabled.mod_from_text(
        """
        import attr
        import typing
        
        @attr.s(auto_attribs=True)
        class Attrs:
            i : int
            l = attr.ib(factory=list)

            dev: typing.ClassVar = False
            stg: typing.ClassVar[bool] = False

            def __attrs_post_init__(self) -> None:
                self.name:str = 'My Name'
        """
    )
    klass = mod['Attrs']
    attr1 = mod['Attrs.i']
    attr2 = mod['Attrs.l']
    attr3 = mod['Attrs.dev']
    attr4 = mod['Attrs.stg']
    # attr5 = mod['Attrs.name'] # not working right now

    assert isinstance(klass, AttrsClassMixin)
    assert isinstance(attr1, AttrsDataMixin)
    assert isinstance(attr2, AttrsDataMixin)
    assert isinstance(attr3, AttrsDataMixin)
    assert isinstance(attr4, AttrsDataMixin)
    # assert isinstance(attr5, AttrsDataMixin)

    assert klass.attrs_decoration is not None
    assert klass.uses_attrs_auto_attribs == True

    assert attr1.is_attrs_attribute == True
    assert attr2.is_attrs_attribute == True
    assert attr3.is_attrs_attribute == False
    assert attr4.is_attrs_attribute == False
    # assert attr5.is_attrs_attribute == False