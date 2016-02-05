#!/usr/bin/env python
# http://docs.python.org/distutils/setupscript.html
# http://docs.python.org/2/distutils/examples.html

import sys
from setuptools import setup, find_packages
import ast

import endpoints
name = endpoints.__name__
version = endpoints.__version__

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
