import os
import sys
import importlib
import inspect
import re
import fnmatch
import ast
import collections
#import keyword
import __builtin__

from .core import Controller
from .call import Router
from .decorators import _property


class ReflectMethod(object):
    """This encompasses the http verbs like POST and GET"""

    @_property
    def version(self):
        bits = self.controller_method_name.split("_", 2)
        return bits[1] if len(bits) > 1 else None

    @property
    def headers(self):
        headers = {}
        version = self.version
        if version:
            headers['Accept'] = "{};version={}".format(self.content_type, version)
        return headers

    @_property
    def name(self):
        """return the method name (GET, POST)"""
        bits = self.controller_method_name.split("_", 2)
        return bits[0]

    @_property
    def decorators(self):
        decorators = self.endpoint.decorators
        return decorators.get(self.controller_method_name, [])

    @_property
    def desc(self):
        """return the description of this endpoint"""
        doc = None
        if self.endpoint:
            def visit_FunctionDef(node):
                """ https://docs.python.org/2/library/ast.html#ast.NodeVisitor.visit """
                if node.name != self.controller_method_name:
                    return

                doc = ast.get_docstring(node)
                raise StopIteration(doc if doc else u"")

            target = self.endpoint.controller_class
            try:
                node_iter = ast.NodeVisitor()
                node_iter.visit_FunctionDef = visit_FunctionDef
                node_iter.visit(ast.parse(inspect.getsource(target)))

            except StopIteration as e:
                doc = str(e)

        else:
            doc = inspect.getdoc(self.controller_method)

        if not doc: doc = u""
        return doc

    @_property
    def params(self):
        """return information about the params that the given http option takes"""
        ret = {}
        for name, args, kwargs in self.decorators:
            if name == 'param':
                is_required =  kwargs.get('required', 'default' not in kwargs)
                ret[args[0]] = {'required': is_required, 'other_names': args[1:], 'options': kwargs}

            if name == 'require_params':
                for a in args:
                    ret[a] = {'required': True, 'other_names': [], 'options': {}}

        return ret

    def __init__(self, controller_method_name, controller_method, *args, **kwargs):
        self.controller_method_name = controller_method_name
        self.controller_method = controller_method
        self.endpoint = kwargs.get("endpoint", None)
        self.content_type = kwargs.get("content_type", None)


class ReflectEndpoint(object):
    """This will encompass an entire Controller and have information on all the verbs
    (eg, GET and POST)"""

    method_class = ReflectMethod

    @_property
    def decorators(self):
        """Get all the decorators of all the option methods in the class

        http://stackoverflow.com/questions/5910703/ specifically, I used this
        answer http://stackoverflow.com/a/9580006
        """
        res = collections.defaultdict(list)
        mmap = {}
        target = self.controller_class

        def get_val(na, default=None):
            ret = None
            if isinstance(na, ast.Num):
                repr_n = repr(na.n)
                val = na.n
                vtype = float if '.' in repr_n else int
                ret = vtype(val)

            elif isinstance(na, ast.Str):
                ret = str(na.s)

            elif isinstance(na, ast.Name):
                # http://stackoverflow.com/questions/12700893/
                ret = getattr(__builtin__, na.id, None)
                if not ret:
                    ret = na.id
                    if ret == 'True':
                        ret = True
                    elif ret == 'False':
                        ret = False

            elif isinstance(na, ast.Dict):
                if na.keys:
                    ret = {get_val(na_[0]): get_val(na_[1]) for na_ in zip(na.keys, na.values)}
                else:
                    ret = {}

            elif isinstance(na, (ast.List, ast.Tuple)):
                if na.elts:
                    ret = [get_val(na_) for na_ in na.elts]
                else:
                    ret = []

                if isinstance(na, ast.Tuple):
                    ret = tuple(ret)

            else:
                ret = default

            return ret


        def is_super(childnode, parentnode):
            """returns true if child node has a super() call to parent node"""
            ret = False
            #pout.b(node.name)
            #pout.v(node)
