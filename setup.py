
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
from setuptools import setup, find_packages
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
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    install_requires=["docspec==1.0.2"], 
)
