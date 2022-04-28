
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
from setuptools import setup
setup(
    name='pydocspec',
    version='0.0.0',
    author='tristanlatr',
    author_email='trislatr at gmail.com',
    description='Pydocspec is a object specification for representing API documentation of a collection of related python modules.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/tristanlatr/pydocspec',
    project_urls = {
        "Bug Tracker": "https://github.com/tristanlatr/pydocspec/issues"
    },
    license='MIT',
    packages=['pydocspec'],
    include_package_data=True,
    install_requires=['cached_property', 
                      'astroid>=2.11.1',
                      'importlib_resources', ], 
    extras_require={
        'converter':['docspec==2.0.1'],

        'test':[
               'docspec==2.0.1', 
               'docspec_python==2.0.1', 
               'docstring_parser', 
               'pytest',
               'hypothesis',
               'cython'],

        'test-no-docspec':[
                'docstring_parser', 
                'pytest',
                'hypothesis',
                'cython'],
    }
)
