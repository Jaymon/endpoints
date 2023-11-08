# -*- coding: utf-8 -*-

from endpoints.compat import *
from .. import TestCase, testdata


class TemplateTest(TestCase):
    def test_template(self):
        p = testdata.create_file([
            '<h1>Hello {{ name }}</h1>',
        ], ext="html")

        c = self.create_server([
            "from endpoints import Controller",
            "from endpoints.extras.templates import template",
            "class Default(Controller):",
            "    @template('{}', directories=['{}'])".format(
                p.basename,
                p.parent
            ),
            "    def GET(self):",
            "        return {'name': 'foo bar'}"
        ])
        res = c.handle('/')
        self.assertTrue("Hello foo bar" in res.body)

