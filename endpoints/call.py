import importlib
import logging
import os
import sys
import fnmatch
import types
import traceback
import inspect

from .utils import AcceptHeader
from .http import Response, Request
from .exception import CallError, Redirect, CallStop, AccessDenied
from .core import Controller
from .decorators import _property


logger = logging.getLogger(__name__)


class Router(object):

    _module_name_cache = {}

    @property
    def controllers(self):
        """get all the modules in the controller_prefix

        returns -- set -- a set of string module names"""
        controller_prefix = self.controller_prefix
        _module_name_cache = type(self)._module_name_cache
        if controller_prefix in _module_name_cache:
            return _module_name_cache[controller_prefix]

        module = importlib.import_module(controller_prefix)
        basedir = os.path.dirname(module.__file__)
        modules = set()

        for root, dirs, files in os.walk(basedir, topdown=True):
            dirs[:] = [d for d in dirs if d[0] != '.' or d[0] != '_']

            module_name = root.replace(basedir, '', 1)
            module_name = [controller_prefix] + filter(None, module_name.split('/'))
            for f in fnmatch.filter(files, '*.py'):
                if f.startswith('__init__'):
                    modules.add('.'.join(module_name))
                else:
                    # we want to ignore any "private" modules
                    if not f.startswith('_'):
                        file_name = os.path.splitext(f)[0]
                        modules.add('.'.join(module_name + [file_name]))

        _module_name_cache.setdefault(controller_prefix, {})
        _module_name_cache[controller_prefix] = modules
        return modules

    def __init__(self, controller_prefix, path_args=None):
        self.controller_prefix = controller_prefix
        if not controller_prefix:
            raise ValueError("controller prefix is empty")

        if not path_args: path_args = []
        self.load(path_args)

    def load(self, path_args):
        self.controller_class_name = u"Default"
        module_name, args = self.get_module_name(path_args)
        self.controller_module_name = module_name
        self.controller_module = self.get_module(module_name)

        class_object = None
        if args:
            class_object = self.get_class(self.controller_module, args[0].capitalize())

        if class_object:
            args.pop(0)

        else:
            class_object = self.get_class(self.controller_module, self.controller_class_name)

        if class_object:
            self.controller_class_name = class_object.__name__
        self.controller_class = class_object
        self.controller_method_args = args

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


