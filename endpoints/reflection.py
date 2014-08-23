import os
import sys
import importlib
import inspect
import re
import fnmatch
import ast
#import keyword
import __builtin__

from .core import Controller
from .call import get_controllers
from .decorators import _property


class ReflectEndpoint(object):
    @_property
    def post_params(self):
        """return the POST params for this endpoint"""
        return self.params('POST')
        #for m in (m[1] for m in inspect.getmembers(self.endpoint_class) if m[0] == 'POST'):

    @_property
    def get_params(self):
        """return the GET params for this endpoint"""
        return self.params('GET')

    @_property
    def decorators(self):
        """Get all the decorators of all the option methods in the class

        http://stackoverflow.com/questions/5910703/ specifically, I used this
        answer http://stackoverflow.com/a/9580006
        """
        res = {}
        target = self.endpoint_class

        def get_val(na):
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

            elif isinstance(na, ast.List):
                if na.elts:
                    ret = [get_val(na_) for na_ in na.elts]
                else:
                    ret = []

            else:
                raise ValueError("unsupported val")

            return ret

        def visit_FunctionDef(node):
            """ https://docs.python.org/2/library/ast.html#ast.NodeVisitor.visit """
            res[node.name] = []
            for n in node.decorator_list:
                d = {}
                name = ''
                args = []
                kwargs = {}
                if isinstance(n, ast.Call):
                    name = n.func.id
                    for an in n.args:
                        args.append(get_val(an))

                    for an in n.keywords:
                        kwargs[an.arg] = get_val(an.value)

                else:
                    name = n.id

                res[node.name].append((name, args, kwargs))

        node_iter = ast.NodeVisitor()
        node_iter.visit_FunctionDef = visit_FunctionDef
        node_iter.visit(ast.parse(inspect.getsource(target)))

        return res

    @_property
    def class_name(self):
        return self.endpoint_class.__name__

    @_property
    def module_name(self):
        return self.endpoint_module.__name__

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
        doc = inspect.getdoc(self.endpoint_class)
        if not doc: doc = u''
        return doc

    @_property
    def options(self):
        """return what http method options this endpoint supports (eg, POST, GET)"""
        return self.endpoint_class.get_methods()

    def __init__(self, controller_prefix, endpoint_module, endpoint_class, **kwargs):
        self.controller_prefix = controller_prefix
        self.endpoint_module = endpoint_module
        self.endpoint_class = endpoint_class

    def params(self, option):
        """return information about the params that the given http option takes"""
        option = option.upper()
        ret = {}
        decs = self.decorators
        if option in decs:
            for name, args, kwargs in decs[option]:
                if name == 'param':
                    is_required =  kwargs.get('required', 'default' not in kwargs)
                    ret[args[0]] = {'required': is_required, 'other_names': args[1:], 'options': kwargs}

                if name == 'require_params':
                    for a in args:
                        ret[a] = {'required': True, 'other_names': [], 'options': {}}

        return ret


    def is_private(self):
        """return True if this endpoint is considered private"""
        return self.class_name.startswith(u'_') or getattr(self.endpoint_class, 'private', False)


class VersionReflectEndpoint(ReflectEndpoint):
    @_property
    def uri(self):
        return "/" + "/".join(self.bits[1:])

    @_property
    def version(self):
        return self.bits[0]

    @_property
    def headers(self):
        headers = {}
        headers['Accept'] = "{};version={}".format(self.content_type, self.version)
        return headers

    def __init__(self, *args, **kwargs):
        self.content_type = kwargs.pop('content_type')
        super(VersionReflectEndpoint, self).__init__(*args, **kwargs)


class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    controller_prefix = u''

    info_class = ReflectEndpoint

    def __init__(self, controller_prefix):
        self.controller_prefix = controller_prefix
        if not controller_prefix:
            raise ValueError("controller_prefix was empty")

    def normalize_endpoint(self, *args, **kwargs):
        """
        handy for adding any args, or kwargs accumulated through all the calls to the endpoint

        endpoint -- dict -- the endpoint information dict
        """
        return self.info_class(
            self.controller_prefix,
            *args,
            **kwargs
        )

    def get_controller_modules(self):
        """
        get all the controller modules

        this will find any valid controller modules and yield them

        return -- generator of tuples -- module, dict
        """
        controller_prefix = self.controller_prefix
        for controller_name in get_controllers(self.controller_prefix):
            if controller_name.startswith(u'_'): continue

            remove = controller_name in sys.modules

            controller_module = importlib.import_module(controller_name)
            yield controller_module

            if remove:
                sys.modules.pop(controller_name, None)

    def get_controller_classes(self, controller_module):
        """
        get all the endpoints in this controller

        return -- list -- a list of dicts with information about each endpoint in the controller
        """
        classes = inspect.getmembers(controller_module, inspect.isclass)
        for class_name, v in classes:
            if not issubclass(v, Controller): continue
            if class_name.startswith(u'_'): continue

            info = self.normalize_endpoint(controller_module, v)

            # filter out base classes like endpoints.Controller
            if info.options:
                yield info

    def get_endpoints(self):
        """
        go through all the controllers in controller prefix and return them

        return -- list -- a list of endpoints found
        """

        for controller_module in self.get_controller_modules():
            for endpoint_info in self.get_controller_classes(controller_module):
                yield endpoint_info


class VersionReflect(Reflect):
    """
    same as Reflect, but for VersionCall
    """
    info_class = VersionReflectEndpoint

    def __init__(self, controller_prefix, content_type='*/*'):
        self.content_type = content_type
        super(VersionReflect, self).__init__(controller_prefix)

    def normalize_endpoint(self, *args, **kwargs):
        """
        handy for adding any args, or kwargs accumulated through all the calls to the endpoint

        endpoint -- dict -- the endpoint information dict
        """
        return self.info_class(
            self.controller_prefix,
            content_type=self.content_type,
            *args,
            **kwargs
        )

