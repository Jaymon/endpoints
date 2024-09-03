# -*- coding: utf-8 -*-
import mimetypes
import json
import types
from functools import cmp_to_key


from datatypes import (
    ByteString,
    String,
    Base64,
    Path,
    Deepcopy,
    Url as BaseUrl,
)

from .compat import *
from .config import environ


class Url(BaseUrl):
    """a url object on steroids, this is here to make it easy to manipulate
    urls we try to map the supported fields to their urlparse equivalents,
    with some additions

    https://tools.ietf.org/html/rfc3986.html

    given a url http://user:pass@foo.com:1000/bar/che?baz=boom#anchor
    with a controller: Bar

    .scheme = http
    .netloc = user:pass@foo.com:1000
    .hostloc = foo.com:1000
    .hostname = foo.com
    .host() = http://foo.com
    .port = 1000
    .base = http://user:pass@foo.com:1000/bar/che
    .fragment = anchor
    .anchor = fragment
    .uri = /bar/che?baz=boom#anchor
    .host(...) = http://foo.com/...
    .base(...) = http://foo.com/bar/che/...
    .controller(...) = http://foo.com/bar/...
    """
    controller_class_path = ""
    """Holds the path to the controller (eg, if the controller was in module
    `foo.bar` and named `Che` then this would be `/foo/bar/che`

    see Request.url
    """

    controller_module_path = ""
    """Holds the path to controller's module (eg, if the controller was defined
    in `controllers.foo.bar` and the controller_prefix was `controllers` then
    this would be `/foo/bar`

    see Request.url
    """

    @classmethod
    def default_values(cls):
        values = super().default_values()

        # we set these here instead of as class variables because we could
        # update environ at some point after this class has been loaded into
        # memory
        values["scheme"] = environ.SCHEME
        values["hostname"] = environ.HOST

        return values

    def module(self, *paths, **query_kwargs):
        """create a new Url instance using the module path as a base

        :param *paths: list, the paths to append to the module path
        :param **query_kwargs: dict, any query string params to add
        :returns: Url, a new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)

        if self.controller_module_path:
            if "path" in kwargs:
                paths = self.normalize_paths(
                    self.controller_module_path,
                    kwargs["path"]
                )
                kwargs["path"] = "/".join(paths)

            else:
                kwargs["path"] = self.controller_module_path

        return self.create(self.root, **kwargs)

    def controller(self, *paths, **query_kwargs):
        """create a new url object using the controller path as a base

        if you have a controller `foo.BarController` then this would create a
        new Url instance with `host/foo/bar` as the base path, so any *paths
        will be appended to `/foo/bar`

        :example:
            # controller is: foo.Bar

            print(url) # http://host.com/foo/bar/some_random_path

            print(url.controller()) # http://host.com/foo/bar

            # http://host/foo/bar/che?boom=bam
            print(url.controller("che", boom="bam"))

        :param *paths: list, the paths to append to the controller path
        :param **query_kwargs: dict, any query string params to add
        :returns: Url, a new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)

        if self.controller_class_path:
            if "path" in kwargs:
                paths = self.normalize_paths(
                    self.controller_class_path,
                    kwargs["path"]
                )
                kwargs["path"] = "/".join(paths)

            else:
                kwargs["path"] = self.controller_class_path

        return self.create(self.root, **kwargs)


class MimeType(object):
    """This is just a thin wrapper around Python's built-in MIME Type stuff

    https://docs.python.org/2/library/mimetypes.html
    """
    @classmethod
    def find(cls, val):
        return cls.find_type(val)

    @classmethod
    def find_type(cls, val):
        """return the mimetype from the given string value

        if value is a path, then the extension will be found, if val is an
        extension then that will be used to find the mimetype
        """
        mt = ""
        index = val.rfind(".")
        if index == -1:
            val = "fake.{}".format(val)
        elif index == 0:
            val = "fake{}".format(val)

        mt = mimetypes.guess_type(val)[0]
        if mt is None:
            mt = ""

        return mt


