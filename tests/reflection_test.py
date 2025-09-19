# -*- coding: utf-8 -*-
from typing import TypedDict

from datatypes.reflection.inspect import ReflectType

from endpoints.compat import *
from endpoints.reflection.openapi import (
    OpenAPI,
    Field,
    Schema,
)
from endpoints.reflection.inspect import (
    ReflectController,
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
            rcs.append(value["reflect_class"])
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
    def test_reflect_url_paths_1(self):
        rc = self.create_reflect_controllers("""
            class Foo(Controller, CORSMixin):
                cors = True
                def GET(self, bar, che, /):
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

    def test_reflect_url_modules(self):
        rc = self.create_reflect_controllers(
            {
                "": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ],
                "foo_bar": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "class Bar(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "    def POST(*args, **kwargs): pass",
                    ""
                ],
                "foo_bar.baz": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "class Che(Controller):",
                    "    def ANY(*args, **kwargs): pass",
                    ""
                ],
            },
        )[-1]

        rms = list(rc.reflect_url_modules())
        self.assertEqual(2, len(rms))
        self.assertEqual("foo-bar", rms[0].module_key)
        self.assertEqual("foo_bar", rms[0].module_basename)
        self.assertEqual("baz", rms[1].module_key)
        self.assertEqual("baz", rms[1].module_basename)

    def test_get_url_path(self):
        rcs = self.create_reflect_controllers("""
            class Bar(object):
                class Foo(Controller):
                    def GET(self):
                        pass

            class Che(Controller):
                def GET(self):
                    pass

            class Default(Controller):
                def GET(self):
                    pass
        """)

        self.assertEqual("/", rcs[0].get_url_path())
        self.assertEqual("/che", rcs[1].get_url_path())
        self.assertEqual("/bar/foo", rcs[2].get_url_path())


class ReflectMethodTest(TestCase):
    def test_reflect_params_post(self):
        rc = self.create_reflect_controllers("""
            class Foo(Controller):
                def POST(self, foo, /, *, bar: int, che: str = None):
                    pass
        """)[0]

        rm = list(rc.reflect_http_methods("POST"))[0]
        self.assertEqual(3, len(list(rm.reflect_params())))
        self.assertEqual(2, len(list(rm.reflect_body_params())))
        self.assertEqual(1, len(list(rm.reflect_url_params())))
        self.assertEqual(0, len(list(rm.reflect_query_params())))

    def test_reflect_params_get(self):
        rc = self.create_reflect_controllers("""
            class Foo(Controller):
                def GET(self, foo, /, bar: int, che: str = ""):
                    pass
        """)[0]

        rm = list(rc.reflect_http_methods("GET"))[0]
        self.assertEqual(2, len(list(rm.reflect_query_params())))
        self.assertEqual(3, len(list(rm.reflect_params())))
        self.assertEqual(3, len(list(rm.reflect_url_params())))
        self.assertEqual(1, len(list(rm.reflect_path_params())))

    def test_get_url_path_1(self):
        rm = self.create_reflect_methods("""
            class Foo(Controller):
                def POST(self, bar, che, /):
                    pass
        """)[0]
        self.assertEqual("/foo/{bar}/{che}", rm.get_url_path())

    def test_get_url_path_default(self):
        """Default controllers with url params had double slashes (eg //{foo})
        """
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def POST(self, bar, /):
                    pass
        """)[0]
        self.assertEqual("/{bar}", rm.get_url_path())

        rm = self.create_reflect_methods("""
            class Default(Controller):
                def POST(self):
                    pass
        """)[0]
        self.assertEqual("/", rm.get_url_path())

    def test_get_http_method_names_1(self):
        rcs = self.create_reflect_controllers("""
            class _ParentController(Controller):
                def GET(self):
                    pass

            class Foo(_ParentController):
                def GET_one(self):
                    pass
                def GET_two(self):
                    pass
                def POST_one(self):
                    pass
                def ANY(self):
                    pass
        """)

        for rc in rcs:
            controller_method_names = rc.get_http_method_names()

            method_names = controller_method_names["GET"]
            self.assertEqual(["GET", "GET_one", "GET_two"], method_names)

            method_names = controller_method_names["POST"]
            self.assertEqual(["POST_one"], method_names)

            method_names = controller_method_names["ANY"]
            self.assertEqual(["ANY"], method_names)

    def test_get_http_method_names_no_options(self):
        rcs = self.create_reflect_controllers("""
            class Foo(Controller):
                cors = False
                def GET(self):
                    pass
        """)

        controller_method_names = rcs[0].get_method_names()
        self.assertFalse("OPTIONS" in controller_method_names)

    def test_get_method_info(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET_foo(self, foo, bar, /, *, che, **kwargs):
                    pass
        """)[0]

        method_info = rm.get_method_info()
        self.assertEqual("GET_foo", method_info["method_name"])

    def test_mediatype_auto(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET() -> str: pass
        """)[0]

        media_types = rm.get_success_media_types()
        self.assertEqual("text/html", media_types[0][1])

    def test_mediatype_ext(self):
        rm = self.create_reflect_methods("""
            class Default_jpg(Controller):
                def GET() -> bytes: pass
        """)[0]

        media_types = rm.get_success_media_types()
        self.assertEqual("image/jpeg", media_types[0][1])

    def test_mediatype_annotated_single(self):
        """
        https://docs.python.org/3/library/typing.html#typing.Annotated
        """
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET(self) -> Annotated[str, "text/plain"]: pass
        """)[0]

        media_types = rm.get_success_media_types()
        self.assertEqual(1, len(media_types))
        t = media_types[0]
        self.assertTrue(issubclass(t[0], str))
        self.assertEqual("text/plain", t[1])

    def test_mediatype_annotated_union(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET(self) -> (
                    Annotated[str, "text/yaml"]
                    | Annotated[bytes, "image/jpeg"]
                    | int
                ): pass
        """)[0]

        media_types = rm.get_success_media_types()
        self.assertEqual(3, len(media_types))

        t = media_types[1]
        self.assertTrue(issubclass(t[0], bytes))
        self.assertEqual("image/jpeg", t[1])

    def test_mediatype_request(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def POST(self, file: io.BytesIO) -> str:
                    pass
        """)[0]

        mts = rm.get_request_media_types()
        self.assertEqual(1, len(mts))
        self.assertTrue("multipart" in mts[0])

        # the file doesn't have to be passed up so this should support
        # the non multipart media types
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def POST(self, file: Optional[io.BytesIO] = None) -> str:
                    pass
        """)[0]

        mts = rm.get_request_media_types()
        self.assertEqual(3, len(mts))

        # file is required so the only media type is multipart
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def POST(self, file: io.BytesIO, foo: int) -> str:
                    pass
        """)[0]

        mts = rm.get_request_media_types()
        self.assertEqual(1, len(mts))
        self.assertTrue("multipart" in mts[0])

    def test_reflect_defined_params(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET(self, *args, **kwargs):
                    pass
        """)[0]

        self.assertEqual(0, len(list(rm.reflect_url_params())))
        self.assertEqual(0, len(list(rm.reflect_query_params())))
        self.assertEqual(0, len(list(rm.reflect_defined_params())))



