# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import time
import datetime
import importlib
import logging
import os
import sys
import fnmatch
import types
import traceback
import inspect
import pkgutil

from .utils import AcceptHeader
from .http import Response, Request
from .exception import CallError, Redirect, CallStop, AccessDenied, RouteError
from .decorators import _property


logger = logging.getLogger(__name__)


class Call(object):
    def __init__(self, req, res, rou):
        self.request = req
        self.response = res
        self.router = rou
        self.controller = None

    def create_controller(self):
        body = None
        req = self.request
        res = self.response
        rou = self.router
        con = None

        controller_info = {}
        try:
            controller_info = rou.find(req, res)

        except IOError as e:
            logger.warning(str(e), exc_info=True)
            raise CallError(
                408,
                "The client went away before the request body was retrieved."
            )

        except (ImportError, AttributeError, TypeError) as e:
            exc_info = sys.exc_info()
            logger.warning(str(e), exc_info=exc_info)
            raise CallError(
                404,
                "{} not found because of {} \"{}\" on {}:{}".format(
                    req.path,
                    exc_info[0].__name__,
                    str(e),
                    os.path.basename(exc_info[2].tb_frame.f_code.co_filename),
                    exc_info[2].tb_lineno
                )
            )

        else:
            con = controller_info['class_instance']

        return con

    def handle(self):
        body = None
        req = self.request
        res = self.response
        rou = self.router
        con = None

        try:
            con = self.create_controller()
            con.interface = self
            self.controller = con

