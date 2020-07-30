#!/usr/bin/env python
# http://docs.python.org/distutils/setupscript.html
# http://docs.python.org/2/distutils/examples.html

from setuptools import setup, find_packages
import re
import os
from codecs import open


name = "endpoints"
kwargs = {"name": name}

def read(path):
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            return f.read()
    return ""


vpath = os.path.join(name, "__init__.py")
if os.path.isfile(vpath):
    kwargs["packages"] = find_packages()
else:
    vpath = "{}.py".format(name)
    kwargs["py_modules"] = [name]
version = re.search(r"^__version__\s*=\s*[\'\"]([^\'\"]+)", read(vpath), flags=re.I | re.M).group(1)


# https://pypi.org/help/#description-content-type
kwargs["long_description"] = read('README.md')
kwargs["long_description_content_type"] = "text/markdown"


setup(
    version=version,
    description='Get an api up and running quickly',
    keywords="wsgi wsgi-server api api-server server framework web-framework REST rest-api",
    author='Jay Marcyes',
    author_email='jay@marcyes.com',
    url='http://github.com/firstopinion/{}'.format(name),
    license="MIT",
    install_requires=['decorators', 'datatypes'],
    tests_require=['testdata', 'requests'],
    extras_require={
        'websockets': ["websocket-client", "gevent"],
        'tornado': ["tornado"],
        'html': ['jinja2'],
    },
    classifiers=[ # https://pypi.python.org/pypi?:action=list_classifiers
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
    entry_points = {
        'console_scripts': [
            '{} = {}.__main__:console'.format(name, name),
        ],
    },
    **kwargs
)
