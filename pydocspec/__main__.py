import argparse
from pathlib import Path
from . import load_python_modules, _model

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument('modules', nargs='+', type=Path)
    args = parser.parse_args()
    root = load_python_modules(args.modules)
    for m in root.root_modules:
        print(_model.tree_repr(m))
