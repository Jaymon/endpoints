#!/usr/bin/env python
# http://docs.python.org/distutils/setupscript.html
# http://docs.python.org/2/distutils/examples.html

import sys
from setuptools import setup, find_packages
import ast
import os


name = 'endpoints'
version = ''
with open(os.path.join(name, "__init__.py"), 'rU') as f:
    for node in (n for n in ast.parse(f.read()).body if isinstance(n, ast.Assign)):
        node_name = node.targets[0]
        if isinstance(node_name, ast.Name) and node_name.id.startswith('__version__'):
            version = node.value.s
            break

if not version:
    raise RuntimeError('Unable to find version number')


setup(
    name=name,
    version=version,
    description='Get an api up and running quickly',
    author='Jay Marcyes',
    author_email='jay@marcyes.com',
    url='http://github.com/firstopinion/{}'.format(name),
    packages=find_packages(),
    license="MIT",
    install_requires=['decorators'],
    tests_require=['testdata', 'requests'],
    classifiers=[ # https://pypi.python.org/pypi?:action=list_classifiers
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries',
        'Programming Language :: Python :: 2.7',
    ],
    entry_points = {
        'console_scripts': [
            'endpoints-wsgiserver = {}.bin.wsgiserver:console'.format(name),
        ],
    },
    #test_suite = "endpoints_test",
)
