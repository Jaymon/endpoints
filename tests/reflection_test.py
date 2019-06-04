# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
from . import TestCase, SkipTest
import os

import testdata

from endpoints.call import Controller
from endpoints.reflection import Reflect, ReflectMethod, ReflectController, ReflectModule


class ReflectTest(TestCase):

    def create_reflect(self, controller_prefix):
        return Reflect([controller_prefix])

    def find_reflect(self, uri, controllers):
        ret = None
        for d in controllers:
            if d.uri == uri:
                ret = d
                break
        return ret

    def test_controllers(self):
        # putting the C back in CRUD
        controller_prefix = "controller_reflect_endpoints"
        testdata.create_modules({
            controller_prefix: [
                "import endpoints",
                "class Default(endpoints.Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.foo".format(controller_prefix): [
                "import endpoints",
                "class Default(endpoints.Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.che".format(controller_prefix): [
                "from endpoints import Controller",
                "class Baz(Controller):",
                "    def POST(*args, **kwargs): pass",
                ""
            ],
            "{}.che.bam".format(controller_prefix): [
                "from endpoints import Controller as Con",
                "class _Base(Con):",
                "    def GET(*args, **kwargs): pass",
                "",
                "class Boo(_Base):",
                "    def DELETE(*args, **kwargs): pass",
                "    def POST(*args, **kwargs): pass",
                ""
                "class Bah(_Base):",
                "    '''this is the doc string'''",
                "    def HEAD(*args, **kwargs): pass",
                ""
            ]
        })

        r = self.create_reflect(controller_prefix)
        l = list(r.controllers)
        self.assertEqual(5, len(l))

        d = self.find_reflect("/che/bam/bah", l)
        self.assertSetEqual(set(["GET", "HEAD", "OPTIONS"]), set(d.methods.keys()))
        self.assertGreater(len(d.desc), 0)

        d = self.find_reflect("/", l)
        self.assertNotEqual(d, None)

        d = self.find_reflect("/foo", l)
        self.assertNotEqual(d, None)

    def test_methods(self):
        class MethodsController(Controller):
            def POST(self): pass
            def GET(self): pass
            def ABSURD(self): pass
            def ignORED(self): pass

        rc = ReflectController("foo", MethodsController)
        methods = list(rc.methods)

        self.assertEqual(4, len(methods))
        for o in ['ABSURD', 'GET', 'POST', 'OPTIONS']:
            self.assertTrue(o in methods)

    def test_versioned_controllers(self):
        # putting the C back in CRUD
        controller_prefix = "versioned_controllers"
        testdata.create_modules({
                "foo": [
                    "import endpoints",
                    "from endpoints.decorators import param, version",
                    "class Bar(endpoints.Controller):",
                    "    @param('foo', default=1, type=int)",
                    "    @param('bar', type=bool, required=False)",
                    "    @version('v1')",
                    "    def GET_v1(self): pass",
                    "",
                    "    @version('v2')",
                    "    def GET_v2(self): pass",
                    ""
                ],
                "che": [
                    "from endpoints import Controller",
                    "from endpoints.decorators import version",
                    "class Baz(Controller):",
                    "    @version('v3')",
                    "    def GET_v3(self): pass",
                    ""
                ],
            }, prefix=controller_prefix)

        rs = self.create_reflect(controller_prefix)
        l = list(rs.controllers)

        self.assertEqual(2, len(l))
        for d in l:
            self.assertEqual(2, len(d.methods))

        d = self.find_reflect("/foo/bar", l)
        self.assertTrue(d)

        d = self.find_reflect("/che/baz", l)
        self.assertTrue(d)

    def test_decorators_inherit_2(self):
        """you have a parent class with POST method, the child also has a POST method,
        what do you do? What. Do. You. Do?"""
        controller_prefix = "decinherit2"
        m = testdata.create_module(controller_prefix, [
            "import endpoints",
            "",
            "def a(f):",
            "    def wrapped(*args, **kwargs):",
            "        return f(*args, **kwargs)",
            "    return wrapped",
            "",
            "class b(object):",
            "    def __init__(self, func):",
            "        self.func = func",
            "    def __call__(*args, **kwargs):",
            "        return f(*args, **kwargs)",
            "",
            "def c(func):",
            "    def wrapper(*args, **kwargs):",
            "        return func(*args, **kwargs)",
            "    return wrapper",
            "",
            "def POST(): pass",
            "",
            "class D(object):",
            "    def HEAD(): pass"
            "",
            "class _BaseController(endpoints.Controller):",
            "    @a",
            "    @b",
            "    def POST(self, **kwargs): pass",
            "",
            "    @a",
            "    @b",
            "    def HEAD(self): pass",
            "",
            "    @a",
            "    @b",
            "    def GET(self): pass",
            "",
            "class Default(_BaseController):",
            "    @c",
            "    def POST(self, **kwargs): POST()",
            "",
            "    @c",
            "    def HEAD(self):",
            "        d = D()",
            "        d.HEAD()",
            "",
            "    @c",
            "    def GET(self):",
            "        super(Default, self).GET()",
            "",
        ])

        rs = self.create_reflect(controller_prefix)
        l = list(rs.controllers)
        r = l[0]
        self.assertEqual(1, len(r.decorators["POST"]))
        self.assertEqual(1, len(r.decorators["HEAD"]))
        self.assertEqual(3, len(r.decorators["GET"]))


    def test_decorator_inherit_1(self):
        """make sure that a child class that hasn't defined a METHOD inherits the
        METHOD method from its parent with decorators in tact"""
        controller_prefix = "foodecinherit"
        m = testdata.create_module(controller_prefix, [
            "import endpoints",
            "",
            "def foodec(func):",
            "    def wrapper(*args, **kwargs):",
            "        return func(*args, **kwargs)",
            "    return wrapper",
            "",
            "class _BaseController(endpoints.Controller):",
            "    @foodec",
            "    def POST(self, **kwargs):",
            "        return 1",
            "",
            "class Default(_BaseController):",
            "    pass",
            "",
        ])
        rs = self.create_reflect(controller_prefix)
        for count, endpoint in enumerate(rs, 1):
            self.assertEqual("foodec", endpoint.decorators["POST"][0].name)
        self.assertEqual(1, count)

    def test_docblock(self):
        controller_prefix = "docblock"
        testdata.create_module(controller_prefix, [
            "import endpoints",
            "class Foo(endpoints.Controller):",
            "    '''this is a multiline docblock",
            "",
            "    this means it has...",
            "    ",
            "    multiple lines",
            "    '''",
            "    def GET(*args, **kwargs): pass",
            "",
        ])

        rs = self.create_reflect(controller_prefix)
        for endpoint in rs:
            self.assertTrue("\n" in endpoint.desc)

    def test_method_docblock(self):
        controller_prefix = "mdoc"
        testdata.create_module(controller_prefix, [
            "import endpoints",
            "class Foo(endpoints.Controller):",
            "    '''controller docblock'''",
            "    def GET(*args, **kwargs):",
            "        '''method docblock'''",
            "        pass",
            "",
        ])

        rs = self.create_reflect(controller_prefix)
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_method_docblock_bad_decorator(self):
        tmpdir = testdata.create_dir("reflectdoc2")
        controller_prefix = "mdoc2"
        testdata.create_module(controller_prefix, [
            "import endpoints",
            "",
            "def bad_dec(func):",
            "    def wrapper(*args, **kwargs):",
            "        return func(*args, **kwargs)",
            "    return wrapper",
            "",
            "class Foo(endpoints.Controller):",
            "    '''controller docblock'''",
            "    @bad_dec",
            "    def GET(*args, **kwargs):",
            "        '''method docblock'''",
            "        pass",
            "",
            "    def POST(*args, **kwargs):",
            "        '''should not return this docblock'''",
            "        pass",
            "",
        ])

        rs = self.create_reflect(controller_prefix)
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_decorators(self):
        controller_prefix = "controller_reflect"
        testdata.create_module(controller_prefix, [
            "import endpoints",
            "from endpoints.decorators import param",
            "",
            "def dec_func(f):",
            "    def wrapped(*args, **kwargs):",
            "        return f(*args, **kwargs)",
            "    return wrapped",
            "",
            "class dec_cls(object):",
            "    def __init__(self, func):",
            "        self.func = func",
            "    def __call__(*args, **kwargs):",
            "        return f(*args, **kwargs)",
            "",
            "class Foo(endpoints.Controller):",
            "    @dec_func",
            "    def GET(*args, **kwargs): pass",
            "    @dec_cls",
            "    @param('foo', default=1, type=int)",
            "    @param('bar', type=bool, required=False)",
            "    @param('che_empty', type=dict, default={})",
            "    @param('che_full', type=dict, default={'key': 'val', 'key2': 2.0})",
            "    @param('baz_empty', type=list, default=[])",
            "    @param('baz_full', type=list, default=['val', False, 1])",
            "    @param('d')",
            "    def POST(*args, **kwargs): pass",
            ""
        ])

        rs = self.create_reflect(controller_prefix)
        l = list(rs.controllers)
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for p in ['d']:
            self.assertTrue(params[p]['required'])

        for p in ['foo', 'bar', 'che_empty', 'che_full', 'baz_empty', 'baz_full']:
            self.assertFalse(params[p]['required'])

        self.assertEqual(1, len(l))
        self.assertEqual('/foo', r.uri)
        self.assertSetEqual(set(['GET', 'POST', 'OPTIONS']), set(r.methods.keys()))

    def test_decorators_param_help(self):
        controller_prefix = "dec_param_help"
        testdata.create_module(controller_prefix, [
            "import endpoints",
            "from endpoints.decorators import param",
            "class Default(endpoints.Controller):",
            "    @param('baz_full', type=list, default=['val', False, 1], help='baz_full')",
            "    @param('d', help='d')",
            "    def POST(*args, **kwargs): pass",
            ""
        ])

        rs = self.create_reflect(controller_prefix)
        l = list(rs.controllers)
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for k, v in params.items():
            self.assertEqual(k, v['options']['help'])


class ReflectControllerTest(TestCase):
    def test_method_required_path_args(self):
        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param('one')",
            "    def POST(self, *args, **kwargs): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual([0], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param('one')",
            "    def POST(self, zero, one): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual(["zero"], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param(1, default=1)",
            "    def POST(self, *args): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual([0], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param(1, default=1)",
            "    def POST(self, zero, *args): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual(["zero"], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0)",
            "    @param(1, default=1)",
            "    def POST(self, zero, one): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual(["zero"], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0, default=0)",
            "    @param(1, default=1)",
            "    def POST(self, zero, one): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual([], r)

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def POST(self, one, two=2, three=3): pass",
        ])
        rm = ReflectMethod("POST", mp.module.Foo.POST, ReflectController(mp, mp.module.Foo))
        r = rm.required_path_args
        self.assertEqual(1, len(r))

    def test__get_methods_info(self):
        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Bar(Controller):",
            "    @version('v1')",
            "    def GET_v1(self, **kwargs): pass",
            "",
            "    @version('v2')",
            "    def GET_v2(self, *args): pass",
            ""
            "    def POST(self, *args, **kwargs): pass",
        ])

        rc = ReflectController(mp, mp.module.Bar)
        r = rc._get_methods_info()
        self.assertEqual(2, len(r["GET"]))
        self.assertEqual(1, len(r["POST"]))

    def test_get_info(self):
        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def POST(self, one, two=2, three=3): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertFalse(r["POST"]["POST"]["positionals"])
        self.assertFalse(r["POST"]["POST"]["keywords"])
        self.assertEqual(3, len(r["POST"]["POST"]["params"]))
        self.assertEqual(3, r["POST"]["POST"]["params"][2]["default"])
        self.assertTrue(r["POST"]["POST"]["params"][0]["required"])

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    @param(0, default=1)",
            "    @param(1)",
            "    @param('che')",
            "    def POST(self, zero, one, che): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertEqual(3, len(r["POST"]["POST"]["params"]))
        self.assertEqual(3, len(r["POST"]["POST"]["decorators"]))

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def GET(self, *args, **kwargs): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertTrue(r["GET"]["GET"]["positionals"])
        self.assertTrue(r["GET"]["GET"]["keywords"])

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def GET(self): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertFalse(r["GET"]["GET"]["positionals"])
        self.assertFalse(r["GET"]["GET"]["keywords"])

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def GET(self, **kwargs): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertFalse(r["GET"]["GET"]["positionals"])
        self.assertTrue(r["GET"]["GET"]["keywords"])

        mp = testdata.create_module(contents=[
            "from endpoints import param, version, Controller",
            "class Foo(Controller):",
            "    def GET(self, *args): pass",
        ])
        rc = ReflectController(mp, mp.module.Foo)
        r = rc.get_info()
        self.assertTrue(r["GET"]["GET"]["positionals"])
        self.assertFalse(r["GET"]["GET"]["keywords"])

        # TODO this is a valid py3 method declarations:
        # def foo(*args, bar, che): pass

