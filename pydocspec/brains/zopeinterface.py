import pydocspec
from pydocspec import visitors

def dump(root:pydocspec.TreeRoot) -> None:
    for mod in root.root_modules:
        visitors.PrintVisitor().walk(mod)

# pydocspec_processes = {
#     90: dump
# }
