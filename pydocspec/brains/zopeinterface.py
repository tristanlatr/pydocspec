import pydocspec
from pydocspec import visitors

def dump(root:pydocspec.TreeRoot) -> None:
    for mod in root.root_modules:
        mod.walk(visitors.PrintVisitor())

# pydocspec_processes = {
#     90: dump
# }
