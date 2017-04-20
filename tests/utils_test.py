# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from unittest import TestCase

import testdata

from endpoints.utils import MimeType, AcceptHeader


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