class AcceptHeader(object):
    """
    wraps the Accept header to allow easier versioning

    provides methods to return the accept media types in the correct order
    """
    def __init__(self, header):
        self.header = header
        self.media_types = []

        if header:
            accepts = header.split(',')
            for accept in accepts:
                accept = accept.strip()
                a = accept.split(';')

                # first item is the media type:
                media_type = self._split_media_type(a[0])

                # all other items should be in key=val so let's add them to a dict:
                params = {}
                q = 1.0 # default according to spec
                for p in a[1:]:
                    pk, pv = p.strip().split('=')
                    if pk == 'q':
                        q = float(pv)
                    else:
                        params[pk] = pv

                #pout.v(media_type, q, params)
                self.media_types.append((media_type, q, params, accept))

    def _split_media_type(self, media_type):
        """return type, subtype from media type: type/subtype"""
        media_type_bits = media_type.split('/')
        return media_type_bits

    def _sort(self, a, b):
        '''
        sort the headers according to rfc 2616 so when __iter__ is called, the
        accept media types are in order from most preferred to least preferred
        '''
        ret = 0

        # first we check q, higher values win:
        if a[1] != b[1]:
            ret = cmp(a[1], b[1])
        else:
            found = False
            for i in range(2):
                ai = a[0][i]
                bi = b[0][i]
                if ai == '*':
                    if bi != '*':
                        ret = -1
                        found = True
                        break
                    else:
                        # both *, more verbose params win
                        ret = cmp(len(a[2]), len(b[2]))
                        found = True
                        break
                elif bi == '*':
                    ret = 1
                    found = True
                    break

            if not found:
                ret = cmp(len(a[2]), len(b[2]))

        return ret

    def __iter__(self):
        sorted_media_types = sorted(
            self.media_types,
            key=cmp_to_key(self._sort),
            reverse=True
        )
        for x in sorted_media_types:
            yield x

    def filter(self, media_type, **params):
        """
        iterate all the accept media types that match media_type

        media_type -- string -- the media type to filter by
        **params -- dict -- further filter by key: val

        return -- generator -- yields all matching media type info things
        """
        mtype, msubtype = self._split_media_type(media_type)
        for x in self.__iter__():
            # all the params have to match to make the media type valid
            matched = True
            for k, v in params.items():
                if x[2].get(k, None) != v:
                    matched = False
                    break

            if matched:
                if x[0][0] == '*':
                    if x[0][1] == '*':
                        yield x

                    elif x[0][1] == msubtype:
                        yield x

                elif mtype == '*':
                    if msubtype == '*':
                        yield x

                    elif x[0][1] == msubtype:
                        yield x

                elif x[0][0] == mtype:
                    if msubtype == '*':
                        yield x

                    elif x[0][1] == '*':
                        yield x

                    elif x[0][1] == msubtype:
                        yield x


class JSONEncoder(json.JSONEncoder):
    """Smooths out some rough edges with the default encoder"""
    def default(self, obj):
        if isinstance(obj, types.GeneratorType):
            return [x for x in obj]

        elif isinstance(obj, Exception):
            return {
                "errmsg": String(obj)
            }

        elif isinstance(obj, bytes):
            # this seems like a py3 bug, for some reason bytes can get in here
            # https://bugs.python.org/issue30343
            # https://stackoverflow.com/questions/43913256/understanding-subclassing-of-jsonencoder
            return String(obj)

        else:
            #return json.JSONEncoder.default(self, obj)
            return super().default(obj)


class Status(String):
    def __new__(cls, code, **kwargs):
        if code < 1000:
            status = cls.get_http_status(code)

        else:
            status = cls.get_websocket_status(code)

        if not status:
            status = "UNKNOWN"

        instance = super().__new__(cls, status)
        instance.code = code
        return instance

    @classmethod
    def get_http_status(cls, code, **kwargs):
        status = ""
        status_tuple = BaseHTTPRequestHandler.responses.get(code)
        if status_tuple:
            status = status_tuple[0]

        return status

    @classmethod
    def get_websocket_status(cls, code, **kwargs):
        """Get the websocket status code

        https://github.com/Luka967/websocket-close-codes
        """
        status = ""

        codes = {
            # Successful operation / regular socket shutdown
            1000: "Close Normal",

            # Client is leaving (browser tab closing)
            1001: "Close Going Away",

            # Endpoint received a malformed frame
            1002: "Close Protocol Error",

            # Endpoint received an unsupported frame (e.g. binary-only endpoint
            # received text frame)
            1003: "Close Unsupported",

            1004: "Reserved",

            # Expected close status, received none
            1005: "Closed No Status",

            # No close code frame has been receieved
            1006: "Close Abnormal",

            # Endpoint received inconsistent message (e.g. malformed UTF-8)
            1007: "Unsupported Payload",

            # Generic code used for situations other than 1003 and 1009
            1008: "Policy Violation",

            # Endpoint won't process large frame
            1009: "Close Too Large",

            # Client wanted an extension which server did not negotiate
            1010: "Mandatory Extension",

            # Internal server error while operating
            1011: "Server Error",

            # Server/service is restarting
            1012: "Service Restart",

            # Temporary server condition forced blocking client's request
            1013: "Try Again Later",

            # Server acting as gateway received an invalid response
            1014: "Bad Gateway",

            # Transport Layer Security handshake failure
            1015: "TLS Handshake Fail",
        }

        if code in codes:
            status = codes[code]

        elif code >= 1016 and code <= 1999:
            status = "Reserved For Later"

        elif code >= 2000 and code <= 2999:
            status = "Reserved For WebSocket Extensions"

        elif code >= 3000 and code <= 3999:
            status = "Registered First Come First Serve at IANA"

        elif code >= 4000 and code <= 4999:
            status = "Available For Applications"

        return status

