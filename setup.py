
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
from setuptools import setup
setup(
    name='pydocspec',
    version='0.0.0',
    author='tristanlatr',
    author_email='trislatr@gmail.com',
    description='Extends docspec for python specific usages.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/tristanlatr/pydocspec',
    project_urls = {
        "Bug Tracker": "https://github.com/tristanlatr/pydocspec/issues"
    },
    license='MIT',
    packages=['pydocspec'],
    include_package_data=True,
    install_requires=['docspec @ git+https://github.com/NiklasRosenstein/docspec.git#subdirectory=docspec', 
                      'docspec_python @ git+https://github.com/NiklasRosenstein/docspec.git#subdirectory=docspec-python', 
                      'cached-property', 'astor', 'typing_extensions'], 
)