#         mp = testdata.create_module(controller_prefix, [
#             "import endpoints",
#             "from endpoints.decorators import param, version",
#             "class Bar(endpoints.Controller):",
#             "    @param('foo', default=1, type=int)",
#             "    @version('v1')",
#             "    def GET_v1(self, **kwargs): pass",
#             "",
#             "    @version('v2')",
#             "    def GET_v2(self, *args): pass",
#             ""
#             "    @version('v3')",
#             "    def GET_v3(self): pass",
#             ""
#             "    @param(0, default=1)",
#             "    @param('che')",
#             "    @version('v1')",
#             "    def POST_v1(self, *args, **kwargs): pass",
#             "",
#             "    @param(0, default=1)",
#             "    @param(1)",
#             "    @param('che')",
#             "    @version('v2')",
#             "    def POST_v2(self, zero, one, che): pass",
#         ])
# 
#         rc = ReflectController(controller_prefix, mp.module.Bar)
#         rc._get_info()

    def test_multi_methods(self):
        controller_prefix = "multi_methods"
        mp = testdata.create_module(controller_prefix, [
            "import endpoints",
            "from endpoints.decorators import param, version",
            "class Bar(endpoints.Controller):",
            "    @param('foo', default=1, type=int)",
            "    @param('bar', type=bool, required=False)",
            "    @version('v1')",
            "    def GET_version1(self): pass",
            "",
            "    @version('v2')",
            "    def GET_version2(self): pass",
            ""
        ])

        rc = ReflectController(controller_prefix, mp.module.Bar)
        self.assertEqual(2, len(rc.methods["GET"]))

        for rm in rc.methods["GET"]:
            self.assertTrue(rm.version in ["v1", "v2"])

    def test_metavar(self):
        # https://github.com/firstopinion/endpoints/issues/58
        controller_prefix = "metavar_rct"
        mp = testdata.create_module(controller_prefix, [
            "import endpoints",
            "from endpoints.decorators import param, version",
            "class Bar(endpoints.Controller):",
            "    @param(0, metavar='bar')",
            "    @param(1, metavar='che')",
            "    def GET(self, bar, che): pass",
            "",
        ])

        rc = ReflectController(controller_prefix, mp.module.Bar)

        for rm in rc.methods["GET"]:
            for name, pr in rm.params.items():
                self.assertTrue("metavar" in pr["options"])


