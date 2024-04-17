#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Setup script for json_configs."""

__author__ = 'Aaron Hosford'

from setuptools import setup
from codecs import open
from os import path

from json_configs import __version__

here = path.abspath(path.dirname(__file__))


# Default long description
long_description = """

JSON Configs
============

*JSON-compatible configuration & serialization*

JSON Configs is a framework for configuring arbitrary Python data structures in
a format that directly supports JSON serialization. 

Links
-----

-  `Source <https://github.com/hosford42/json_configs>`__
-  `Distribution <https://pypi.python.org/pypi/json_configs>`__

The package is available for download under the permissive `Revised BSD
License <https://github.com/hosford42/json_configs/blob/master/LICENSE>`__.

""".strip()


# Get the long description from the relevant file. First try README.rst,
# then fall back on the default string defined here in this file.
if path.isfile(path.join(here, 'README.rst')):
    with open(path.join(here, 'README.rst'),
              encoding='utf-8',
              mode='r') as description_file:
        long_description = description_file.read()

# See https://pythonhosted.org/setuptools/setuptools.html for a full list
# of parameters and their meanings.
setup(
    name='json_configs',
    version=__version__,
    author=__author__,
    author_email='hosford42@gmail.com',
    url='http://hosford42.github.io/json_configs',
    license='Revised BSD',
    platforms=['any'],
    description='JSON Configs: JSON-compatible configuration & serialization',
    long_description=long_description,

    # See https://pypi.python.org/pypi?:action=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Topic :: File Formats :: JSON',
        'Topic :: File Formats :: JSON :: JSON Schema',
        'Topic :: Utilities',
        'Typing :: Typed',

        # Specify the Python versions you support here. In particular,
        # ensure that you indicate whether you support Python 2, Python 3
        # or both.
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.12',
    ],

    keywords='json config configuration serialize serialization framework',
    packages=['json_configs'],

    test_suite="test_json_configs",
    tests_require=[],
)