class ReflectParamTest(TestCase):
    """Test the ReflectParam class

    This inherited all of the original tests from call.Param and
    decorators.param which is why a lot of the test names are strange
    """
    def test_param_query(self):
        """This was moved from decorators_test.ParamTest when a param_query
        decorator existed, that's why it has the strange name
        """
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(self, foo: int, bar: float):
                    pass
        """)
        self.assertEqual(1, rps[0].normalize_value("1"))
        self.assertEqual(1.5, rps[1].normalize_value("1.5"))

        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(self, foo: list[int]):
                    pass
        """)
        self.assertEqual(
            [1, 2, 3, 4, 5],
            rps[0].normalize_value(["1,2,3,4", "5"])
        )

    def test_param_body(self):
        """This was moved from decorators_test.ParamTest when a param_body
        decorator existed, that's why it has the strange name"""
        rp = self.create_reflect_params("""
            class Default(Controller):
                def POST(self, foo: Annotated[int, dict(choices=[1, 2, 3])]):
                    pass
        """)[0]
        with self.assertRaises(ValueError):
            rp.normalize_value("8")
        self.assertEqual(1, rp.normalize_value("1"))

    def test_type_string_casting(self):
        """I made a change in v4.0.0 that would encode a value to String when
        the param type was a str descendent, but my change was bad because it
        would just cast it to a String, not to the type, this makes sure
        that's fixed"""
        c = self.create_server("""
            class Che(String):
                pass

            class Default(Controller):
                def POST(self, che: Che):
                    return che.__class__.__name__
        """)

        r = c.post("/", {"che": "1234"})
        self.assertEqual("Che", r._body)

    def test_regex_issue_77(self):
        """
        https://github.com/Jaymon/endpoints/issues/77
        """
        c = self.create_server("""
            import datetime

            def parse(dts):
                return datetime.datetime.strptime(dts, "%Y-%m-%d")

            class Foo(Controller):
                def GET(
                    self,
                    dt: Annotated[parse, dict(regex=r"^\\d{4}-\\d{2}-\\d{2}$")]
                ):
                    return dt
        """)

        res = c.handle("/foo", query="dt=2018-01-01")
        self.assertEqual(res._body.year, 2018)
        self.assertEqual(res._body.month, 1)
        self.assertEqual(res._body.day, 1)

    async def test_append_list_choices(self):
        rp = self.create_reflect_params("""
            class Default(Controller):
                def POST(
                    self,
                    foo: Annotated[list[int], dict(choices=[1, 2])]
                ):
                    pass
        """)[0]

        self.assertEqual([1, 2], rp.normalize_value("1,2"))

        with self.assertRaises(ValueError):
            rp.normalize_value("1,2,3")

        self.assertEqual([1], rp.normalize_value(1))

        with self.assertRaises(ValueError):
            rp.normalize_value(3)

    async def test_param_multiple_names(self):
        rm = self.create_reflect_methods("""
            class Default(Controller):
                def GET(
                    self,
                    foo: Annotated[int, dict(names=["foos", "foo3"])]
                ):
                    return foo
        """)[0]

        bind_info = rm.get_bind_info(**{"foos": 1})
        self.assertEqual(1, bind_info["bound_kwargs"]["foo"])

        bind_info = rm.get_bind_info(**{"foo": 2})
        self.assertEqual(2, bind_info["bound_kwargs"]["foo"])

        bind_info = rm.get_bind_info(**{"foo3": 3})
        self.assertEqual(3, bind_info["bound_kwargs"]["foo"])

        bind_info = rm.get_bind_info(**{"foo4": 4})
        self.assertTrue("foo" in bind_info["missing_names"])

    async def test_param_size(self):
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(
                    self,
                    foo: Annotated[int, dict(min_size=100)],
                    bar: Annotated[int, dict(max_size=100)],
                    che: Annotated[int, dict(min_size=100, max_size=200)],
                    boo: Annotated[str, dict(min_size=2, max_size=4)],
                ):
                    pass
        """)

        self.assertEqual(100, rps[0].normalize_value("100"))
        self.assertEqual(200, rps[0].normalize_value("200"))
        with self.assertRaises(ValueError):
            rps[0].normalize_value("10")

        self.assertEqual(10, rps[1].normalize_value("10"))
        self.assertEqual(100, rps[1].normalize_value("100"))
        with self.assertRaises(ValueError):
            rps[1].normalize_value("200")

        self.assertEqual(150, rps[2].normalize_value("150"))
        with self.assertRaises(ValueError):
            rps[2].normalize_value("300")
        with self.assertRaises(ValueError):
            rps[2].normalize_value("10")

        self.assertEqual("foo", rps[3].normalize_value("foo"))
        with self.assertRaises(ValueError):
            rps[3].normalize_value("barbar")

    async def test_param_empty_default(self):
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(
                    self,
                    foo: int | None = None
                ):
                    pass
        """)

        self.assertEqual(None, rps[0].normalize_value(None))

    async def test_param_regex(self):
        rps = self.create_reflect_params("""
            import re

            class Default(Controller):
                def GET(
                    self,
                    foo: Annotated[str, dict(regex=r"^\\S+@\\S+$")],
                    bar: Annotated[str, dict(regex=re.compile(r"^\\S+@\\S+$"))],
                ):
                    pass
        """)

        rps[0].normalize_value("foo@bar.com")
        with self.assertRaises(ValueError):
            rps[0].normalize_value(" foo@bar.com")

        rps[1].normalize_value("foo@bar.com")
        with self.assertRaises(ValueError):
            rps[1].normalize_value(" foo@bar.com")

    async def test_param_bool(self):
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(
                    self,
                    foo: bool,
                ):
                    pass
        """)

        self.assertEqual(True, rps[0].normalize_value("true"))
        self.assertEqual(True, rps[0].normalize_value("True"))
        self.assertEqual(True, rps[0].normalize_value("1"))
        self.assertEqual(False, rps[0].normalize_value("false"))
        self.assertEqual(False, rps[0].normalize_value("False"))
        self.assertEqual(False, rps[0].normalize_value("0"))

    async def test_param_list(self):
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(
                    self,
                    foo: list,
                ):
                    pass
        """)

        v = ["bar", "baz"]
        self.assertEqual(v, rps[0].normalize_value(v))

    async def test_positionals(self):
        """Make sure positional args work"""
        rms = self.create_reflect_methods("""
            class Default(Controller):
                def GET_1(
                    self,
                    foo: int,
                    /,
                ):
                    pass

                def GET_2(
                    self,
                    foo: str,
                    bar: int = 20,
                    /,
                ):
                    pass

                def GET_3(
                    self,
                    foo: int,
                    bar: int = 20,
                    /,
                    *,
                    che: str = "che value"
                ):
                    pass
        """)

        bind_info = rms[0].get_bind_info(*[1])
        self.assertEqual([1], bind_info["bound_args"])
        bind_info = rms[0].get_bind_info()
        self.assertTrue("foo" in bind_info["missing_names"])

        bind_info = rms[1].get_bind_info(*[1])
        self.assertEqual([1], bind_info["bound_args"])

        bind_info = rms[1].get_bind_info(*[1, 2])
        self.assertEqual([1, 2], bind_info["bound_args"])

        bind_info = rms[2].get_bind_info(*[1, 2], **{"che": "3"})
        self.assertEqual([1, 2], bind_info["bound_args"])
        self.assertEqual("3", bind_info["bound_kwargs"]["che"])

        bind_info = rms[2].get_bind_info(*[1], **{"che": "3"})
        self.assertEqual([1], bind_info["bound_args"])
        self.assertEqual("3", bind_info["bound_kwargs"]["che"])

        bind_info = rms[2].get_bind_info(*[1])
        self.assertEqual([1], bind_info["bound_args"])

    def test_required_arg_kwargs(self):
        """positional or keyword catch-alls shouldn't be required"""
        rps = self.create_reflect_params("""
            class Default(Controller):
                def GET(self, *args, **kwargs):
                    pass
        """)

        for count, rp in enumerate(rps):
            self.assertFalse(rp.is_required())
        self.assertLess(0, count)