class ReflectModuleTest(TestCase):
    def test_mixed_modules_packages(self):
        """make sure a package with modules and other packages will resolve correctly"""
        controller_prefix = "mmp"
        r = testdata.create_modules({
            "": [
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ],
            "foo": [
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ],
            "foo.bar": [
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ],
            "che": [
                "from endpoints import Controller",
                "class Default(Controller): pass",
            ],
        }, prefix=controller_prefix)

        r = ReflectModule(controller_prefix)
        self.assertEqual(set(['mmp.foo', 'mmp', 'mmp.foo.bar', 'mmp.che']), r.module_names)

        # make sure just a file will resolve correctly
        controller_prefix = "mmp2"
        testdata.create_module(controller_prefix, os.linesep.join([
            "from endpoints import Controller",
            "class Bar(Controller): pass",
        ]))
        r = ReflectModule(controller_prefix)
        self.assertEqual(set(['mmp2']), r.module_names)

    def test_routing_module(self):
        controller_prefix = "routing_module"
        contents = [
            "from endpoints import Controller",
            "class Bar(Controller):",
            "    def GET(*args, **kwargs): pass"
        ]
        testdata.create_module("{}.foo".format(controller_prefix), contents=contents)

        r = ReflectModule(controller_prefix)
        self.assertTrue(controller_prefix in r.module_names)
        self.assertEqual(2, len(r.module_names))

    def test_routing_package(self):
        controller_prefix = "routepack"
        contents = [
            "from endpoints import Controller",
            "",
            "class Default(Controller):",
            "    def GET(self): pass",
            "",
        ]
        f = testdata.create_package(controller_prefix, contents=contents)

        r = ReflectModule(controller_prefix)
        self.assertTrue(controller_prefix in r.module_names)
        self.assertEqual(1, len(r.module_names))

    def test_controllers(self):
        controller_prefix = "get_controllers"
        d = {
            controller_prefix: [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.default".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.foo".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                "",
                "class Bar(Controller):",
                "    def GET(*args, **kwargs): pass",
                "    def POST(*args, **kwargs): pass",
                ""
            ],
            "{}.foo.baz".format(controller_prefix): [
                "from endpoints import Controller",
                "class Default(Controller):",
                "    def GET(*args, **kwargs): pass",
                "",
                "class Che(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
            "{}.foo.boom".format(controller_prefix): [
                "from endpoints import Controller",
                "",
                "class Bang(Controller):",
                "    def GET(*args, **kwargs): pass",
                ""
            ],
        }
        r = testdata.create_modules(d)
        s = set(d.keys())


        r = ReflectModule(controller_prefix)
        controllers = r.module_names
        self.assertEqual(s, controllers)

        # just making sure it always returns the same list
        controllers = r.module_names
        self.assertEqual(s, controllers)

