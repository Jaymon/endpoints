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
from io import IOBase


from .compat.environ import *
from . import environ


class ByteString(Bytes):
    """Wrapper around a byte string b"" to make sure we have a byte string that
    will work across python versions and handle the most annoying encoding issues
    automatically

    :Example:
        # python 3
        s = ByteString("foo)
        str(s) # calls __str__ and returns self.unicode()
        unicode(s) # errors out
        bytes(s) # calls __bytes__ and returns ByteString

        # python 2
        s = ByteString("foo)
        str(s) # calls __str__ and returns ByteString
        unicode(s) # calls __unicode__ and returns String
        bytes(s) # calls __str__ and returns ByteString
    """
    def __new__(cls, val=b"", encoding=""):
        if isinstance(val, type(None)): return None

        if not encoding:
            encoding = environ.ENCODING

        if not isinstance(val, (bytes, bytearray)):
            if is_py2:
                val = unicode(val)
            else:
                val = str(val)
            #val = val.__str__()
            val = bytearray(val, encoding)

        instance = super(ByteString, cls).__new__(cls, val)
        instance.encoding = encoding
        return instance

    def __str__(self):
        return self if is_py2 else self.unicode()

    def unicode(self):
        s = self.decode(self.encoding)
        return String(s)
    __unicode__ = unicode

    def bytes(self):
        return self
    __bytes__ = bytes

    def raw(self):
        """because sometimes you need a vanilla bytes()"""
        return b"" + self


class String(Str):
    """Wrapper around a unicode string "" to make sure we have a unicode string that
    will work across python versions and handle the most annoying encoding issues
    automatically

    :Example:
        # python 3
        s = String("foo)
        str(s) # calls __str__ and returns String
        unicode(s) # errors out
        bytes(s) # calls __bytes__ and returns ByteString

        # python 2
        s = String("foo)
        str(s) # calls __str__ and returns ByteString
        unicode(s) # calls __unicode__ and returns String
        bytes(s) # calls __str__ and returns ByteString
    """
    def __new__(cls, val="", encoding=""):
        if isinstance(val, type(None)): return None

        if not encoding:
            encoding = environ.ENCODING

        if not isinstance(val, Str):
            val = ByteString(val, encoding).unicode()

        instance = super(String, cls).__new__(cls, val)
        instance.encoding = encoding
        return instance

    def __str__(self):
        return self.bytes() if is_py2 else self

    def unicode(self):
        return self
    __unicode__ = unicode

    def bytes(self):
        s = self.encode(self.encoding)
        return ByteString(s)
    __bytes__ = bytes

    def raw(self):
        """because sometimes you need a vanilla str() (or unicode() in py2)"""
        return "" + self


class Base64(String):
    """This exists to normalize base64 encoding between py2 and py3, it assures that
    you always get back a unicode string when you encode or decode and that you can
    pass in a unicode or byte string and it just works
    """
    @classmethod
    def encode(cls, s):
        """converts a plain text string to base64 encoding

        :param s: unicode str|bytes, the base64 encoded string
        :returns: unicode str
        """
        b = ByteString(s)
        be = base64.b64encode(b).strip()
        return String(be)

    @classmethod
    def decode(cls, s):
        """decodes a base64 string to plain text

        :param s: unicode str|bytes, the base64 encoded string
        :returns: unicode str
        """
        b = ByteString(s)
        bd = base64.b64decode(b)
        return String(bd)


class Path(String):
    def __new__(cls, s):
        s = os.path.abspath(os.path.expanduser(str(s)))
        return super(Path, cls).__new__(cls, s)


class MimeType(object):
    """This is just a thin wrapper around Python's built-in MIME Type stuff

    https://docs.python.org/2/library/mimetypes.html
    """

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


class Deepcopy(object):
    """deep copy an object trying to anticipate and handle any errors"""
    @classmethod
    def copy(cls, val, memodict=None, shell_instance=None):
        ret = val
        if not memodict:
            memodict = {}

        if isinstance(val, Mapping):
            ret = shell_instance if shell_instance else type(val)()
            for k, v in val.items():
                ret[k] = cls.copy(v, memodict)

        elif isinstance(val, IOBase):
            # file/stream objects should just be passed through
            pass

        elif hasattr(val, "__dict__"):
            if shell_instance:
                ret = shell_instance
                for k, v in val.__dict__.items():
                    if not k.startswith("_"):
                        if v is None:
                            setattr(ret, k, v)

                        else:
                            if k in memodict and v is memodict[k]:
                                continue

                            else:
                                setattr(ret, k, cls.copy(v, memodict))

            else:
                ret = cls._copy(val, memodict)

        else:
            ret = cls._copy(val, memodict)

        return ret

    @classmethod
    def _copy(cls, val, memodict):
        ret = val
        try:
            ret = copy.deepcopy(val, memodict)

        except (AttributeError, TypeError):
            try:
                ret = copy.copy(val)

            except TypeError:
                pass

        return ret

