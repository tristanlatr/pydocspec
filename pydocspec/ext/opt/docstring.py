import dataclasses
from typing import Optional

import pydocspec
from pydocspec.ext import ExtRegistrar, ApiObjectMixin, ApiObjectVisitorExt

import docstring_parser

def setup_extension(r: ExtRegistrar) -> None:
    r.register_mixins(HasParsedDocstring)
    r.register_postbuild_visitors(DocstringParsingVis)

@dataclasses.dataclass
class HasParsedDocstring(ApiObjectMixin):
    parsed_docstring: Optional[docstring_parser.Docstring] = None

class DocstringParsingVis(ApiObjectVisitorExt):
    when = ApiObjectVisitorExt.When.AFTER
    def unknown_visit(self, ob: pydocspec.ApiObject) -> None:
        assert isinstance(ob, HasParsedDocstring)
        if ob.docstring is not None:
            ob.parsed_docstring = docstring_parser.parse(ob.docstring)