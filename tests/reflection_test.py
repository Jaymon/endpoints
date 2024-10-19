# -*- coding: utf-8 -*-

from endpoints.compat import *
from endpoints.reflection import (
    OpenAPI,
    Field,
    Schema,
    ReflectController,
    ReflectType,
)

from . import TestCase


class TestCase(TestCase):
    def create_openapi(self, *args, **kwargs):
        server = self.create_server(*args, **kwargs)
        return OpenAPI(server.application)

    def create_reflect_controllers(self, *args, **kwargs):
        rcs = []
        server = self.create_server(*args, **kwargs)
        pf = server.application.router.pathfinder
        for keys, value in pf.get_class_items():
            rcs.append(ReflectController(keys, value))
        return rcs

    def create_reflect_methods(self, *args, **kwargs):
        rms = []
        rcs = self.create_reflect_controllers(*args, **kwargs)
        for rc in rcs:
            rms.extend(rc.reflect_http_methods())
        return rms

    def create_reflect_params(self, *args, **kwargs):
        rps = []
        rms = self.create_reflect_methods(*args, **kwargs)
        for rm in rms:
            rps.extend(rm.reflect_params())
        return rps


class ReflectControllerTest(TestCase):
    def test_reflect_url_paths(self):
        rc = self.create_reflect_controllers("""
            class Foo(Controller):
                cors = True
                @param(0)
                @param(1)
                def GET(self, bar, che):
                    pass

                def POST(self, **kwargs):
                    pass
        """)[0]

        url_paths = rc.reflect_url_paths()
        self.assertEqual(2, len(url_paths))

        verbs = set(rm.http_verb for rm in url_paths["/foo/{bar}/{che}"])
        self.assertEqual(set(["GET", "OPTIONS"]), verbs)

        verbs = set(rm.http_verb for rm in url_paths["/foo"])
        self.assertEqual(set(["POST", "OPTIONS"]), verbs)


class ReflectMethodTest(TestCase):
    def test_reflect_params(self):
        rc = self.create_reflect_controllers("""
            class Foo(Controller):
                @param(0)
                @param("bar", type=int, help="bar variable")
                @param("che", type=str, required=False, help="che variable")
                def POST(self, *args, **kwargs):
                    pass
        """)[0]

        rm = list(rc.reflect_http_methods("POST"))[0]
        self.assertEqual(3, len(list(rm.reflect_params())))
        self.assertEqual(2, len(list(rm.reflect_body_params())))
        self.assertEqual(1, len(list(rm.reflect_url_params())))

    def test_get_url_path(self):
        rm = self.create_reflect_methods("""
            class Foo(Controller):
                @param(0)
                @param(1)
                def POST(self, bar, che):
                    pass
        """)[0]
        self.assertEqual("/foo/{bar}/{che}", rm.get_url_path())


class OpenABCTest(TestCase):
    def test_fields(self):
        fields = OpenAPI.fields
        self.assertLess(0, len(fields))

        for k, v in fields.items():
            self.assertTrue(isinstance(v, Field))

    def test_set_keys(self):
        c = self.create_server("")
        oa = OpenAPI(c.application)
        self.assertEqual(4, len(oa))

    def test_classfinder(self):
        oa = self.create_openapi()
        class_keys = set(oa.classfinder.class_keys.keys())
        for k in ["schema_class", "operation_class"]:
            self.assertTrue(k in class_keys, k)


class OpenAPITest(TestCase):
    def test_minimum_controller(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def GET(self):
                    pass
        """)

        self.assertTrue("/" in oa.paths)
        self.assertTrue("get" in oa.paths["/"])

    def test_params_positional_named(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                @param(0)
                def GET(self, zero, *args, **kwargs):
                    pass
        """)

        self.assertTrue("/foo/{zero}" in oa.paths)

        parameter = oa.paths["/foo/{zero}"]["get"].parameters[0]
        self.assertEqual("zero", parameter["name"])
        self.assertEqual("path", parameter["in"])

    def test_params_query(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                @param("zero")
                def GET(self, zero, *args, **kwargs):
                    pass
        """)

        self.assertEqual("query", oa.paths["/foo"]["get"].parameters[0]["in"])
        self.assertEqual(1, len(oa.paths["/foo"]["get"].parameters))

    def test_params_body(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                @param("bar", type=int, help="bar variable")
                @param("che", type=str, required=False, help="che variable")
                def POST(self, **kwargs):
                    pass
        """)

        schema = oa.paths["/foo"].post.requestBody.content["*/*"]["schema"]
        self.assertTrue(1, len(schema["required"]))
        self.assertTrue("bar" in schema["required"])
        self.assertTrue(2, len(schema["properties"]))

    def test_responses(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                @version("v2")
                def POST(self) -> dict:
                    raise CallError(401, "error message")
        """)

        self.assertEqual(
            "error message",
            oa.paths["/foo"].post.responses["401"]["description"]
        )

    def test_security_schemes(self):
        oa = self.create_openapi("")
        schemes = oa.components.securitySchemes
        self.assertTrue("auth_basic" in schemes)
        self.assertTrue("auth_bearer" in schemes)

    def test_security_requirement(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                @auth_basic()
                def POST(self):
                    pass
        """)

        op = oa.paths["/foo"].post
        self.assertTrue("auth_basic" in op.security[0])

    def test_any_operation(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def ANY(self):
                    pass
        """)

        pi = oa.paths["/foo"]
        self.assertFalse("any" in pi)
        for field_name in ["post", "get"]:
            self.assertTrue(field_name in pi)

    def test_write_json(self):
        oa = self.create_openapi(
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

        dp = self.create_dir()
        oa.write_json(dp)

    def test_multiple_path_with_options(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                cors = True
                @param(0)
                @param(1)
                def GET(self, bar, che):
                    pass
        """)


class SchemaTest(TestCase):
    def test_list_value_types(self):
        rt = ReflectType(list[dict[str, int]|tuple[float, float]])
        schema = Schema(None)
        schema.set_type(rt)
        self.assertTrue(schema.is_array())
        self.assertEqual(2, len(schema["items"]["anyOf"]))

