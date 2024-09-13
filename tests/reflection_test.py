# -*- coding: utf-8 -*-

from endpoints.compat import *
from endpoints.reflection import (
    OpenAPI,
    Field,
    Parameter,
    Operation,
    ReflectController,
    ReflectMethod,
    OpenABC,
    Paths,
)

from . import TestCase


class TestCase(TestCase):
    def create_openapi(self, *args, **kwargs):
        server = self.create_server(*args, **kwargs)
        return OpenAPI(server.application)

#     def create_server(self, *args, **kwargs):
#         kwargs.setdefault("cors", False)
#         return super().create_server(*args, **kwargs)


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




class FieldTest(TestCase):
    def test_get_factory_classes(self):
        f = Field(Paths[str, Operation])
        classes = f.get_factory_classes()
        self.assertEqual(1, len(classes))

        f = Field(dict)
        classes = f.get_factory_classes()
        self.assertEqual(0, len(classes))

        f = Field(OpenABC)
        classes = f.get_factory_classes()
        self.assertEqual(0, len(classes))

        f = Field(dict[str, Operation])
        classes = f.get_factory_classes()
        self.assertEqual(1, len(classes))
        #         self.assertTrue("operation_class" in classes)

        f = Field(dict[str, Parameter|Operation])
        classes = f.get_factory_classes()
        self.assertEqual(2, len(classes))
        #         for k in ["operation_class", "parameter_class"]:
#             self.assertTrue(k in classes)

        f = Field(list[Operation])
        classes = f.get_factory_classes()
        self.assertEqual(1, len(classes))
        #         self.assertTrue("operation_class" in classes)

        f = Field(list[Parameter|Operation])
        classes = f.get_factory_classes()
        self.assertEqual(2, len(classes))
        #         for k in ["operation_class", "parameter_class"]:
#             #for k in ["Operation", "Parameter"]:
#             self.assertTrue(k in classes)

        f = Field(Parameter|Operation|OpenABC)
        classes = f.get_factory_classes()
        #classes = {k: c for k, c in f.get_factory_classes()}
        #classes = {c.__name__: c for c in f.get_factory_classes()}
        self.assertEqual(2, len(classes))
        #         for k in ["operation_class", "parameter_class"]:
#             #for k in ["Operation", "Parameter"]:
#             self.assertTrue(k in classes)


class ReflectMethodTest(TestCase):
    def test_reflect_params(self):
        server = self.create_server("""
            class Foo(Controller):
                @param(0)
                @param("bar", type=int, help="bar variable")
                @param("che", type=str, required=False, help="che variable")
                def POST(self, *args, **kwargs):
                    pass
        """)

        pf = server.application.router.pathfinder
        keys, value = next(pf.get_class_items())
        rc = ReflectController(keys, value)
        rm = list(rc.reflect_http_methods("POST"))[0]
        self.assertEqual(3, len(list(rm.reflect_params())))
        self.assertEqual(2, len(list(rm.reflect_body_params())))
        self.assertEqual(1, len(list(rm.reflect_url_params())))


class OpenABCTest(TestCase):
    def test_fields(self):
        fields = OpenAPI.fields
        self.assertLess(0, len(fields))

        for k, v in fields.items():
            self.assertTrue(isinstance(v, Field))

    def test_set_keys(self):
        c = self.create_server("")
        oa = OpenAPI(c.application)
        self.assertEqual(2, len(oa))

#     def test_stdtypes_init(self):
#         """Make sure OpenABC correctly handles standard types like list and
#         dict and also handles UnionType"""
#         rm = ReflectMethod("GET", lambda: None, None)
#         op = Operation(None, reflect_method=rm)
#         # if no errors were raised then it passed

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

#     def test_headers(self):
#         c = self.create_server("""
#             class Foo(Controller):
#                 cors = False
# 
#                 @version("v2")
#                 def POST(self):
#                     pass
#         """)
# 
#         oa = OpenAPI(c.application)



#     def test_paths(self):
#         c = self.create_server(
#             {
#                 "": [
#                     "class Default(Controller):",
#                     "    def GET(*args, **kwargs): pass",
#                     ""
#                 ],
#                 "boo": [
#                     "class Default(Controller):",
#                     "    def GET(*args, **kwargs): pass",
#                     ""
#                 ],
#                 "foo": [
#                     "class Default(Controller):",
#                     "    def GET(*args, **kwargs): pass",
#                     "",
#                     "class Bar(Controller):",
#                     "    def GET(*args, **kwargs): pass",
#                     "    def POST(*args, **kwargs): pass",
#                     ""
#                 ],
#                 "foo.baz": [
#                     "class Default(Controller):",
#                     "    def GET(*args, **kwargs): pass",
#                     "",
#                     "class Che(Controller):",
#                     "    def ANY(*args, **kwargs): pass",
#                     ""
#                 ],
#             },
#         )
# 
#         oa = OpenAPI(c.application)


class ParameterTest(TestCase):
    def test_set_param(self):
        rp = self.create_reflect_params("""
            class Foo(Controller):
                @param("foo", type=str, required=False, help="che variable")
                def POST(self, **kwargs):
                    pass
        """)[0]

        pout.v(rp)

