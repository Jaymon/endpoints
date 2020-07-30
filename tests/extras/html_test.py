# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from endpoints.compat import *
from .. import TestCase, testdata, Server


class DecoratorsTest(TestCase):
    def test_html(self):

        p = testdata.create_file("foo.html", contents=[
            '<h1>Hello {{ name }}</h1>',
        ])

        c = Server(contents=[
            "from endpoints import Controller",
            "from endpoints.extras.html.decorators import view",
            "class Default(Controller):",
            "    @view('{}', directories=['{}'])".format(p.fileroot, p.parent),
            "    def GET(self):",
            "        return {'name': 'foo bar'}"
        ])
        res = c.handle('/')
        self.assertTrue("Hello foo bar" in res._body)

