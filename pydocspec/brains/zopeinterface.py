import pydocspec
from pydocspec import visitors

def dump(root:pydocspec.ApiObjectsRoot) -> None:
    for mod in root.root_modules:
        mod.walk(visitors.PrintVisitor())

# POST_PROCESSES = {
#     90: dump
# }
