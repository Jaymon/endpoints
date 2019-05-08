# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import sys
import importlib
import inspect
import re
import fnmatch
import ast
import collections
#import keyword
from .compat.imports import builtins
import pkgutil

from .decorators import _property, version, param


class ReflectDecorator(object):
    """The information of each individual decorator on a given ReflectMethod will
    be wrapped in this class"""

    @_property
    def parents(self):
        ret = []
        decor = self.decorator
        if inspect.isclass(decor):
            parents = inspect.getmro(decor)
            ret = parents[1:]
        return ret

    def __init__(self, name, args, kwargs, decorator):
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.decorator = decorator

    def contains(self, obj):
        ret = obj == self.decorator
        if not ret:
            for parent in self.parents:
                if parent == obj:
                    ret = True
                    break

        return ret

    def __contains__(self, obj):
        return self.contains(obj)


class ReflectMethod(object):
    """This encompasses the http verbs like POST and GET"""

    @_property
    def version(self):
        ret = ""
        for decor in self.decorators:
            if version in decor:
                ret = list(filter(None, decor.args))[0]
                break
        return ret

    @property
    def headers(self):
        headers = {}
        version = self.version
        if version:
            headers['Accept'] = "{};version={}".format(self.controller.content_type, version)
        return headers

    @_property
    def name(self):
        """return the method name (GET, POST)"""
        bits = self.method_name.split("_", 2)
        return bits[0]

    @_property
    def decorators(self):
        decorators = self.controller.decorators
        return decorators.get(self.method_name, [])

    @_property
    def desc(self):
        """return the description of this endpoint"""
        doc = None
        def visit_FunctionDef(node):
            """ https://docs.python.org/2/library/ast.html#ast.NodeVisitor.visit """
            if node.name != self.method_name:
                return

            doc = ast.get_docstring(node)
            raise StopIteration(doc if doc else "")

        target = self.controller.controller_class
        try:
            node_iter = ast.NodeVisitor()
            node_iter.visit_FunctionDef = visit_FunctionDef
            node_iter.visit(ast.parse(inspect.getsource(target)))

        except StopIteration as e:
            doc = str(e)

        if not doc: doc = ""
        return doc

    @_property
    def params(self):
        """return information about the params that the given http option takes"""
        ret = {}
        for rd in self.decorators:
            args = rd.args
            kwargs = rd.kwargs
            if param in rd:
                is_required =  kwargs.get('required', 'default' not in kwargs)
                ret[args[0]] = {'required': is_required, 'other_names': args[1:], 'options': kwargs}

        return ret

    def __init__(self, method_name, method, controller):
        self.method_name = method_name
        self.method = method
        self.controller = controller


class ReflectController(object):
    """This will encompass an entire Controller and have information on all the http
    methods (eg, GET and POST)"""

    method_class = ReflectMethod

    decorator_class = ReflectDecorator

    @_property
    def decorators(self):
        """Get all the decorators of all the option methods in the class

        http://stackoverflow.com/questions/5910703/ specifically, I used this
        answer http://stackoverflow.com/a/9580006
        """
        res = collections.defaultdict(list)
        mmap = {}

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
                ret = getattr(builtins, na.id, None)
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

                    d = {
                        "name": name,
                        "args": args,
                        "kwargs": kwargs
                    }
                    m = self.module
                    decor = getattr(m, name, None)
                    if decor:
                        d["decorator"] = decor

                    #res[node.name].append((name, args, kwargs))
                    res[node.name].append(self.decorator_class(**d))

        node_iter = ast.NodeVisitor()
        node_iter.visit_FunctionDef = visit_FunctionDef
        for target_cls in inspect.getmro(self.controller_class):
            if target_cls == object: break
            node_iter.visit(ast.parse(inspect.getsource(target_cls)))

        return res

    @_property
    def class_name(self):
        return self.controller_class.__name__

    @_property
    def module_name(self):
        return self.controller_class.__module__

    @_property
    def module(self):
        return ReflectModule(self.module_name).module

    @_property
    def bits(self):
        bits = self.module_name.replace(self.controller_prefix, '', 1).lower()
        bits = list(filter(None, bits.split(".")))

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
        if not doc: doc = ''
        return doc

    @_property
    def methods(self):
        """
        return the supported http method options that this class supports
        return what http method options this endpoint supports (eg, POST, GET)

        http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html

        :returns: dict, each http method (eg, GET, POST) will have a key with the value
            being every method from the controller that can satisfy the http method
        """
        ret = {}
        method_regex = re.compile(r"^[A-Z][A-Z0-9]+(_|$)")
        controller_methods = inspect.getmembers(self.controller_class)
        for controller_method_name, controller_method in controller_methods:
            if controller_method_name.startswith('_'): continue

            if method_regex.match(controller_method_name):
                method = self.method_class(
                    controller_method_name,
                    controller_method,
                    controller=self
                )
                ret.setdefault(method.name, [])
                ret[method.name].append(method)

        return ret

    def __init__(self, controller_prefix, controller_class):
        """reflect a controller

        :param controller_prefix: the base controller prefix that this controller
            class resides in, this is needed so the path can be figured out, basically
            if the controller prefix is foo.controllers and this controller is located
            in the module foo.controllers.bar.che then the module path can be worked
            out to bar/che using controller_prefix
        :param controller_class: type, the actual python class
        """
        self.controller_prefix = controller_prefix
        self.controller_class = controller_class
        self.content_type = controller_class.content_type

    def is_private(self):
        """return True if this endpoint is considered private"""
        return self.class_name.startswith('_') or getattr(self.controller_class, 'private', False)


