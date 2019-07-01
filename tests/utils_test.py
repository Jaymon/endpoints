# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from unittest import TestCase
import json

import testdata

from endpoints.utils import MimeType, AcceptHeader, String, ByteString, Base64, JSONEncoder
from endpoints.compat.environ import *


# class HostTest(TestCase):
#     def test_port(self):
#         h = Host("localhost:8080")
#         self.assertEqual(8080, h.port)
# 
#         h = Host("localhost")
#         self.assertEqual(0, h.port)
# 
#         h = Host("localhost:")
#         self.assertEqual(0, h.port)


class Base64Test(TestCase):
    def test_encode_decode(self):
        s = testdata.get_words()

        b = Base64.encode(s)
        self.assertTrue(isinstance(b, unicode))
        self.assertNotEqual(b, s)

        s2 = Base64.decode(b)
        self.assertTrue(isinstance(s2, unicode))
        self.assertNotEqual(b, s2)
        self.assertEqual(s, s2)


class StringTest(TestCase):
    def test_string(self):
        s = String(1)
        self.assertEqual("1", s)

        s = String(b"foo")
        self.assertEqual("foo", s)

        s = String({"foo": 1})
        self.assertEqual("{u'foo': 1}" if is_py2 else "{'foo': 1}", s)

        s = String((1, 2))
        self.assertEqual("(1, 2)", s)

        s = String([1, 2])
        self.assertEqual("[1, 2]", s)

        s = String(True)
        self.assertEqual("True", s)

        s = String(None)
        self.assertEqual(None, s)

        s = String("foo")
        self.assertEqual("foo", s)

        su = testdata.get_unicode()
        s = String(su)
        sb = bytes(s)
        s2 = String(sb)
        self.assertEqual(s, s2)

    def test_bytestring(self):
        s = ByteString(1)
        self.assertEqual(b"1", s)

        s = ByteString("foo")
        self.assertEqual(b"foo", s)

        s = ByteString(True)
        self.assertEqual(b"True", s)

        s = ByteString(None)
        self.assertEqual(None, s)

        su = testdata.get_unicode()
        s = ByteString(su)
        self.assertEqual(su, s.unicode())






class MimeTypeTest(TestCase):
    def test_default_file(self):
        test_mt = "image/jpeg"

        mt = MimeType.find_type("some/path/file.jpg")
        self.assertEqual(test_mt, mt)

        mt = MimeType.find_type("jpg")
        self.assertEqual(test_mt, mt)

        mt = MimeType.find_type("JPG")
        self.assertEqual(test_mt, mt)

        mt = MimeType.find_type(".JPG")
        self.assertEqual(test_mt, mt)

        mt = MimeType.find_type(".jpg")
        self.assertEqual(test_mt, mt)


class AcceptHeaderTest(TestCase):

    def test_init(self):
        ts = [
            (
                "text/*, text/html, text/html;level=1, */*",
                [
                    "text/html;level=1",
                    "text/html",
                    "text/*",
                    "*/*"
                ]
            ),
            (
                'text/*;q=0.3, text/html;q=0.7, text/html;level=1, text/html;level=2;q=0.4, */*;q=0.5',
                [
                    "text/html;level=1",
                    "text/html;q=0.7",
                    "*/*;q=0.5",
                    "text/html;level=2;q=0.4",
                    "text/*;q=0.3",
                ]
            ),
        ]

        for t in ts:
            a = AcceptHeader(t[0])
            for i, x in enumerate(a):
                self.assertEqual(x[3], t[1][i])

    def test_filter(self):
        ts = [
            (
                "*/*;version=v5", # accept header that is parsed
                ("application/json", {}), # filter args, kwargs
                1 # how many matches are expected
            ),
            (
                "*/*;version=v5",
                ("application/json", {'version': 'v5'}),
                1
            ),
            (
                "application/json",
                ("application/json", {}),
                1
            ),
            (
                "application/json",
                ("application/*", {}),
                1
            ),
            (
                "application/json",
                ("text/html", {}),
                0
            ),
            (
                "application/json;version=v1",
                ("application/json", {"version": "v1"}),
                1
            ),
            (
                "application/json;version=v2",
                ("application/json", {"version": "v1"}),
                0
            ),

        ]

        for t in ts:
            a = AcceptHeader(t[0])
            count = 0
            for x in a.filter(t[1][0], **t[1][1]):
                count += 1

            self.assertEqual(t[2], count)


class JSONEncoderTest(TestCase):
    def test_string(self):
        r1 = json.dumps({'foo': b'bar'}, cls=JSONEncoder)
        r2 = json.dumps({'foo': 'bar'}, cls=JSONEncoder)
        self.assertEqual(r1, r2)