class OpenapiOpenABCTest(TestCase):
    def test_fields(self):
        fields = OpenAPI.fields
        self.assertLess(0, len(fields))

        for k, v in fields.items():
            self.assertTrue(isinstance(v, Field))

    def test_set_keys(self):
        c = self.create_server("")
        oa = OpenAPI(c.application)
        self.assertEqual(5, len(oa))

    def test_classfinder(self):
        oa = self.create_openapi()
        class_keys = set(oa.classfinder.class_keys.keys())
        for k in ["schema_class", "operation_class"]:
            self.assertTrue(k in class_keys, k)


class OpenapiOpenAPITest(TestCase):
    def test_minimum_controller(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def GET(self):
                    pass
        """)

        self.assertTrue("/" in oa.paths)
        self.assertTrue("get" in oa.paths["/"])

    def test_params_body(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def POST(self, bar: int, che: Optional[str]):
                    pass
        """)

        for media_type in oa.paths["/foo"].post.requestBody.content.values():
            schema = media_type["schema"]
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

        self.assertEqual(
            "OK",
            oa.paths["/foo"].post.responses["200"]["description"]
        )

    def test_response_merge(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def POST(self) -> dict:
                    raise CallError(401, "call error message 1")
                    raise CallError(401, "call error message 2")
        """)

        for errmsg in ["call error message 1", "call error message 2"]:
            self.assertTrue(
                errmsg in oa.paths["/foo"].post.responses["401"]["description"]
            )

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

    def test_operation_operationid_simple(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def GET(self):
                    pass

                def POST(self):
                    pass

                def PUT(self):
                    pass
        """)

        pi = oa.paths["/foo"]
        for http_verb in ["post", "get", "put"]:
            self.assertEqual(f"{http_verb}Foo", pi[http_verb]["operationId"])

    def test_operation_operationid_ext(self):
        oa = self.create_openapi({
            "bar": """class Foo_ext(Controller):
                def GET(self):
                    pass
            """
        })

        pi = oa.paths["/bar/foo.ext"]
        self.assertEqual("getBarFooExt", pi["get"]["operationId"])

    def test_operation_operationid_positionals(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def GET(self, bar, che, /):
                    pass
        """)
        #pout.v(oa.paths)

        pi = oa.paths["/foo/{bar}/{che}"]
        self.assertEqual("getFooWithBarChe", pi["get"]["operationId"])

    def test_operation_operationid_any(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def ANY(self):
                    pass
        """)

        pi = oa.paths["/foo"]

        for http_verb in ["post", "get"]:
            self.assertEqual(f"{http_verb}Foo", pi[http_verb]["operationId"])

    def test_operation_operationid_multiple_methods_with_args(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def GET_1(self, bar, /):
                    pass

                def GET_2(self, che, /):
                    pass
        """)

        ti = {
            "/foo/{bar}": "getFoo1",
            "/foo/{che}": "getFoo2"
        }
        for path, operation_id in ti.items():
            pi = oa.paths[path]
            self.assertEqual(operation_id, pi["get"]["operationId"])

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
        fp = oa.write_json(dp)
        self.assertTrue(fp.isfile())

    def test_write_yaml(self):
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
        fp = oa.write_yaml(dp)
        self.assertTrue(fp.isfile())

    def test_url_path(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def ANY(self, param, /, *args, **kwargs) -> dict:
                    pass
        """)

        pi = oa.paths["/{param}"]
        self.assertEqual(1, len(pi["parameters"]))
        self.assertEqual("param", pi["parameters"][0]["name"])

    def test_get_tags_values_1(self):
        oa = self.create_openapi(
            {
                "": [
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

        self.assertEqual(3, len(oa["tags"]))

        pi = oa.paths["/foo/baz/che"]
        self.assertEqual(2, len(pi["get"]["tags"]))

    def test_get_tags_values_default(self):
        oa = self.create_openapi(
            {
                "": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                    "class Foo(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ],
                "bar": [
                    "class Default(Controller):",
                    "    def GET(*args, **kwargs): pass",
                    "",
                ],
            },
        )

        self.assertEqual(2, len(oa["tags"]))

        pi = oa.paths["/foo"]
        self.assertEqual(["root"], pi["get"]["tags"])

        pi = oa.paths["/bar"]
        self.assertEqual(["bar"], pi["get"]["tags"])


class OpenapiPathItemTest(TestCase):
    def test_multiple_path_with_options(self):
        oa = self.create_openapi("""
            class Foo(Controller, CORSMixin):
                cors = True
                def GET(self, bar, che, /):
                    pass
        """)

        pi = oa.paths["/foo/{bar}/{che}"]
        for http_verb in ["get", "options"]:
            self.assertTrue(http_verb in pi)

        self.assertFalse("405" in pi["options"]["responses"])
        self.assertFalse("/foo" in oa.paths)

    def test_params_positional_named(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def GET(self, zero, /, *args, **kwargs):
                    pass
        """)

        self.assertTrue("/foo/{zero}" in oa.paths)

        parameter = oa.paths["/foo/{zero}"].parameters[0]
        self.assertEqual("zero", parameter["name"])
        self.assertEqual("path", parameter["in"])


class OpenapiOperationTest(TestCase):
    def test_any_parameters(self):
        """Makes sure ANY sets a get operation with parameters and sets a post
        with a requestBody with a foo property"""
        oa = self.create_openapi("""
            class Default(Controller):
                def ANY(self, foo: int = 1) -> None:
                    pass
        """)

        pi = oa.paths["/"]

        self.assertEqual("foo", pi["get"]["parameters"][0]["name"])
        self.assertFalse("Paremeters"in pi["post"])
        for media_type in pi["post"]["requestBody"]["content"].values():
            schema = media_type["schema"]
            self.assertTrue("foo" in schema["properties"])

    def test_params_query(self):
        oa = self.create_openapi("""
            class Foo(Controller):
                def GET(self, zero, *args, **kwargs):
                    pass
        """)

        pi = oa.paths["/foo"]
        self.assertEqual(0, len(pi.parameters))
        self.assertEqual("query", pi["get"]["parameters"][0]["in"])

    def test_security(self):
        oa = self.create_openapi("")

        # add some more security schemes
        components = oa.components
        schemes = oa.components.securitySchemes
        schemes["auth_basic_q"] = components.create_security_scheme_instance(
            type="apiKey",
            name="basic_key",
            _in="query"
        )
        schemes["auth_basic_h"] = components.create_security_scheme_instance(
            type="apiKey",
            name="X-Basic-Key",
            _in="header"
        )

        # create a method we will use to create a path item to check to make
        # sure the security key was populated correctly
        rm = self.create_reflect_methods("""
            class Foo(Controller):
                @auth_basic
                def POST(self):
                    pass
        """)[0]
        pi = oa.create_instance("path_item_class")
        pi.add_method(rm)
        self.assertEqual(3, len(pi["post"]["security"]))

    def test_parameters_catchall(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def GET(self, **kwargs):
                    pass
        """)

        op = oa["paths"]["/"]["get"]
        self.assertFalse("parameters" in op)


class OpenapiSchemaTest(TestCase):
    def test_list_value_types(self):
        rt = ReflectType(list[dict[str, int]|tuple[float, float]])
        schema = Schema(None)
        schema.set_type(rt)
        self.assertTrue(schema.is_array())
        self.assertEqual(2, len(schema["items"]["anyOf"]))

    def test_ref_keyword(self):
        ref = "foo/bar/che"
        s = Schema(None, **{"$ref": ref})
        self.assertEqual(ref, s["$ref"])

    def test_validate_refs(self):
        oa = self.create_openapi()
        schema = Schema(oa)

        comp_schema = Schema(oa)
        comp_schema.set_type(ReflectType(dict[str, int]))
        ref_schema = schema.add_components_schema("foo", comp_schema)
        schema.set_type(ReflectType(list))
        schema["items"] = ref_schema

        schema.validate([{"foo": 1, "bar": 2}])

        with self.assertRaises(Exception):
            schema.validate([{"foo": "one"}])

    def test_get_ref_schema(self):
        oa = self.create_openapi()

        comp_schema = Schema(oa)
        comp_schema.set_type(ReflectType(dict[str, int]))
        ref_schema = comp_schema.add_components_schema("foo", comp_schema)

        self.assertTrue(ref_schema.is_ref())

        rs = ref_schema.get_ref_schema()
        self.assertEqual(rs, comp_schema)

        ref_schema["$ref"] = "http://bogus.url"
        with self.assertRaises(ValueError):
            ref_schema.get_ref_schema()

    def test_todict(self):
        s = Schema(None)
        s.set_object_keys()
        d = s.todict()
        self.assertFalse("properties" in d)
        self.assertFalse("required" in d)
        self.assertTrue("type" in d)

    def test_set_schema(self):
        schema = Schema(None)
        schema.set_type(ReflectType(str))

        schema2 = Schema(None)
        schema2.set_type(ReflectType(dict[str, int]))
        self.assertNotEqual(schema, schema2)

        schema.set_schema(schema2)
        self.assertEqual(schema, schema2)

    def test_param_catchall(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def POST(self, **kwargs):
                    pass
        """)

        op = oa["paths"]["/"]["post"]
        content = op["requestBody"]["content"]
        for media_type, mt in content.items():
            self.assertEqual(0, len(mt))

    def test_set_type_typed_dict(self):
        class TD(TypedDict):
            foo: str
            bar: int
            che: dict[str, str]

        rt = ReflectType(TD)
        s = Schema(None)
        s.set_type(rt)
        for k in ["foo", "bar", "che"]:
            self.assertTrue(k in s["properties"])


class OpenapiComponentsTest(TestCase):
    def test_get_security_schemes_value(self):
        oa = self.create_openapi("")
        schemes = oa.components.securitySchemes
        self.assertTrue("auth_basic" in schemes)
        self.assertTrue("auth_bearer" in schemes)

    def test_security_scheme_in_keyword(self):
        """This just makes sure that passing in kwarg _in=... works as
        expected"""
        oa = self.create_openapi("")

        # add some more security schemes
        components = oa.components
        schemes = oa.components.securitySchemes

        schemes["foo"] = components.create_security_scheme_instance(
            type="apiKey",
            name="basic_key",
            _in="query"
        )
        self.assertTrue("in" in schemes["foo"])

    def test_add_schema(self):
        oa = self.create_openapi("")
        s = Schema(oa)

        s.set_type(ReflectType(list[str]))

        s2 = oa.components.add_schema("foo", s)
        self.assertTrue("$ref" in s2)
        self.assertEqual(s, oa.components.schemas["foo"])

    def test_get_schema(self):
        oa = self.create_openapi("")

        s = Schema(oa)
        s.set_type(ReflectType(list[str]))

        s2 = oa.components.add_schema("foo", s)
        s3 = oa.components.get_schema(s2["$ref"])
        self.assertEqual(s, s3)

        s4 = oa.components.get_schema("foo")
        self.assertEqual(s, s4)

    def test_security_decorator(self):
        oa = self.create_openapi("""
            class Default(Controller):
                @auth_bearer
                def GET(self) -> None:
                    return None
        """)

        op = oa["paths"]["/"]["get"]
        self.assertEqual(1, len(op["security"]))
        self.assertTrue("auth_bearer" in op["security"][0])


class OpenapiRequestBodyTest(TestCase):
    def test_multipart_1(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def POST(self, foo: io.BytesIO) -> None:
                    return None
        """)

        op = oa.paths["/"]["post"]
        content = op["requestBody"]["content"]
        mt = content["multipart/form-data"]

        schema = mt["schema"]
        self.assertEqual("string", schema["properties"]["foo"]["type"])
        self.assertEqual("binary", schema["properties"]["foo"]["format"])

    def test_multipart_2(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def POST(
                    self,
                    bar: str,
                    foo: io.BytesIO|None = None,
                ) -> None:
                    return None
        """)

        content = oa.paths["/"]["post"]["requestBody"]["content"]
        for media_range, mt in content.items():
            if media_range.startswith("multipart/"):
                self.assertTrue("foo" in mt["schema"]["properties"])

            self.assertTrue("bar" in mt["schema"]["properties"])

    def test_multipart_3(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def POST(
                    self,
                    foo: Annotated[io.BytesIO, "image/*"],
                    che: str
                ) -> None:
                    return None
        """)

        content = oa.paths["/"]["post"]["requestBody"]["content"]
        mt = content["multipart/form-data"]
        encoding = mt["encoding"]
        self.assertTrue("image/*", encoding["foo"]["contentType"])

    def test_multipart_catchall(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def POST(
                    self,
                    foo: io.BytesIO,
                    **kwargs
                ) -> None:
                    return None
        """)

        content = oa.paths["/"]["post"]["requestBody"]["content"]
        mt = content["multipart/form-data"]
        self.assertEqual(1, len(mt["schema"]["properties"]))


class OpenapiResponseTest(TestCase):
    def test_infer_or_type(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def ANY(self) -> dict[str, int]|list[int]|None:
                    return None
        """)

        responses = oa.paths["/"]["post"].responses

        self.assertTrue("204" in responses)

        schema = responses["200"]["content"]["application/json"]["schema"]
        self.assertTrue("oneOf" in schema)
        self.assertEqual(2, len(schema["oneOf"]))

    def test_str_return_media_type(self):
        oa = self.create_openapi("""
            class Default(Controller):
                def GET(self, param, *args, **kwargs) -> str:
                    pass
        """)

        content = oa.paths["/"]["get"]["responses"]["200"]["content"]
        self.assertTrue("text/html" in content)

