from . import TestCase, SkipTest
import os

import testdata

from endpoints import Controller, Reflect


class ReflectTest(TestCase):
    def test_decorators_inherit_2(self):
        """you have a parent class with POST method, the child also has a POST method,
        what do you do? What. Do. You. Do?"""
        prefix = "decinherit2"
        m = testdata.create_modules(
            {
                prefix: os.linesep.join([
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
                ]),
            }
        )

        rs = Reflect(prefix, 'application/json')
        l = list(rs.get_endpoints())
        r = l[0]
        self.assertEqual(1, len(r.decorators["POST"]))
        self.assertEqual(1, len(r.decorators["HEAD"]))
        self.assertEqual(3, len(r.decorators["GET"]))


    def test_decorator_inherit_1(self):
        """make sure that a child class that hasn't defined a METHOD inherits the
        METHOD method from its parent with decorators in tact"""
        prefix = "decinherit"
        tmpdir = testdata.create_dir(prefix)
        m = testdata.create_modules(
            {
                "foodecinherit": os.linesep.join([
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
                ]),
            },
            tmpdir=tmpdir
        )

        controller_prefix = "foodecinherit"
        rs = Reflect(controller_prefix, 'application/json')
        for count, endpoint in enumerate(rs, 1):
            self.assertEqual("foodec", endpoint.decorators["POST"][0][0])
        self.assertEqual(1, count)

    def test_get_methods(self):
        # this doesn't work right now, I've moved this functionality into Reflect
        # this method needs to be updated to work
        return
        class GetMethodsController(Controller):
            def POST(self): pass
            def GET(self): pass
            def ABSURD(self): pass
            def ignORED(self): pass

        options = GetMethodsController.get_methods()
        self.assertEqual(3, len(options))
        for o in ['ABSURD', 'GET', 'POST']:
            self.assertTrue(o in options)

    def test_docblock(self):
        tmpdir = testdata.create_dir("reflectdoc")
        testdata.create_modules(
            {
                "doc.block": os.linesep.join([
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
            },
            tmpdir=tmpdir
        )

        rs = Reflect("doc", 'application/json')
        for endpoint in rs:
            self.assertTrue("\n" in endpoint.desc)

    def test_method_docblock(self):
        tmpdir = testdata.create_dir("reflectdoc")
        testdata.create_modules(
            {
                "mdoc.mblock": os.linesep.join([
                    "import endpoints",
                    "class Foo(endpoints.Controller):",
                    "    '''controller docblock'''",
                    "    def GET(*args, **kwargs):",
                    "        '''method docblock'''",
                    "        pass",
                    "",
                ])
            },
            tmpdir=tmpdir
        )

        rs = Reflect("mdoc", 'application/json')
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_method_docblock_bad_decorator(self):
        tmpdir = testdata.create_dir("reflectdoc2")
        testdata.create_modules(
            {
                "mdoc2.mblock": os.linesep.join([
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
            },
            tmpdir=tmpdir
        )

        rs = Reflect("mdoc2", 'application/json')
        for endpoint in rs:
            desc = endpoint.methods['GET'][0].desc
            self.assertEqual("method docblock", desc)
 
    def test_get_versioned_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("versionreflecttest")
        testdata.create_modules(
            {
                "controller_vreflect.foo": os.linesep.join([
                    "import endpoints",
                    "from endpoints.decorators import param, require_params",
                    "class Bar(endpoints.Controller):",
                    "    @param('foo', default=1, type=int)",
                    "    @param('bar', type=bool, required=False)",
                    "    def GET(*args, **kwargs): pass",
                    "",
                    "    def GET_v2(*args, **kwargs): pass",
                    ""
                ]),
                "controller_vreflect.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def GET_v3(*args, **kwargs): pass",
                    ""
                ]),
            },
            tmpdir=tmpdir
        )

        rs = Reflect("controller_vreflect", 'application/json')
#         for endpoint in rs.get_endpoints():
#             for method_name, methods in endpoint.methods.items():
#                 for method in methods:
#                     pout.v(method.headers, method.version)
# 

        l = list(rs.get_endpoints())

        self.assertEqual(2, len(l))
        for d in l:
            self.assertEqual(1, len(d.methods))

        def get_match(endpoint_uri, l):
            ret = {}
            for d in l:
                if d.uri == endpoint_uri:
                    ret = d
            return ret

        d = get_match("/foo/bar", l)
        self.assertTrue(d)

        d = get_match("/che/baz", l)
        self.assertTrue(d)

    def test_decorators(self):
        testdata.create_modules({
            "controller_reflect": os.linesep.join([
                "import endpoints",
                "from endpoints.decorators import param, require_params",
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
                "    @require_params('a', 'b', 'c')",
                "    @param('d')",
                "    def POST(*args, **kwargs): pass",
                ""
            ])
        })

        rs = Reflect("controller_reflect")
        l = list(rs.get_endpoints())
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for p in ['a', 'b', 'c', 'd']:
            self.assertTrue(params[p]['required'])

        for p in ['foo', 'bar', 'che_empty', 'che_full', 'baz_empty', 'baz_full']:
            self.assertFalse(params[p]['required'])

        self.assertEqual(1, len(l))
        self.assertEqual(u'/foo', r.uri)
        self.assertSetEqual(set(['GET', 'POST']), set(r.methods.keys()))

    def test_decorators_param_help(self):
        testdata.create_modules({
            "dec_param_help.foo": os.linesep.join([
                "import endpoints",
                "from endpoints.decorators import param, require_params",
                "class Default(endpoints.Controller):",
                "    @param('baz_full', type=list, default=['val', False, 1], help='baz_full')",
                "    @param('d', help='d')",
                "    def POST(*args, **kwargs): pass",
                ""
            ])
        })

        rs = Reflect("dec_param_help")
        l = list(rs.get_endpoints())
        r = l[0]

        methods = r.methods
        params = methods['POST'][0].params
        for k, v in params.items():
            self.assertEqual(k, v['options']['help'])

    def test_get_endpoints(self):
        # putting the C back in CRUD
        tmpdir = testdata.create_dir("reflecttest")
        testdata.create_modules(
            {
                "controller_reflect_endpoints": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.foo": os.linesep.join([
                    "import endpoints",
                    "class Default(endpoints.Controller):",
                    "    def GET(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.che": os.linesep.join([
                    "from endpoints import Controller",
                    "class Baz(Controller):",
                    "    def POST(*args, **kwargs): pass",
                    ""
                ]),
                "controller_reflect_endpoints.che.bam": os.linesep.join([
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
                ])
            },
            tmpdir=tmpdir
        )

        r = Reflect("controller_reflect_endpoints")
        l = list(r.get_endpoints())
        self.assertEqual(5, len(l))

        def get_match(endpoint, l):
            for d in l:
                if d.uri == endpoint:
                    return d

        d = get_match("/che/bam/bah", l)
        self.assertSetEqual(set(["GET", "HEAD"]), set(d.methods.keys()))
        self.assertGreater(len(d.desc), 0)

        d = get_match("/", l)
        self.assertNotEqual(d, None)

        d = get_match("/foo", l)
        self.assertNotEqual(d, None)


