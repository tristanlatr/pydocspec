
from typing import Optional, cast

import pydocspec
from pydocspec.ext import ExtRegistrar, ApiObjectMixin, ApiObjectVisitorExt

import docstring_parser

def setup_extension(r: ExtRegistrar) -> None:
    r.register_mixins(HasParsedDocstring)
    r.register_postbuild_visitors(DocstringParsingVis)

class HasParsedDocstring(ApiObjectMixin):
    # def _init_attribs(self) -> None:
    #     cast(pydocspec.ApiObject, super())._init_attribs()
    #     self.
    parsed_docstring: Optional[docstring_parser.Docstring] = None

class DocstringParsingVis(ApiObjectVisitorExt):
    when = ApiObjectVisitorExt.When.AFTER
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        assert isinstance(ob, HasParsedDocstring)
        if ob.docstring is not None:
            ob.parsed_docstring = docstring_parser.parse(ob.docstring.content)
