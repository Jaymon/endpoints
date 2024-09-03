# -*- coding: utf-8 -*-

from endpoints.compat import *
from endpoints.reflection import (
    OpenAPI
)

from . import TestCase


class OpenAPITest(TestCase):
    def test_parameter_positional_named(self):
        c = self.create_server("""
            class Foo(Controller):
                cors = False

                @param(0)
                def GET(self, zero, *args, **kwargs):
                    pass
        """)

        oa = OpenAPI(c.application)
        self.assertTrue("/foo/{zero}" in oa.paths)

    def test_parameter_query(self):
        c = self.create_server("""
            class Foo(Controller):
                cors = False

                @param("zero")
                def GET(self, zero, *args, **kwargs):
                    pass
        """)

        oa = OpenAPI(c.application)
        self.assertEqual("query", oa.paths["/foo"]["get"].parameters[0]["in"])
        self.assertEqual(1, len(oa.paths["/foo"]["get"].parameters))

    def test_parameter_body(self):
        c = self.create_server("""
            class Foo(Controller):
                cors = False

                @param("bar", type=int, help="the bar variable")
                @param("che", type=str, help="the che variable")
                def GET(self, **kwargs):
                    pass
        """)

        oa = OpenAPI(c.application)
        self.assertEqual("query", oa.paths["/foo"]["get"].parameters[0]["in"])
        self.assertEqual(1, len(oa.paths["/foo"]["get"].parameters))


    def test_paths(self):
        c = self.create_server(
            {
                "": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ],
                "boo": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ],
                "foo": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "class Bar(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "    def POST(*args, **kwargs): pass",
                    ""
                ],
                "foo.baz": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "class Che(Controller):",
                    "    def ANY(*args, **kwargs): pass",
                    ""
                ],
            },
        )

        oa = OpenAPI(c.application)

