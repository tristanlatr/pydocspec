# pydocspec

Pydocspec is a object specification for representing API documentation of a collection of related python modules. It offers facility to resolve names according to python lookups rules and provides additional informations. 

The object model is built on top of the [docspec](https://github.com/NiklasRosenstein/docspec) library. 

We provide our own loader, based on [astroid](https://github.com/PyCQA/astroid), a powefull AST analysis library that helps get better results, in particular for the inference of complex `__all__` module variables.

There is also the possiblity to create a `pydocspec` tree from `docspec_python` and the other way around, in which case `astroid` is not used. This can be used to serialize trees to JSON format and read them back into `pydocspec` tree.

The main goal of this project is to replace the 15 years old [pydoctor](https://github.com/twisted/pydoctor) ast builder that is becomming unmaintainable. 

Pydocspec focuses on Python semantic analysis, strives to be extensible, correct well documented and de-coupled from any presentation details.

This software is work in progress... API might change without deprecation notice.

Read the [API documentation](https://tristanlatr.github.io/pydocspec/pydocspec.html) for more information.
