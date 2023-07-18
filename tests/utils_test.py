# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import json

from endpoints.compat import *
from endpoints.utils import (
    MimeType,
    AcceptHeader,
    JSONEncoder,
    Url,
)

from . import TestCase, testdata


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


class UrlTest(TestCase):
    def test_module(self):
        c = self.create_server({
            "foo": [
                "from endpoints import Controller",
                "class Bar(Controller):",
                "    def GET(self):",
                "        u = self.request.url",
                "        return u.module()",
                "",
                "class Default(Controller):",
                "    def GET(self):",
                "        u = self.request.url",
                "        return u.module()",
                "",
            ],
        })

        res = c.handle("/foo/bar")
        self.assertEqual("http://endpoints.fake/foo", res._body)

        res = c.handle("/foo")
        self.assertEqual("http://endpoints.fake/foo", res._body)

    def test_controller(self):
        u = Url("http://example.com/foo/bar/che", class_path="foo")
        u2 = u.controller(che=4)
        self.assertEqual("http://example.com/foo?che=4", u2)

