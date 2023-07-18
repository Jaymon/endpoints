# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import mimetypes
import sys
import base64
import json
import types
import copy
from io import IOBase, FileIO
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
from . import environ


class Url(BaseUrl):
    """a url object on steroids, this is here to make it easy to manipulate urls
    we try to map the supported fields to their urlparse equivalents, with some
    additions

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
    class_path = ""

    module_path = ""

    def module(self, *paths, **query_kwargs):
        """create a new Url instance using the module path as a base

        :param *paths: list, the paths to append to the module path
        :param **query_kwargs: dict, any query string params to add
        :returns: new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)
        if self.module_path:
            if "path" in kwargs:
                paths = self.normalize_paths(self.module_path, kwargs["path"])
                kwargs["path"] = "/".join(paths)
            else:
                kwargs["path"] = self.module_path
        return self.create(self.root, **kwargs)

    def controller(self, *paths, **query_kwargs):
        """create a new url object using the controller path as a base

        if you have a controller `foo.BarController` then this would create a new
        Url instance with `host/foo/bar` as the base path, so any *paths will be
        appended to `/foo/bar`

        :example:
            # controller foo.Bar(Controller)

            print url # http://host.com/foo/bar/some_random_path

            print url.controller() # http://host.com/foo/bar
            print url.controller("che", boom="bam") # http://host/foo/bar/che?boom=bam

        :param *paths: list, the paths to append to the controller path
        :param **query_kwargs: dict, any query string params to add
        :returns: new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)
        if self.class_path:
            if "path" in kwargs:
                paths = self.normalize_paths(self.class_path, kwargs["path"])
                kwargs["path"] = "/".join(paths)
            else:
                kwargs["path"] = self.class_path
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

