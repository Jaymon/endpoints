import importlib
import logging
import os
import sys
import fnmatch
import types

from .utils import AcceptHeader
from .http import Response, Request
from .exception import CallError, Redirect, CallStop, AccessDenied
from .core import Controller
from .decorators import _property


logger = logging.getLogger(__name__)

_module_cache = {}

def get_controllers(controller_prefix):
    """get all the modules in the controller_prefix

    returns -- set -- a set of string module names"""
    global _module_cache
    if not controller_prefix:
        raise ValueError("controller prefix is empty")
    if controller_prefix in _module_cache:
        return _module_cache[controller_prefix]

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

    _module_cache.setdefault(controller_prefix, {})
    _module_cache[controller_prefix] = modules
    return modules


class Call(object):
    """
    Where all the routing magic happens

    we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs

    GET /foo -> controller_prefix.version.foo.Default.get
    POST /foo/bar -> controller_prefix.version.foo.Bar.post
    GET /foo/bar/che -> controller_prefix.version.foo.Bar.get(che)
    POST /foo/bar/che?baz=foo -> controller_prefix.version.foo.Bar.post(che, baz=foo)
    """

    controller_prefix = u""
    """since endpoints interprets requests as /module/class, you can use this to do: controller_prefix.module.class"""

    content_type = "application/json"
    """the content type this call is going to represent"""

    @_property
    def request(self):
        '''
        Call.request, this request object is used to decide how to route the client request

        a Request instance to be used to translate the request to a controller
        '''
        return Request()

    @_property
    def response(self):
        '''
        Call.response, this object is used to decide how to answer the client

        a Response instance to be returned from handle populated with info from controller
        '''
        return Response()

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

    def get_controllers(self, controller_prefix):
        """return a set of string controllers that includes controller_prefix and
        any sub modules underneath it

        controller_prefix -- string -- you pass this in because it can be different
            values (not just self.controller_prefix) depending on if a Versioned call
            is being used, etc.
        """
        cset = get_controllers(controller_prefix)
        return cset

    def get_module_name(self, path_args):
        """returns the module_name and remaining path args.

        return -- tuple -- (module_name, path_args)"""
        controller_prefix = self.get_normalized_prefix()
        cset = self.get_controllers(controller_prefix)
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
        d['module_name'] = u""
        d['class_name'] = u"Default"
        d['module'] = None
        d['class'] = None
        d['method'] = req.method.upper()
        d['args'] = []
        d['kwargs'] = {}

        module_name, path_args = self.get_module_name(path_args)
        d['module_name'] = module_name
        d['module'] = self.get_module(d['module_name'])

        class_object = None
        if path_args:
            class_object = self.get_class(d['module'], path_args[0].capitalize())

        if class_object:
            path_args.pop(0)

        else:
            class_object = self.get_class(d['module'], d['class_name'])
            if not class_object:
                class_object = None
                raise TypeError(
                    "could not find a valid controller with {}.{}.{}".format(
                        d['module_name'],
                        d['class_name'],
                        d['method']
                    )
                )

        d['class'] = class_object
        d['class_name'] = class_object.__name__
        d['args'] = path_args
        d['kwargs'] = self.get_kwargs()

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

    def generate_body(self):
        """create a generator that returns the body for the given request

        this is wrapped like this so that a controller can use yield result and then
        have it pick up right where it left off after resturning back to the client
        what yield returned, it's just a tricksy way of being able to defer some
        processing until after responding to the client

        return -- generator -- a body generator"""
        try:
            body_generated = False
            self.response.headers['Content-Type'] = self.content_type
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
            self.response.headers.update(e.headers)
            ret = e.body

        elif isinstance(e, Redirect):
            #logger.exception(e)
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = None
            self.response.headers.update(e.headers)
            ret = None

        elif isinstance(e, (AccessDenied, CallError)):
            #logger.debug("Request Path: {}".format(self.request.path))
            exc_info = sys.exc_info()
            logger.warning(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = e
            self.response.headers.update(e.headers)
            ret = e

        elif isinstance(e, TypeError):
            # this is raised when there aren't enough args passed to controller
            exc_info = sys.exc_info()
            logger.warning(str(e), exc_info=exc_info)
            self.response.code = 404
            #self.response.body = e
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


class VersionCall(Call):
    """
    versioning is based off of this post: http://urthen.github.io/2013/05/09/ways-to-version-your-api/
    """
    default_version = None
    """set this to the default version if you want a fallback version, if this is None then version check is enforced"""

    def get_normalized_prefix(self):
        cp = u""
        if hasattr(self, "controller_prefix"):
            cp = self.controller_prefix
        v = self.get_version()
        if cp:
            cp += u".{}".format(v)
        else:
            cp = v

        return cp

    def get_version(self):
        if not self.content_type:
            raise ValueError("You are versioning a call with no content_type")

        v = None
        accept_header = self.request.get_header('accept', u"")
        if accept_header:
            a = AcceptHeader(accept_header)
            for mt in a.filter(self.content_type):
                v = mt[2].get(u"version", None)
                if v: break

        if not v:
            v = self.default_version
            if not v:
                raise CallError(406, "Expected accept header with {};version=N media type".format(self.content_type))

        return v