#             for n in node.body:
#                 if isinstance(n, ast.Expr):
#                     pout.v(n.value.func, n.value.func.ctx, n.value.func.value)
            for n in childnode.body:
                if not isinstance(n, ast.Expr): continue

                try:
                    func = n.value.func
                    func_name = func.attr
                    if func_name == parentnode.name:
                        ret = isinstance(func.value, ast.Call)
                        break

                except AttributeError as e:
                    ret = False

            return ret


        def visit_FunctionDef(node):
            """ https://docs.python.org/2/library/ast.html#ast.NodeVisitor.visit """

            add_decs = True
            if node.name in res:
                add_decs = is_super(mmap[node.name], node)

            mmap[node.name] = node

            if add_decs:
                for n in node.decorator_list:
                    d = {}
                    name = ''
                    args = []
                    kwargs = {}
                    if isinstance(n, ast.Call):
                        name = n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                        for an in n.args:
                            args.append(get_val(an))

                        for an in n.keywords:
                            kwargs[an.arg] = get_val(an.value)

                    else:
                        name = n.attr if isinstance(n, ast.Attribute) else n.id

                    res[node.name].append((name, args, kwargs))


        node_iter = ast.NodeVisitor()
        node_iter.visit_FunctionDef = visit_FunctionDef
        for target_cls in inspect.getmro(target):
            if target_cls == Controller: break
            node_iter.visit(ast.parse(inspect.getsource(target_cls)))

        return res

    @_property
    def class_name(self):
        return self.controller_class.__name__

    @_property
    def module_name(self):
        return self.controller_module.__name__

    @_property
    def bits(self):
        bits = self.module_name.replace(self.controller_prefix, '', 1).lower()
        bits = filter(None, bits.split("."))

        class_name = self.class_name.lower()
        if class_name != "default":
            bits.append(class_name)

        return bits

    @_property
    def uri(self):
        return "/" + "/".join(self.bits)

    @_property
    def desc(self):
        """return the description of this endpoint"""
        doc = inspect.getdoc(self.controller_class)
        if not doc: doc = u''
        return doc

    @_property
    def methods(self):
        """
        return the supported http method options that this class supports
        return what http method options this endpoint supports (eg, POST, GET)

        link -- http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html

        return -- set -- the http methods (eg, ['GET', 'POST']) this endpoint supports
        """
        ret = {}
        method_regex = re.compile(ur"^[A-Z][A-Z0-9]+(_|$)")
        # won't pick up class decorators
        #methods = inspect.getmembers(v, inspect.ismethod)
        # won't pick up class decorators that haven't been functools wrapped
        #methods = inspect.getmembers(v, inspect.isroutine)
        controller_methods = inspect.getmembers(self.controller_class)
        for controller_method_name, controller_method in controller_methods:
            if controller_method_name.startswith(u'_'): continue

            if method_regex.match(controller_method_name):
                method = self.method_class(
                    controller_method_name,
                    controller_method,
                    content_type=self.content_type,
                    endpoint=self
                )
                ret.setdefault(method.name, [])
                ret[method.name].append(method)

        return ret

    def __init__(self, controller_prefix, controller_module, controller_class, **kwargs):
        self.controller_prefix = controller_prefix
        self.controller_module = controller_module
        self.controller_class = controller_class
        self.content_type = kwargs.get('content_type', None)

    def is_private(self):
        """return True if this endpoint is considered private"""
        return self.class_name.startswith('_') or getattr(self.controller_class, 'private', False)


class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    controller_prefix = ''

    endpoint_class = ReflectEndpoint

    def __init__(self, controller_prefix, content_type='*/*'):
        self.controller_prefix = controller_prefix
        self.content_type = content_type
        if not controller_prefix:
            raise ValueError("controller_prefix was empty")

    def get_controller_modules(self):
        """
        get all the controller modules

        this will find any valid controller modules and yield them

        return -- generator of tuples -- module, dict
        """
        router = Router(self.controller_prefix)
        controller_prefix = self.controller_prefix

        # NOTE -- this method previously tried to clean up after itself by deleting
        # any new modules that were added, but that leads to really subtle errors
        # that are really difficult to track down and fix and I can't guarrantee we've
        # caught them all, so my solution is to no longer try and clean up, this
        # method imports all the modules, live with it

        #new_modules = set()
        #orig_modules = set(sys.modules.keys())

        for controller_name in router.controllers:
            if controller_name.startswith(u'_'): continue

            controller_module = importlib.import_module(controller_name)

            # what new modules were added?
            #snapshot_modules = set(sys.modules.keys())
            #new_modules.update(snapshot_modules.difference(orig_modules))

            yield controller_module

        # leave no trace, if the module wasn't there previously, get rid of it now
        #for module_name in new_modules:
        #    sys.modules.pop(module_name, None)

    def get_controller_classes(self, controller_module):
        """
        get all the endpoints in this controller

        return -- list -- a list of dicts with information about each endpoint in the controller
        """
        classes = inspect.getmembers(controller_module, inspect.isclass)
        for controller_class_name, controller_class in classes:
            if not issubclass(controller_class, Controller): continue
            if controller_class_name.startswith(u'_'): continue

            endpoint = self.create_endpoint(
                controller_prefix=self.controller_prefix,
                controller_module=controller_module,
                controller_class=controller_class,
                content_type=self.content_type
            )

            # filter out base classes like endpoints.Controller
            if endpoint.methods:
                yield endpoint

    def create_endpoint(self, *args, **kwargs):
        return self.endpoint_class(*args, **kwargs)

    def get_endpoints(self):
        """
        go through all the controllers in controller prefix and return them

        return -- list -- a list of endpoints found
        """

        for controller_module in self.get_controller_modules():
            for endpoint in self.get_controller_classes(controller_module):
                yield endpoint

    def __iter__(self):
        return self.get_endpoints()

