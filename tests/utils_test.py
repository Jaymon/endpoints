# -*- coding: utf-8 -*-
import json

from endpoints.compat import *
from endpoints.utils import (
    MimeType,
    AcceptHeader,
    JSONEncoder,
    Url,
    Status,
)

from . import TestCase


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
                ", ".join([
                    "text/*;q=0.3",
                    "text/html;q=0.7",
                    "text/html;level=1",
                    "text/html;level=2;q=0.4",
                    "*/*;q=0.5",
                ]),
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

    def test_parsing_error(self):
        s = "\"===============1234==\""
        ct = f"multipart/form-data;  boundary={s}"
        ah = AcceptHeader(ct)
        self.assertEqual(s, ah.media_types[0][2]["boundary"])


class JSONEncoderTest(TestCase):
    def test_string(self):
        r1 = json.dumps({'foo': b'bar'}, cls=JSONEncoder)
        r2 = json.dumps({'foo': 'bar'}, cls=JSONEncoder)
        self.assertEqual(r1, r2)


class UrlTest(TestCase):
    def test_module_and_controller(self):
        c = self.create_server({
            "foomod": [
                "class Bar(Controller):",
                "    def GET(self, *args):",
                "        u = self.request.url",
                "        return u.module()",
                "",
                "class Default(Controller):",
                "    def GET(self, *args):",
                "        u = self.request.url",
                "        return u.module()",
                "",
            ],
            "fooclass": [
                "class Bar(Controller):",
                "    def GET(self, *args):",
                "        u = self.request.url",
                "        return u.controller()",
                "",
                "class Default(Controller):",
                "    def GET(self, *args):",
                "        u = self.request.url",
                "        return u.controller()",
                "",
            ],
        })

        res = c.handle("/foomod/bar")
        self.assertEqual("http://endpoints.fake/foomod", res._body)

        res = c.handle("/foomod")
        self.assertEqual("http://endpoints.fake/foomod", res._body)

        res = c.handle("/fooclass/bar")
        self.assertEqual("http://endpoints.fake/fooclass/bar", res._body)

        res = c.handle("/fooclass")
        self.assertEqual("http://endpoints.fake/fooclass", res._body)

    def test_controller(self):
        u = Url("http://example.com/foo/bar/che", controller_class_path="foo")
        u2 = u.controller(che=4)
        self.assertEqual("http://example.com/foo?che=4", u2)

    def test_default_scheme_host(self):
        kwargs = dict(
            ENDPOINTS_HOST="localhost:12345",
            ENDPOINTS_SCHEME="http",
        )

        with self.environ(**kwargs):
            url = Url("/foo/bar")
            self.assertEqual("http://localhost:12345/foo/bar", url)


class StatusTest(TestCase):
    def test_codes(self):
        s = Status(401)
        self.assertEqual("Unauthorized", s)

        s = Status(1001)
        self.assertEqual("Close Going Away", s)

