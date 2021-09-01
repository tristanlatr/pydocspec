#!/bin/bash
# This bash script builds the API documentation for pydocspec.

# Resolve source directory path. From https://stackoverflow.com/questions/59895/how-to-get-the-source-directory-of-a-bash-script-from-within-the-script-itself/246128#246128
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd $SCRIPT_DIR

# Stop if errors
set -euo pipefail
IFS=$'\n\t,'

# Figure the project version
project_version="$(python3 setup.py -V)"

# Figure commit ref
git_sha="$(git rev-parse HEAD)"
if ! git describe --exact-match --tags > /dev/null 2>&1 ; then
    is_tag=false
else
    git_sha="$(git describe --exact-match --tags)"
    is_tag=true
fi

# Init output folder
docs_folder="./apidocs/"
rm -rf "${docs_folder}"
mkdir -p "${docs_folder}"

# We generate the docs for the docspec module too, such that we can document 
# the methods inherited from docspec classes. 
curl https://raw.githubusercontent.com/NiklasRosenstein/docspec/develop/docspec/src/docspec/__init__.py > ./docspec.py

# Delete the file when the script exits
trap "rm -f ./docspec.py" EXIT

pydoctor \
    --project-name="pydocspec ${project_version}" \
    --project-url="https://github.com/tristanlatr/pydocspec" \
    --html-viewsource-base="https://github.com/tristanlatr/pydocspec/tree/${git_sha}" \
    --intersphinx=https://docs.python.org/3/objects.inv \
    --make-html \
    --quiet \
    --project-base-dir=.\
    --html-output="${docs_folder}" \
    ./docspec.py ./pydocspec/ || true 

echo "API docs generated in ${docs_folder}"