class Call(object):
    """
    Where all the routing magic happens

    we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs

    GET /foo -> controller_prefix.version.foo.Default.get
    POST /foo/bar -> controller_prefix.version.foo.Bar.post
    GET /foo/bar/che -> controller_prefix.version.foo.Bar.get(che)
    POST /foo/bar/che?baz=foo -> controller_prefix.version.foo.Bar.post(che, baz=foo)
    """
    router_class = Router

    controller_prefix = u""
    """since endpoints interprets requests as /module/class, you can use this to do: controller_prefix.module.class"""

    content_type = "application/json"
    """the content type this call is going to represent"""

    charset = 'UTF-8'
    """the default charset of the call, this will be passed down in the response"""

    @_property
    def version(self):
        """
        versioning is based off of this post 
        http://urthen.github.io/2013/05/09/ways-to-version-your-api/
        """
        v = None
        accept_header = self.request.get_header('accept', u"")
        if accept_header:
            if not self.content_type:
                raise ValueError("You are versioning a call with no content_type")

            a = AcceptHeader(accept_header)
            for mt in a.filter(self.content_type):
                v = mt[2].get("version", None)
                if v: break

        return v

    def __init__(self, controller_prefix, *args, **kwargs):
        '''
        create the instance

        controller_prefix -- string -- the module path where all your controller modules live
        *args -- tuple -- convenience, in case you extend and need something in another method
        **kwargs -- dict -- convenience, in case you extend
        '''
        if not controller_prefix:
            raise ValueError("controller_prefix was empty")

        self.controller_prefix = controller_prefix
        self.args = args
        self.kwargs = kwargs

        self.router = None
        self.request = None
        self.response = None

    def get_kwargs(self):
        """combine GET and POST params to be passed to the controller"""
        req = self.request
        kwargs = dict(req.query_kwargs)
        if req.has_body():
            kwargs.update(req.body_kwargs)

        return kwargs

    def get_controller_info(self):
        '''
        get info about finding a controller based off of the request info

        This method will use path info trying to find the longest module name it
        can and then the class name, passing anything else that isn't the module
        or the class as the args, with any query params as the kwargs

        You can modify a lot of the behavior of this method by overriding the
        sub methods that it calls

        return -- dict -- all the gathered info about the controller
        '''
        d = {}
        req = self.request
        path_args = list(req.path_args)
        router = self.router_class(self.controller_prefix, path_args)

        d['module'] = router.controller_module
        d['module_name'] = router.controller_module_name

        d['class'] = router.controller_class
        d['class_name'] = router.controller_class_name

        d['method'] = self.get_normalized_method()
        d['args'] = router.controller_method_args
        d['kwargs'] = self.get_kwargs()

        if not d['class']:
            raise TypeError(
                "could not find a valid controller with {}.{}.{}".format(
                    d['module_name'],
                    d['class_name'],
                    d['method']
                )
            )

        return d

    def get_callback(self, controller_info):
        """using the controller_info retrieved from get_controller_info(), get the
        actual controller callback method that will be used to handle the request"""
        callback = None
        try:
            instance = controller_info['class'](self.request, self.response)
            instance.call = self

            callback = getattr(instance, controller_info['method'])
            logger.debug("handling request with callback {}.{}.{}".format(
                controller_info['module_name'],
                controller_info['class_name'],
                controller_info['method'])
            )

        except AttributeError, e:
            r = self.request
            raise CallError(405, "{} {} not supported".format(r.method, r.path))

        return callback

    def get_callback_info(self):
        '''
        get the controller callback that will be used to complete the call

        return -- tuple -- (callback, callback_args, callback_kwargs), basically, everything you need to
            call the controller: callback(*callback_args, **callback_kwargs)
        '''
        try:
            d = self.get_controller_info()

        except (ImportError, AttributeError, TypeError), e:
            r = self.request
            exc_info = sys.exc_info()
            logger.warning(str(e), exc_info=exc_info)
            raise CallError(
                404,
                "{} not found because of {} \"{}\" on {}:{}".format(
                    r.path,
                    exc_info[0].__name__,
                    str(e),
                    os.path.basename(exc_info[2].tb_frame.f_code.co_filename),
                    exc_info[2].tb_lineno
                )
            )

        return self.get_callback(d), d['args'], d['kwargs'] 

    def get_normalized_prefix(self):
        """
        do any normalization of the controller prefix and return it

        return -- string -- the full controller module prefix
        """
        return self.controller_prefix

    def get_normalized_method(self):
        """
        perform any normalization of the controller's method

        return -- string -- the full method name to be used
        """
        method = self.request.method.upper()
        version = self.version
        if version:
            method += "_{}".format(version)

        return method

    def generate_body(self):
        """create a generator that returns the body for the given request

        this is wrapped like this so that a controller can use yield result and then
        have it pick up right where it left off after returning back to the client
        what yield returned, it's just a tricksy way of being able to defer some
        processing until after responding to the client

        return -- generator -- a body generator"""
        try:
            body_generated = False
            self.response.set_header('Content-Type', "{};charset={}".format(self.content_type, self.charset))

            self.response.charset = self.charset
            callback, callback_args, callback_kwargs = self.get_callback_info()
            body = self.handle_controller(callback, callback_args, callback_kwargs)
            if isinstance(body, types.GeneratorType):
                for b in body:
                    body_generated = True
                    yield b

            else:
                yield body

        except Exception as e:
            if body_generated:
                raise
            else:
                body = self.handle_error(e)
                yield body

    def handle_controller(self, callback, callback_args, callback_kwargs):
        body = callback(*callback_args, **callback_kwargs)
        return body

    def handle_error(self, e):
        ret = None
        if isinstance(e, CallStop):
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = e.body
            self.response.set_headers(e.headers)
            ret = e.body

        elif isinstance(e, Redirect):
            #logger.exception(e)
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = None
            self.response.set_headers(e.headers)
            ret = None

        elif isinstance(e, (AccessDenied, CallError)):
            #logger.debug("Request Path: {}".format(self.request.path))
            exc_info = sys.exc_info()
            logger.warning(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = e
            self.response.set_headers(e.headers)
            ret = e

        elif isinstance(e, TypeError):
            exc_info = sys.exc_info()
            tbs = traceback.extract_tb(exc_info[2])
            filename, linenum, funcname, text = tbs[-1]
            filename = os.path.splitext(filename)[0]

            methodname = "handle_controller"
            methodfilename = os.path.splitext(inspect.getfile(type(self)))[0]
            if funcname == methodname and filename == methodfilename:
                self.response.code = 404
                ret = e
            else:
                self.response.code = 500
                ret = e

        else:
            logger.exception(e)
            self.response.code = 500
            #self.response.body = e
            ret = e

        return ret

    def handle(self):
        """returns a response where the controller is already evaluated

        return -- Response() -- the response object with a body already"""
        self.ghandle()
        for b in self.response.gbody: pass
        return self.response

    def ghandle(self):
        '''
        return a response that is ready to have the controller evaluated, you can
        trigger the controller being called and everything by just calling the body

            response.body

        or by iterating through the generator

            for b in response.gbody: pass

        return -- Response() -- the response object, ready to be populated with
            information once the body is called
        '''
        self.response.gbody = self.generate_body()
        return self.response