#             logger.debug("handling request with {}.{}.{}".format(
#                 req.controller_info['module_name'],
#                 req.controller_info['class_name'],
#                 req.method, #req.controller_info['method_name']
#             ))

            con.handle() # this will manipulate self.response

        except Exception as e:
            # if anything gets to here we've messed up because we threw an error before
            # the controller's error handler could handle it :(
            self.handle_error(e) # this will manipulate self.response

        finally:
            if res.code == 204:
                res.headers.pop('Content-Type', None)
                res.body = None # just to be sure since body could've been ""

        return res

    def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        :returns: mixed, the body for the response
        """
        req = self.request
        res = self.response
        con = self.controller

        if isinstance(e, CallStop):
            logger.info(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            res.body = e.body

        elif isinstance(e, Redirect):
            logger.info(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            res.body = None

        elif isinstance(e, (AccessDenied, CallError)):
            logger.warning(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            res.body = e

        elif isinstance(e, NotImplementedError):
            logger.warning(str(e), exc_info=True)
            res.code = 501
            res.body = e

        elif isinstance(e, TypeError):
            e_msg = unicode(e)
            if e_msg.startswith(req.method) and 'argument' in e_msg:
                logger.debug(e_msg, exc_info=True)
                res.code = 404

            else:
                logger.exception(e)
                res.code = 500

            res.body = e

        else:
            logger.exception(e)
            res.code = 500
            res.body = e

        if con:
            con.handle_error(e, **kwargs)


class Router(object):
    """
    Where all the routing magic happens

    we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs

    GET /foo -> controller_prefix.version.foo.Default.get
    POST /foo/bar -> controller_prefix.version.foo.Bar.post
    GET /foo/bar/che -> controller_prefix.version.foo.Bar.get(che)
    POST /foo/bar/che?baz=foo -> controller_prefix.version.foo.Bar.post(che, baz=foo)
    """

    @property
    def controllers(self):
        """get all the modules in the controller_prefix

        returns -- set -- a set of string module names"""
        controller_prefix = self.controller_prefix
        _module_name_cache = self._module_name_cache
        if controller_prefix in _module_name_cache:
            return _module_name_cache[controller_prefix]

        module = self.get_module(controller_prefix)

        if hasattr(module, "__path__"):
            # path attr exists so this is a package
            modules = self.find_modules(module.__path__[0], controller_prefix)

        else:
            # we have a lonely .py file
            modules = set([controller_prefix])

        _module_name_cache.setdefault(controller_prefix, {})
        _module_name_cache[controller_prefix] = modules

        return modules

    def __init__(self, controller_prefix):
        if not controller_prefix:
            raise ValueError("controller prefix is empty")

        self.controller_prefix = controller_prefix
        self._module_name_cache = {}

    def find(self, req, res):
        ret = {}
        controller_path_args = []
        request_path_args = list(req.path_args)

        module_name, controller_method_args = self.get_module_name(request_path_args)
        controller_module_name = module_name
        controller_module = self.get_module(module_name)

        controller_class = None
        if controller_method_args:
            controller_class = self.get_class(
                controller_module,
                controller_method_args[0].capitalize()
            )

        if controller_class:
            controller_path_args.append(controller_method_args.pop(0))
            controller_class_name = controller_class.__name__

        else:
            controller_class_name = "Default"
            controller_class = self.get_class(controller_module, controller_class_name)

        if not controller_class:
            raise TypeError(
                "Could not find a valid module and Controller class for {}".format(
                    req.path
                )
            )

        ret['path'] = "/".join(controller_path_args)

        ret['module'] = controller_module
        ret['module_name'] = controller_module_name

        ret['class'] = controller_class
        ret['class_name'] = controller_class_name
        ret['class_instance'] = self.get_class_instance(req, res, controller_class)

        ret['method_args'] = controller_method_args
        ret['method_kwargs'] = req.kwargs
        #ret['method_name'] = self.get_method_name(req, controller_class)
        #ret['method'] = self.get_method(req, ret['class_instance'], ret['method_name'])

        req.controller_info = ret
        #pout.v(ret)
        return ret

    def get_class_instance(self, req, res, controller_class):
        instance = controller_class(req, res)
        instance.router = self
        return instance

    def get_method_name(self, req, controller_class):
        """
        perform any normalization of the controller's method

        return -- string -- the full method name to be used
        """
        method = req.method.upper()
        version = req.version(controller_class.content_type)
        if version:
            method += "_{}".format(version)

        return method

    def get_method(self, req, controller_instance, method_name):
        """using the controller_info retrieved from get_controller_info(), get the
        actual controller callback method that will be used to handle the request"""
        callback = None
        try:
            callback = getattr(controller_instance, method_name)

        except AttributeError as e:
            logger.warning(str(e), exc_info=True)
            raise CallError(405, "{} {} not supported".format(req.method, req.path))

        return callback

    def find_modules(self, path, prefix):
        """recursive method that will find all the submodules of the given module
        at prefix with path"""

        modules = set([prefix])

        # https://docs.python.org/2/library/pkgutil.html#pkgutil.iter_modules
        for module_info in pkgutil.iter_modules([path]):
            # we want to ignore any "private" modules
            if module_info[1].startswith('_'): continue

            module_prefix = ".".join([prefix, module_info[1]])
            if module_info[2]:
                # module is a package
                submodules = self.find_modules(os.path.join(path, module_info[1]), module_prefix)
                modules.update(submodules)
            else:
                modules.add(module_prefix)

        return modules

    def get_module_name(self, path_args):
        """returns the module_name and remaining path args.

        return -- tuple -- (module_name, path_args)"""
        controller_prefix = self.controller_prefix
        cset = self.controllers
        module_name = controller_prefix
        mod_name = module_name
        while path_args:
            mod_name += "." + path_args[0]
            if mod_name in cset:
                module_name = mod_name
                path_args.pop(0)
            else:
                break

        return module_name, path_args

    def get_module(self, module_name):
        """load a module by name"""
        return importlib.import_module(module_name)

    def get_class(self, module, class_name):
        """try and get the class_name from the module and make sure it is a valid
        controller"""
        # let's get the class
        class_object = getattr(module, class_name, None)
        if not class_object or not issubclass(class_object, Controller):
            class_object = None

        return class_object


class Controller(object):
    """
    this is the interface for a Controller sub class

    All your controllers MUST extend this base class, since it ensures a proper interface :)

    to activate a new endpoint, just add a module on your PYTHONPATH.controller_prefix that has a class
    that extends this class, and then defines at least one option method (like GET or POST), so if you
    wanted to create the endpoint /foo/bar (with controller_prefix che), you would just need to:

    ---------------------------------------------------------------------------
    # che/foo.py
    import endpoints

    class Bar(endpoints.Controller):
        def GET(self, *args, **kwargs):
            return "you just made a GET request to /foo/bar"
    ---------------------------------------------------------------------------

    as you support more methods, like POST and PUT, you can just add POST() and PUT()
    methods to your Bar class and Bar will support those http methods. Although you can
    request any method (a method is valid if it is all uppercase), here is a list of
    rfc approved http request methods:

    http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

    If you would like to create a base controller that other controllers will extend and don't
    want that controller to be picked up by reflection, just start the classname with an underscore:

    ---------------------------------------------------------------------------
    import endpoints

    class _BaseController(endpoints.Controller):
        def GET(self, *args, **kwargs):
            return "every controller that extends this will have this GET method"
    ---------------------------------------------------------------------------
    """
    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    call = None
    """holds the call() instance that invoked this Controller"""

    private = False
    """set this to True if the controller should not be picked up by reflection, the controller
    will still be available, but reflection will not reveal it as an endpoint"""

    cors = True
    """Activates CORS support, http://www.w3.org/TR/cors/"""

    content_type = "application/json"
    """the response content type this controller will set"""

    encoding = 'UTF-8'
    """the response charset of this controller"""

    def __init__(self, request, response, *args, **kwargs):
        self.request = request
        self.response = response
        super(Controller, self).__init__(*args, **kwargs)
        self.set_cors_common_headers()

    def OPTIONS(self, *args, **kwargs):
        if not self.cors:
            raise CallError(405)

        req = self.request

        origin = req.get_header('origin')
        if not origin:
            raise CallError(400, 'Need Origin header') 
        call_headers = [
            ('Access-Control-Request-Headers', 'Access-Control-Allow-Headers'),
            ('Access-Control-Request-Method', 'Access-Control-Allow-Methods')
        ]
        for req_header, res_header in call_headers:
            v = req.get_header(req_header)
            if v:
                self.response.set_header(res_header, v)
            else:
                raise CallError(400, 'Need {} header'.format(req_header))

        other_headers = {
            'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Max-Age': 3600
        }
        self.response.add_headers(other_headers)

    def set_cors_common_headers(self):
        """
        This will set the headers that are needed for any cors request (OPTIONS or real)
        """
        if not self.cors: return

        req = self.request
        origin = req.get_header('origin')
        if origin:
            self.response.set_header('Access-Control-Allow-Origin', origin)

    def handle(self):
        """handles the request and returns the response

        :returns: Response instance, the response object with a body already"""
        start = time.time()
        req = self.request
        res = self.response
        try:
            self.log_start(start)
            res.set_header('Content-Type', "{};charset={}".format(
                self.content_type,
                self.encoding
            ))

            encoding = req.accept_encoding
            res.encoding = encoding if encoding else self.encoding

            controller_args = req.controller_info["method_args"]
            controller_kwargs = req.controller_info["method_kwargs"]

            controller_methods = self.find_methods()
            for controller_method_name, controller_method in controller_methods:
                try:
                    logger.debug("Attempting to handle request with {}.{}.{}".format(
                        req.controller_info['module_name'],
                        req.controller_info['class_name'],
                        controller_method_name
                    ))
                    res.body = controller_method(
                        *controller_args,
                        **controller_kwargs
                    )
                    break

                except RouteError:
                    logger.debug("Request {}.{}.{} failed routing check".format(
                        req.controller_info['module_name'],
                        req.controller_info['class_name'],
                        controller_method_name
                    ))

        finally:
            self.log_stop(start)

    def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        pass

    def find_methods(self):
        methods = []
        req = self.request
        method_name = req.method.upper()
        member = getattr(self, method_name, None)
        if member:
            methods.append((method_name, member))

        else:
            members = inspect.getmembers(self)
            for member_name, member in members:
                if member_name.startswith(method_name):
                    methods.append((member_name, member))

        return methods

    def get_method_name(self, req, controller_class):
        """
        perform any normalization of the controller's method

        return -- string -- the full method name to be used
        """
        method = req.method.upper()
        version = req.version(controller_class.content_type)
        if version:
            method += "_{}".format(version)

        return method

    def get_method(self, req, controller_instance, method_name):
        """using the controller_info retrieved from get_controller_info(), get the
        actual controller callback method that will be used to handle the request"""
        callback = None
        try:
            callback = getattr(controller_instance, method_name)

        except AttributeError as e:
            logger.warning(str(e), exc_info=True)
            raise CallError(405, "{} {} not supported".format(req.method, req.path))

        return callback

    def get_method_params(self, request, controller_args, controller_kwargs):
        pass


    def log_start(self, start):
        """log all the headers and stuff at the start of the request"""
        if not logger.isEnabledFor(logging.INFO): return

        try:
            req = self.request

            logger.info("REQUEST {} {}?{}".format(req.method, req.path, req.query))
            logger.info(datetime.datetime.strftime(datetime.datetime.utcnow(), "DATE %Y-%m-%dT%H:%M:%S.%f"))

            ip = req.ip
            if ip:
                hs.append("\tIP ADDRESS: {}".format(ip))

            if 'authorization' in req.headers:
                logger.info('AUTH {}'.format(req.headers['authorization']))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            hs = ["Request Headers..."]
            for k, v in req.headers.items():
                if k not in ignore_hs:
                    hs.append("\t{}: {}".format(k, v))

            logger.info(os.linesep.join(hs))

        except Exception as e:
            logger.warn(e, exc_info=True)

    def log_stop(self, start):
        """log a summary line on how the request went"""
        if not logger.isEnabledFor(logging.INFO): return

        stop = time.time()
        get_elapsed = lambda start, stop, multiplier, rnd: round(abs(stop - start) * float(multiplier), rnd)
        elapsed = get_elapsed(start, stop, 1000.00, 1)
        total = "%0.1f ms" % (elapsed)
        logger.info("RESPONSE {} {} in {}".format(self.response.code, self.response.status, total))

