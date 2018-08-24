# -*- coding: utf-8 -*-
"""
Handy utilities that are sometimes needed
"""
from __future__ import unicode_literals, division, print_function, absolute_import

from .version import is_py2, is_py3

if is_py2:
    # shamelously ripped from six https://bitbucket.org/gutworth/six
    exec("""def reraise(tp, value, tb=None):
        try:
            raise tp, value, tb
        finally:
            tb = None
    """)


# TODO -- create an object that makes all the magic method compatible switches, so __str__ and the others

elif is_py3:
    # ripped from six https://bitbucket.org/gutworth/six
    def reraise(tp, value, tb=None):
        try:
            if value is None:
                value = tp()
            if value.__traceback__ is not tb:
                raise value.with_traceback(tb)
            raise value
        finally:
            value = None
            tb = None


# TODO using reraise

#             if py_2:
#                 #raise error_info[0].__class__, error_info[0], error_info[1][2]
#                 reraise(*error_info)
#                 #raise error_info[0].__class__, error_info[1], error_info[2]
# 
#             elif py_3:
#                 #e, exc_info = error_info
#                 #et, ei, tb = exc_info
# 
#                 reraise(*error_info)
#                 #et, ei, tb = error_info
#                 #raise ei.with_traceback(tb)


# if not error_info:
#                     exc_info = sys.exc_info()
#                     #raise e.__class__, e, exc_info[2]
#                     #self.error_info = (e, exc_info)
#                     self.error_info = exc_info
# 
# if error_info:
# 
#             reraise(*error_info)