class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    controller_class = ReflectController

    @property
    def controllers(self):
        # avoid circular dependencies
        from .call import Controller

        for controller_prefix in self.controller_prefixes:
            for rm in ReflectModule(controller_prefix):
                for controller_class_name, controller_class in rm.classes:
                    if not issubclass(controller_class, Controller): continue
                    if controller_class == Controller: continue

                    controller = self.create_controller(
                        controller_prefix=controller_prefix,
                        controller_class=controller_class,
                    )

                    # filter out controllers that can't handle any requests
                    if controller.methods:
                        yield controller

    def __init__(self, controller_prefixes):
        self.controller_prefixes = controller_prefixes

    def create_controller(self, *args, **kwargs):
        return self.controller_class(*args, **kwargs)

    def __iter__(self):
        return self.controllers


class ReflectModule(object):
    @property
    def path(self):
        return self.find_module_import_path()

    @property
    def module(self):
        """return the actual python module found at self.module_name"""
        return self.get_module(self.module_name)

    @property
    def classes(self):
        """yields all the (class_name, class_type) that is found in only this
        module (not submodules)

        this filters our private classes (classes that start with _)

        :returns: a generator of tuples (class_name, class_type)
        """
        module = self.module
        classes = inspect.getmembers(module, inspect.isclass)
        for class_name, class_type in classes:
            if class_name.startswith('_'): continue
            yield class_name, class_type

    @property
    def module_names(self):
        """return all the module names that this module encompasses

        :returns: set, a set of string module names
        """
        module = self.get_module(self.module_name)

        if hasattr(module, "__path__"):
            # path attr exists so this is a package
            module_names = self.find_module_names(module.__path__[0], self.module_name)

        else:
            # we have a lonely .py file
            module_names = set([self.module_name])

        return module_names

    def __init__(self, module_name):
        self.module_name = module_name

    def __iter__(self):
        """This will iterate through this module and all its submodules

        :returns: a generator that yields ReflectModule instances
        """
        for module_name in self.module_names:
            yield type(self)(module_name)

    def find_module_names(self, path, prefix):
        """recursive method that will find all the submodules of the given module
        at prefix with path

        :returns: list, a list of submodule names under prefix.path
        """

        module_names = set([prefix])

        # https://docs.python.org/2/library/pkgutil.html#pkgutil.iter_modules
        for module_info in pkgutil.iter_modules([path]):
            # we want to ignore any "private" modules
            if module_info[1].startswith('_'): continue

            module_prefix = ".".join([prefix, module_info[1]])
            if module_info[2]:
                # module is a package
                submodule_names = self.find_module_names(os.path.join(path, module_info[1]), module_prefix)
                module_names.update(submodule_names)
            else:
                module_names.add(module_prefix)

        return module_names

    def get_module(self, module_name):
        """load a module by name"""
        return importlib.import_module(module_name)

    def find_module_path(self):
        """find where the master module is located"""
        master_modname = self.module_name.split(".", 1)[0]
        master_module = sys.modules[master_modname]
        #return os.path.dirname(os.path.realpath(os.path.join(inspect.getsourcefile(endpoints), "..")))
        path = os.path.dirname(inspect.getsourcefile(master_module))
        return path

    def find_module_import_path(self):
        """find and return the importable path for endpoints"""
        module_path = self.find_module_path()
        path = os.path.dirname(module_path)
        return path
        #path = os.path.dirname(os.path.realpath(os.path.join(module_path, "..")))
        #return os.path.dirname(os.path.realpath(os.path.join(inspect.getsourcefile(endpoints), "..")))

