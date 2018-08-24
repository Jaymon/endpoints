# -*- coding: utf-8 -*-
"""
This is to normalize the environment between 2 and 3, it should almost always be 
included with:

    from .compat import *

That's because it modifies builtins and primitives like range and str to work
"""
from __future__ import unicode_literals, division, print_function, absolute_import

from .version import is_py2, is_py3


if is_py2:
    basestring = basestring
    range = xrange # range is now always an iterator
    unicode = unicode
    cmp = cmp


elif is_py3:
    basestring = (str, bytes)
    unicode = str

    # py3 has no cmp function for some strange reason
    # https://codegolf.stackexchange.com/a/49779
    def cmp(a, b):
        return (a > b) - (a < b)


Str = unicode if is_py2 else str
Bytes = str if is_py2 else bytes

