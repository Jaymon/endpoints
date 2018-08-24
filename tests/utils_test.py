# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from unittest import TestCase

import testdata

from endpoints.utils import MimeType, AcceptHeader, String, ByteString, Base64
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
#     def test_convert(self):
#         s = ByteString("foo")
#         pout.b()
#         pout.v(s)
#         pout.b()
#         pout.v(str(s))
#         pout.b()
#         pout.v(unicode(s))
#         pout.b()
#         pout.v(bytes(s))
#         pout.b()
#         pout.v(s.bytes())

    def test_formatting(self):
        sb = ByteString("foo")
        sb = b"" + sb
        s = "foo={}".format(sb)
        pout.v(s)

    def test_base64(self):
        username = "bar"
        password = "..."
        username = testdata.get_unicode()
        password = testdata.get_unicode()
        import base64
        be = base64.b64encode(ByteString('{}:{}'.format(username, password))).strip()
        pout.v(be)

        bd = base64.b64decode(be)
        pout.v(bd, String(bd))


    def test_bom(self):
        b = b'm\x99\xbd\xbc\xe8\xb8\xb8\xb8'
        #s = String(b)

        encodings = ['ascii',
            'big5',
            'big5hkscs',
            'cp037',
            'cp273',
            'cp424',
            'cp437',
            'cp500',
            'cp720',
            'cp737',
            'cp775',
            'cp850',
            'cp852',
            'cp855',
            'cp856',
            'cp857',
            'cp858',
            'cp860',
            'cp861',
            'cp862',
            'cp863',
            'cp864',
            'cp865',
            'cp866',
            'cp869',
            'cp874',
            'cp875',
            'cp932',
            'cp949',
            'cp950',
            'cp1006',
            'cp1026',
            'cp1125',
            'cp1140',
            'cp1250',
            'cp1251',
            'cp1252',
            'cp1253',
            'cp1254',
            'cp1255',
            'cp1256',
            'cp1257',
            'cp1258',
            'cp65001',
            'euc_jp',
            'euc_jis_2004',
            'euc_jisx0213',
            'euc_kr',
            'gb2312',
            'gbk',
            'gb18030',
            'hz',
            'iso2022_jp',
            'iso2022_jp_1',
            'iso2022_jp_2',
            'iso2022_jp_2004',
            'iso2022_jp_3',
            'iso2022_jp_ext',
            'iso2022_kr',
            'latin_1',
            'iso8859_2',
            'iso8859_3',
            'iso8859_4',
            'iso8859_5',
            'iso8859_6',
            'iso8859_7',
            'iso8859_8',
            'iso8859_9',
            'iso8859_10',
            'iso8859_11',
            'iso8859_13',
            'iso8859_14',
            'iso8859_15',
            'iso8859_16',
            'johab',
            'koi8_r',
            'koi8_t',
            'koi8_u',
            'kz1048',
            'mac_cyrillic',
            'mac_greek',
            'mac_iceland',
            'mac_latin2',
            'mac_roman',
            'mac_turkish',
            'ptcp154',
            'shift_jis',
            'shift_jis_2004',
            'shift_jisx0213',
            'utf_32',
            'utf_32_be',
            'utf_32_le',
            'utf_16',
            'utf_16_be',
            'utf_16_le',
            'utf_7',
            'utf_8',
            'utf_8_sig']

        for encoding in encodings:
            try:
                s = String(b, encoding)
                print("{} worked: {}".format(encoding, s))
            except (UnicodeError, LookupError): pass

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


