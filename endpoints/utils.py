# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import mimetypes
import sys
import base64
import json
import types
import copy
from collections import Mapping
from io import IOBase, FileIO

from datatypes import (
    ByteString,
    String,
    Base64,
    Path,
    Deepcopy,
)

from .compat import *
from . import environ


class FileWrapper(FileIO):
    """Wraps a file descriptor.

    Honestly, this exists because Python2 won't allow you to add properties to a
    descriptor (because it doesn't extend object), this is currently used for any
    uploaded files"""
    def __init__(self, fp, name=None, **kwargs):
        self.fp = fp
        self.name = name

        for k, v in kwargs.items():
            setattr(self, k, v)

    def close(self, *args, **kwargs):
        return self.fp.close(*args, **kwargs)

    def seekable(self):
        return self.fp.seekable()

    def seek(self, *args, **kwargs):
        return self.fp.seek(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.fp.read(*args, **kwargs)

    def readall(self):
        return self.fp.readall()

    def tell(self, *args, **kwargs):
        return self.fp.tell(*args, **kwargs)

    def readline(self, *args, **kwargs):
        return self.fp.readline(*args, **kwargs)

    def readlines(self, *args, **kwargs):
        return self.fp.readlines(*args, **kwargs)

    def __iter__(self):
        for line in self.fp:
            yield line

    def writable(self):
        return False


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

        if value is a path, then the extension will be found, if val is an extension then
        that will be used to find the mimetype
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
        sort the headers according to rfc 2616 so when __iter__ is called, the accept media types are
        in order from most preferred to least preferred
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
        if is_py2:
            sorted_media_types = sorted(self.media_types, self._sort, reverse=True)
        else:
            from functools import cmp_to_key
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
            return json.JSONEncoder.default(self, obj)

