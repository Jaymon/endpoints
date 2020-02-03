# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from endpoints.client import WebClient, WebsocketClient
from . import TestCase


class WebClientTestCase(TestCase):
    """Tests the HTTP webclient, this class has no server so it can only test the 
    building block methods, I actual requesting of the client is tested in the interface"""
    client_class = WebClient

    def create_client(self, **kwargs):
        kwargs.setdefault("host", "endpoints.fake")
        client = self.client_class(**kwargs)
        return client

    def test_get_fetch_url(self):
        c = self.create_client()

        uri = "http://foo.com"
        url = c.get_fetch_url(uri)
        self.assertEqual(uri, url)

        uri = "/foo/bar"
        url = c.get_fetch_url(uri)
        self.assertEqual("{}{}".format(c.get_fetch_host(), uri), url)

        url = c.get_fetch_url(["foo", "bar"])
        self.assertEqual("{}{}".format(c.get_fetch_host(), "/foo/bar"), url)

    def test_basic_auth(self):
        c = self.create_client()
        c.basic_auth("foo", "bar")
        self.assertRegex(c.headers["authorization"], r"Basic\s+[a-zA-Z0-9=]+")


class WebsocketClientTestCase(WebClientTestCase):
    client_class = WebsocketClient

    def test_get_fetch_request(self):
        c = self.create_client()
        c.query = {
            "bar": 2
        }

        p = c.get_fetch_request("GET", "/foo", {"foo": 1})
        self.assertTrue('"foo": 1' in p)
        self.assertTrue('"bar": 2' in p)

