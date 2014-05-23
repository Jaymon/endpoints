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


logger = logging.getLogger(__name__)

_module_cache = {}

def get_controllers(controller_prefix):
    """get all the modules in the controller_prefix"""
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

    @property
    def request(self):
        '''
        Call.request, this request object is used to decide how to route the client request

        a Request instance to be used to translate the request to a controller
        '''
        if not hasattr(self, "_request"):
            self._request = Request()

        return self._request

    @request.setter
    def request(self, v):
        self._request = v

    @property
    def response(self):
        '''
        Call.response, this object is used to decide how to answer the client

        a Response instance to be returned from handle populated with info from controller
        '''
        if not hasattr(self, "_response"):
            self._response = Response()

        return self._response

    @response.setter
    def response(self, v):
        self._response = v

    def __init__(self, controller_prefix, *args, **kwargs):
        '''
        create the instance

        controller_prefix -- string -- the module path where all your controller modules live
        *args -- tuple -- convenience, in case you extend and need something in another method
        **kwargs -- dict -- convenience, in case you extend
        '''
        assert controller_prefix, "controller_prefix was empty"

        self.controller_prefix = controller_prefix
        self.args = args
        self.kwargs = kwargs

    def get_controller_info_simple(self):
        '''
        get info about finding a controller based off of the request info

        this method will use the path info as:

            module_name/class_name/args?kwargs

        return -- dict -- all the gathered info about the controller
        '''
        d = {}
        req = self.request
        path_args = list(req.path_args)
        d['module_name'] = u"default"
        d['class_name'] = u"Default"
        d['module'] = None
        d['class'] = None
        d['method'] = req.method.upper()
        d['args'] = []
        d['kwargs'] = {}

        # the first arg is the module
        if len(path_args) > 0:
            module_name = path_args.pop(0)
            if module_name.startswith(u'_'):
                raise ValueError("{} is an invalid".format(module_name))
            d['module_name'] = module_name

        controller_prefix = self.get_normalized_prefix()
        if controller_prefix:
            d['module_name'] = u".".join([controller_prefix, d['module_name']])

        # the second arg is the Class
        if len(path_args) > 0:
            class_name = path_args.pop(0)
            if class_name.startswith(u'_'):
                raise ValueError("{} is invalid".format(class_name))
            d['class_name'] = class_name.capitalize()

        d['module'] = importlib.import_module(d['module_name'])
        d['class'] = getattr(d['module'], d['class_name'])
        d['args'] = path_args
        d['kwargs'] = req.query_kwargs

        return d

    def get_controller_info_advanced(self):
        '''
        get info about finding a controller based off of the request info

        This method will use path info trying to find the longest module name it
        can and then the class name, passing anything else that isn't the module
        or the class as the args, with any query params as the kwargs

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

        controller_prefix = self.get_normalized_prefix()
        cset = get_controllers(controller_prefix)
        module_name = controller_prefix
        mod_name = module_name
        while path_args:
            mod_name += "." + path_args[0]
            if mod_name in cset:
                module_name = mod_name
                path_args.pop(0)
            else:
                break

        d['module_name'] = module_name
        d['module'] = importlib.import_module(d['module_name'])

        # let's get the class
        class_object = None
        if path_args:
            class_name = path_args[0].capitalize()
            class_object = getattr(d['module'], class_name, None)
            if class_object and issubclass(class_object, Controller):
                d['class_name'] = class_name
                path_args.pop(0)

            else:
                class_object = None

        if not class_object:
            class_name = d['class_name']
            class_object = getattr(d['module'], class_name, None)
            if not class_object or not issubclass(class_object, Controller):
                class_object = None
                raise TypeError(
                    "could not find a valid controller with {}.{}.{}".format(
                        d['module_name'],
                        class_name,
                        d['method']
                    )
                )

        d['class'] = class_object
        d['args'] = path_args

        # combine GET and POST params to be passed to the controller
        kwargs = dict(req.query_kwargs)
        if req.has_body():
            kwargs.update(req.body_kwargs)
        d['kwargs'] = kwargs

        return d

    def get_controller_info(self):
        return self.get_controller_info_advanced()

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
            logger.exception(e)
            raise CallError(
                404,
                "{} not found because of {} \"{}\" on {}:{}".format(
                    r.path,
                    sys.exc_info()[0].__name__,
                    str(e),
                    os.path.basename(sys.exc_info()[2].tb_frame.f_code.co_filename),
                    sys.exc_info()[2].tb_lineno
                )
            )

        try:
            instance = d['class'](self.request, self.response)
            instance.call = self

            callback = getattr(instance, d['method'])
            logger.debug("handling request with callback {}.{}.{}".format(d['module_name'], d['class_name'], d['method']))

        except AttributeError, e:
            r = self.request
            raise CallError(405, "{} {} not supported".format(r.method, r.path))

        return callback, d['args'], d['kwargs']

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
            self.response.headers['Content-Type'] = self.content_type
            callback, callback_args, callback_kwargs = self.get_callback_info()
            body = callback(*callback_args, **callback_kwargs)
            if isinstance(body, types.GeneratorType):
                for b in body:
                    yield b

            else:
                yield body

        except CallStop, e:
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = e.body
            self.response.headers.update(e.headers)
            yield e.body

        except Redirect, e:
            #logger.exception(e)
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = e.code
            #self.response.body = None
            self.response.headers.update(e.headers)
            yield None

        except (AccessDenied, CallError), e:
            #logger.debug("Request Path: {}".format(self.request.path))
            logger.exception(e)
            self.response.code = e.code
            #self.response.body = e
            self.response.headers.update(e.headers)
            yield e

        except TypeError, e:
            # this is raised when there aren't enough args passed to controller
            exc_info = sys.exc_info()
            logger.info(str(e), exc_info=exc_info)
            self.response.code = 404
            #self.response.body = e
            yield e

        except Exception, e:
            logger.exception(e)
            self.response.code = 500
            #self.response.body = e
            yield e

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
        h = self.request.headers
        accept_header = h.get('accept', u"")
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

