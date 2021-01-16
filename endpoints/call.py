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

from .utils import AcceptHeader, String
from .http import Response, Request
from .exception import (
    CallError,
    Redirect,
    CallStop,
    AccessDenied,
    RouteError,
    VersionError,
    CloseConnection,
)
from .compat import *
from .reflection import ReflectModule, ReflectController, ReflectHTTPMethod


logger = logging.getLogger(__name__)


class Call(object):
    """The middleman

    This class is created in the interface and is responsible for taking the request
    and handling it and setting everything into the body of response so the interface
    can respond to the request"""

    # TODO -- 6-19-2017, I'm not wild about this property or what it does so I shouldn't
    # rely on it existing in the future
    quiet = False
    """Set to True if you would like to avoid logging the request lifecycle"""

    def __init__(self, req, res, rou):
        self.request = req
        self.response = res
        self.router = rou
        self.controller = None

    def create_controller(self):
        """Create a controller to handle the request

        :returns: Controller, this Controller instance should be able to handle
            the request
        """
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
        """Called from the interface to actually handle the request."""
        body = None
        req = self.request
        res = self.response
        rou = self.router
        con = None
        start = time.time()

        try:
            con = self.create_controller()
            con.call = self
            self.controller = con
            if not self.quiet:
                con.log_start(start)

            # the controller handle method will manipulate self.response, it first
            # tries to find a handle_HTTP_METHOD method, if it can't find that it
            # will default to the handle method (which is implemented on Controller).
            # method arguments are passed in so child classes can add decorators
            # just like the HTTP_METHOD that will actually handle the request
            controller_args, controller_kwargs = con.find_method_params()
            controller_method = getattr(con, "handle_{}".format(req.method), None)
            if not controller_method:
                controller_method = getattr(con, "handle")

            if not self.quiet:
                logger.debug("Request handle method: {}.{}.{}".format(
                    con.__class__.__module__,
                    con.__class__.__name__,
                    controller_method.__name__
                ))
            controller_method(*controller_args, **controller_kwargs)

        except CloseConnection:
            raise

        except Exception as e:
            self.handle_error(e) # this will manipulate self.response

        finally:
            if res.code == 204:
                res.headers.pop('Content-Type', None)
                res.body = None # just to be sure since body could've been ""

            if con:
                if not self.quiet:
                    con.log_stop(start)

        return res

    def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        This method will set the response body and then also call Controller.handle_error
        for further customization if the Controller is available

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        req = self.request
        res = self.response
        con = self.controller

        res.body = e

        if isinstance(e, CallStop):
            logger.debug(String(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            res.body = e.body

        elif isinstance(e, Redirect):
            logger.debug(String(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            res.body = None

        elif isinstance(e, (AccessDenied, CallError)):
            logger.warning(String(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)

        elif isinstance(e, NotImplementedError):
            logger.warning(String(e), exc_info=True)
            res.code = 501

        elif isinstance(e, TypeError):
            e_msg = String(e)
            controller_info = req.controller_info

            # filter out TypeErrors raised from non handler methods
            correct_prefix = e_msg.startswith(controller_info["method_prefix"]) or \
                e_msg.startswith(controller_info["method_fallback"])

            if correct_prefix and 'argument' in e_msg:
                # there are subtle messaging differences between py2 and py3
                pos_errs = ["takes exactly", "takes no arguments", "positional argument"]
                if (pos_errs[0] in e_msg) or (pos_errs[1] in e_msg) or (pos_errs[2] in e_msg):
                    # TypeError: <METHOD>() takes exactly M argument (N given)
                    # TypeError: <METHOD>() takes no arguments (N given)
                    # TypeError: <METHOD>() takes M positional arguments but N were given
                    # we shouldn't ever get the "takes no arguments" case because of self,
                    # but just in case
                    # check if there are path args, if there are then 404, if not then 405
                    logger.debug(e_msg, exc_info=True)

                    if len(controller_info["method_args"]):
                        res.code = 404

                    else:
                        res.code = 405

                elif "unexpected keyword argument" in e_msg:
                    # TypeError: <METHOD>() got an unexpected keyword argument '<NAME>'

                    try:
                        # if the binding of just the *args works then the
                        # problem is the **kwargs so a 405 is appropriate,
                        # otherwise return a 404
                        inspect.getcallargs(controller_info["method"], *controller_info["method_args"])
                        res.code = 405

                        logger.warning("Controller method {}.{}.{}".format(
                            controller_info['module_name'],
                            controller_info['class_name'],
                            e_msg
                        ), exc_info=True)

                    except TypeError:
                        res.code = 404

                elif "multiple values" in e_msg:
                    # TypeError: <METHOD>() got multiple values for keyword argument '<NAME>'
                    try:
                        inspect.getcallargs(controller_info["method"], *controller_info["method_args"])
                        res.code = 409
                        logger.warning(e)

                    except TypeError:
                        res.code = 404

                else:
                    res.code = 500
                    logger.exception(e)

            else:
                res.code = 500
                logger.exception(e)

        else:
            res.code = 500
            logger.exception(e)

        if con:
            error_method = getattr(con, "handle_{}_error".format(res.code), None)
            if not error_method:
                error_method = getattr(con, "handle_{}_error".format(req.method), None)
                if not error_method:
                    error_method = getattr(con, "handle_error")

            logger.debug("Handle {} error using method: {}.{}".format(
                res.code,
                con.__class__.__name__,
                error_method.__name__
            ))
            error_method(e, **kwargs)


class Router(object):
    """
    Where all the routing magic happens, this takes an incoming URI and gathers
    the information needed to turn that URI into a Controller

    we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs

    GET /foo -> controller_prefix.foo.Default.GET
    POST /foo/bar -> controller_prefix.foo.Bar.POST
    GET /foo/bar/che -> controller_prefix.foo.Bar.GET(che)
    POST /foo/bar/che?baz=foo -> controller_prefix.foo.Bar.POST(che, baz=foo)
    """
    default_class_name = "Default"

    _module_name_cache = {}

    @property
    def module_names(self):
        """get all the modules in the controller_prefixes

        :returns: set, a set of string module names
        """
        ret = set()
        _module_name_cache = type(self)._module_name_cache

        for controller_prefix in self.controller_prefixes:

            if controller_prefix in _module_name_cache:
                ret.update(_module_name_cache[controller_prefix])

            else:
                logger.debug("Populating module cache for controller_prefix {}".format(controller_prefix))
                rm = ReflectModule(controller_prefix)
                module_names = rm.module_names

                #_module_name_cache.setdefault(controller_prefix, {})
                type(self)._module_name_cache[controller_prefix] = module_names
                ret.update(module_names)

        return ret

    def __init__(self, controller_prefixes):
        if not controller_prefixes:
            raise ValueError("controller_prefixes is empty")

        self.controller_prefixes = controller_prefixes

    def find(self, req, res):
        ret = {}
        controller_path = []

        logger.debug("Searching for Controller using path: {}".format(req.path))

        controller_prefix, module_name, module_path, controller_method_args = self.get_module_name(
            list(req.path_args)
        )
        controller_module_name = module_name
        controller_module_r = ReflectModule(module_name)
        controller_module = controller_module_r.module

        controller_class = None
        if controller_method_args:
            controller_class = self.get_class(
                controller_module,
                controller_method_args[0]
            )

        if controller_class:
            controller_path.append(controller_method_args.pop(0))
            controller_class_name = controller_class.__name__

        else:
            controller_class_name = self.default_class_name
            controller_class = self.get_class(controller_module, controller_class_name)

        if not controller_class:
            raise TypeError(
                "Could not find a valid module and Controller class for {}".format(
                    req.path
                )
            )

        ret['controller_prefix'] = controller_prefix
        ret['module'] = controller_module
        ret['module_reflection'] = controller_module_r
        ret['module_name'] = controller_module_name
        ret['module_path'] = "/".join(module_path)

        ret['class'] = controller_class
        ret['class_reflection'] = ReflectController(
            controller_module_r,
            controller_class,
            controller_prefix
        )
        ret['class_name'] = controller_class_name
        ret['class_instance'] = self.get_class_instance(req, res, controller_class)
        ret['class_path'] = "/".join(controller_path)

        # we merge the leftover path args with the body kwargs
        controller_method_args.extend(req.body_args)

        ret['method_args'] = controller_method_args
        ret['method_kwargs'] = req.kwargs

        ret["method_prefix"] = req.method.upper()
        ret["method_fallback"] = "ANY"

        req.controller_info = ret
        return ret

    def get_class_instance(self, req, res, controller_class):
        instance = controller_class(req, res)
        instance.router = self
        return instance

    def get_module_name(self, path_args):
        """returns the module_name and remaining path args.

        :returns: tuple, (controller_prefix, module_name, module_path, path_args),
            where controller_prefix is the prefix the module was found in and module_name
            is the python module path (eg, foo.bar.che) and module_path is a list
            of the different parts (eg, ["foo", "bar", "che"]) and path_args are
            the remaining path_args after finding the module
        """
        module_name = ""
        module_path = []

        # using the path_args we are going to try and find the best module path
        # for the request
        if path_args:
            cset = self.module_names
            for controller_prefix in self.controller_prefixes:
                mod_name = controller_prefix + "." + path_args[0]
                if mod_name in cset:
                    module_name = mod_name
                    module_path.append(path_args.pop(0))

                    while path_args:
                        mod_name += "." + path_args[0]
                        if mod_name in cset:
                            module_name = mod_name
                            module_path.append(path_args.pop(0))
                        else:
                            break

                    break

        if not module_name:
            # we didn't find the correct module using module paths, so now let's
            # try class paths, first found class path wins
            default_module_name = ""

            for controller_prefix in self.controller_prefixes:
                controller_module = ReflectModule(controller_prefix).module
                if path_args:
                    controller_class = self.get_class(controller_module, path_args[0])
                    if controller_class:
                        module_name = controller_prefix
                        break

                if not default_module_name:
                    # look for the default class just in case
                    controller_class = self.get_class(controller_module, self.default_class_name)
                    if controller_class:
                        default_module_name = controller_prefix

            if not module_name:
                if default_module_name:
                    module_name = default_module_name
                    controller_prefix = module_name

                else:
                    raise TypeError(
                        "Could not find a valid module with path {} and controller_prefixes {}".format(
                            "/".join(path_args),
                            self.controller_prefixes
                        )
                    )
                    #module_name = self.controller_prefixes[0]

        return controller_prefix, module_name, module_path, path_args

    def get_class(self, module, class_name):
        """try and get the class_name from the module and make sure it is a valid
        controller"""
        # let's get the class
        class_name = class_name.capitalize()
        class_object = getattr(module, class_name, None)
        if not class_object or not issubclass(class_object, Controller):
            class_object = None

        return class_object


class Controller(object):
    """
    this is the interface for a Controller sub class

    All your controllers MUST extend this base class, since it ensures a proper interface :)

    to activate a new endpoint, just add a module on your PYTHONPATH.controller_prefix that has a class
    that extends this class, and then defines at least one http method (like GET or POST), so if you
    wanted to create the endpoint /foo/bar (with controller_prefix che), you would just need to:

    :Example:
        # che/foo.py
        import endpoints

        class Bar(endpoints.Controller):
            def GET(self, *args, **kwargs):
                return "you just made a GET request to /foo/bar"

    as you support more methods, like POST and PUT, you can just add POST() and PUT()
    methods to your Bar class and Bar will support those http methods. Although you can
    request any method (a method is valid if it is all uppercase), here is a list of
    rfc approved http request methods:

    http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

    If you would like to create a base controller that other controllers will extend and don't
    want that controller to be picked up by reflection, just start the classname with an underscore:

    :Example:
        import endpoints

        class _BaseController(endpoints.Controller):
            def GET(self, *args, **kwargs):
                return "every controller that extends this will have this GET method"
    """
    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    call = None
    """holds the call() instance that created this Controller"""

    router = None
    """holds the Router() instance that found this controller"""

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

        # we use self.logger and set the name to endpoints.call.module.class so
        # you can filter all controllers using endpoints.call, filter all
        # controllers in a certain module using endpoints.call.module or just a
        # specific controller using endpoints.call.module.class
        logger_name = logger.name
        class_name = self.__class__.__name__
        module_name = self.__class__.__module__
        self.logger = logging.getLogger("{}.{}.{}".format(logger_name, class_name, module_name))

    def OPTIONS(self, *args, **kwargs):
        """Handles CORS requests for this controller

        if self.cors is False then this will raise a 405, otherwise it sets everything
        necessary to satisfy the request in self.response
        """
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

    def handle(self, *controller_args, **controller_kwargs):
        """handles the request and returns the response

        This should set any response information directly onto self.response

        this method has the same signature as the request handling methods
        (eg, GET, POST) so subclasses can override this method and add decorators

        :param *controller_args: tuple, the path arguments that will be passed to
            the request handling method (eg, GET, POST)
        :param **controller_kwargs: dict, the query and body params merged together
        """
        req = self.request
        res = self.response
        res.set_header('Content-Type', "{};charset={}".format(
            self.content_type,
            self.encoding
        ))

        encoding = req.accept_encoding
        res.encoding = encoding if encoding else self.encoding

        # the @route* and @version decorators have a catastrophic error handler
        # that will be called if all if all found methods failed to resolve
        res_error_handler = None

        controller_methods = self.find_methods()
        for controller_method_name, controller_method in controller_methods:
            req.controller_info["method_name"] = controller_method_name
            req.controller_info["method"] = controller_method
            # VersionError and RouteError handling is here because they can be
            # raised multiple times in this one request and handled each time,
            # any exceptions that can't be handled are bubbled up
            try:
                self.logger.debug("Request Controller method: {}.{}.{}".format(
                    req.controller_info['module_name'],
                    req.controller_info['class_name'],
                    controller_method_name
                ))
                res.body = controller_method(
                    *controller_args,
                    **controller_kwargs
                )

                res_error_handler = None
                break

            except VersionError as e:
                if not res_error_handler:
                    res_error_handler = getattr(e.instance, "handle_failure", None)

                self.logger.debug("Request Controller method: {}.{}.{} failed version check [{} not in {}]".format(
                    req.controller_info['module_name'],
                    req.controller_info['class_name'],
                    controller_method_name,
                    e.request_version,
                    e.versions
                ))

            except RouteError as e:
                if not res_error_handler:
                    res_error_handler = getattr(e.instance, "handle_failure", None)

                self.logger.debug("Request Controller method: {}.{}.{} failed routing check".format(
                    req.controller_info['module_name'],
                    req.controller_info['class_name'],
                    controller_method_name
                ))

        if res_error_handler:
            res_error_handler(self)

    def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method, this method is called from the Call instance

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        pass

    def find_methods(self):
        """Find the methods that could satisfy this request

        This will go through and find any method that starts with the request.method,
        so if the request was GET /foo then this would find any methods that start
        with GET

        https://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html

        :returns: list of tuples (method_name, method), all the found methods
        """
        methods = []
        req = self.request
        controller_info = req.controller_info
        method_name = controller_info["method_prefix"]
        method_names = set()

        members = inspect.getmembers(self)
        for member_name, member in members:
            if member_name.startswith(method_name):
                if member:
                    methods.append((member_name, member))
                    method_names.add(member_name)

        if len(methods) == 0:
            fallback_method_name = controller_info["method_fallback"]
            any_method = getattr(self, fallback_method_name, "")
            if any_method:
                methods.append((fallback_method_name, any_method))

            else:
                if len(controller_info["method_args"]):
                    # if we have method args and we don't have a method to even
                    # answer the request it should be a 404 since the path is
                    # invalid
                    raise CallError(404)

                else:
                    # https://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1
                    # and 501 (Not Implemented) if the method is unrecognized or not
                    # implemented by the origin server
                    self.logger.warning("No methods to handle {} found".format(method_name), exc_info=True)
                    raise CallError(501, "{} {} not implemented".format(req.method, req.path))

        elif len(methods) > 1 and method_name in method_names:
            raise ValueError(
                " ".join([
                    "A multi method {} request should not have any methods named {}.",
                    "Instead, all {} methods should use use an appropriate decorator",
                    "like @route or @version and have a unique name starting with {}_"
                ]).format(
                    method_name,
                    method_name,
                    method_name,
                    method_name
                )
            )

        return methods

    def find_method_params(self):
        """Return the method params

        :returns: tuple (args, kwargs) that will be passed as *args, **kwargs
        """
        req = self.request
        args = req.controller_info["method_args"]
        kwargs = req.controller_info["method_kwargs"]
        return args, kwargs

    def log_start(self, start):
        """log all the headers and stuff at the start of the request"""
        if not self.logger.isEnabledFor(logging.INFO): return

        try:
            req = self.request
            uuid = getattr(req, "uuid", "")
            if uuid:
                uuid += " "

            if req.query:
                self.logger.info("Request {}method: {} {}?{}".format(uuid, req.method, req.path, req.query))
            else:
                self.logger.info("Request {}method: {} {}".format(uuid, req.method, req.path))

            self.logger.info("Request {}date: {}".format(
                uuid,
                datetime.datetime.utcfromtimestamp(start).strftime("%Y-%m-%dT%H:%M:%S.%f"),
            ))

            ip = req.ip
            if ip:
                self.logger.info("Request {}IP address: {}".format(uuid, ip))

            if 'authorization' in req.headers:
                self.logger.info('Request {}auth: {}'.format(uuid, req.headers['authorization']))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            #hs = []
            for k, v in req.headers.items():
                if k not in ignore_hs:
                    self.logger.info("Request {}header {}: {}".format(uuid, k, v))
                    #hs.append("Request header: {}: {}".format(k, v))

            #self.logger.info(os.linesep.join(hs))
            self.log_start_body()

        except Exception as e:
            self.logger.warn(e, exc_info=True)

    def log_start_body(self):
        """Log the request body

        this is separate from log_start so it can be easily overridden in children
        """
        if not self.logger.isEnabledFor(logging.DEBUG): return

        req = self.request
        uuid = getattr(req, "uuid", "")
        if uuid:
            uuid += " "

        if req.has_body():
            try:
                self.logger.debug("Request {}body: {}".format(uuid, req.body_kwargs))

            except Exception:
                self.logger.debug("Request {}body raw: {}".format(uuid, req.body))
                #logger.debug("RAW REQUEST: {}".format(req.raw_request))
                raise

    def log_stop(self, start):
        """log a summary line on how the request went"""
        if not self.logger.isEnabledFor(logging.INFO): return

        res = self.response
        req = self.request
        uuid = getattr(req, "uuid", "")
        if uuid:
            uuid += " "

        for k, v in res.headers.items():
            self.logger.info("Request {}response header {}: {}".format(uuid, k, v))

        stop = time.time()
        get_elapsed = lambda start, stop, multiplier, rnd: round(abs(stop - start) * float(multiplier), rnd)
        elapsed = get_elapsed(start, stop, 1000.00, 1)
        total = "%0.1f ms" % (elapsed)
        self.logger.info("Request {}response {} {} in {}".format(
            uuid,
            self.response.code,
            self.response.status,
            total
        ))

