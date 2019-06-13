# -*- coding: utf-8 -*-
"""
This module normalizes imports to python 3 standards, so when py2 is different it
will be changed to python3 syntax to make it equivalent accross versions
"""
from __future__ import unicode_literals, division, print_function, absolute_import

from .version import is_py2, is_py3


if is_py2:
    import __builtin__ as builtins
    from BaseHTTPServer import BaseHTTPRequestHandler
    import urlparse as parse

    try:
        from cstringio import StringIO
    except ImportError:
        from StringIO import StringIO

    from urllib import urlencode
    import SocketServer as socketserver
    #from base64 import encodestring as encodebytes

#     import Queue as queue
#     import thread as _thread
#     try:
#         from cStringIO import StringIO
#     except ImportError:
#         from StringIO import StringIO
# 
#         from SimpleHTTPServer import SimpleHTTPRequestHandler
#     from BaseHTTPServer import HTTPServer
#     from Cookie import SimpleCookie
#     import urlparse
#     from urllib import urlencode
#     from urllib2 import Request, urlopen, URLError, HTTPError


elif is_py3:
    import builtins
    from http.server import BaseHTTPRequestHandler
    from urllib import parse
    from io import StringIO
    from urllib.parse import urlencode
    import socketserver
    #from base64 import encodebytes


#     import queue
#     import _thread
#     from io import StringIO
#     from http.server import HTTPServer, SimpleHTTPRequestHandler
#     #from http import cookies
#     from http.cookies import SimpleCookie
#     from urllib import parse as urlparse
#     from urllib.request import Request, urlopen
#     from urllib.error import URLError, HTTPError
#     from urllib.parse import urlencode

