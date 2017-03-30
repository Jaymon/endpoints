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
from .exception import CallError, Redirect, CallStop, AccessDenied
from .core import Controller
from .decorators import _property


logger = logging.getLogger(__name__)


class Router(object):

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
        ret['class_instance'] = self.get_instance(req, res, controller_class)

        ret['method_args'] = controller_method_args
        ret['method_kwargs'] = req.get_kwargs()
        ret['method_name'] = self.get_method_name(req, controller_class)
        ret['method'] = self.get_method(req, ret['class_instance'], ret['method_name'])

        return ret

    def get_instance(self, req, res, controller_class):
        instance = controller_class(req, res)
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

            callback = getattr(instance, controller_info['method_name'])

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
                self.controller_path_args.append(path_args.pop(0))
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

    #content_type = "application/json"
    """the content type this call is going to represent"""

    #charset = 'UTF-8'
    """the default charset of the call, this will be passed down in the response"""

#     @_property
#     def version(self):
#         """
#         versioning is based off of this post 
#         http://urthen.github.io/2013/05/09/ways-to-version-your-api/
#         """
#         v = None
#         accept_header = self.request.get_header('accept', u"")
#         if accept_header:
#             if not self.content_type:
#                 raise ValueError("You are versioning a call with no content_type")
# 
#             a = AcceptHeader(accept_header)
#             for mt in a.filter(self.content_type):
#                 v = mt[2].get("version", None)
#                 if v: break
# 
#         return v

#     def __init__(self, controller_prefix, *args, **kwargs):
#         '''
#         create the instance
# 
#         controller_prefix -- string -- the module path where all your controller modules live
#         *args -- tuple -- convenience, in case you extend and need something in another method
#         **kwargs -- dict -- convenience, in case you extend
#         '''
#         if not controller_prefix:
#             raise ValueError("controller_prefix was empty")
# 
#         self.controller_prefix = controller_prefix
#         self.args = args
#         self.kwargs = kwargs
# 
#         self.router = None
#         self.request = None
#         self.response = None
# 
#     def get_kwargs(self):
#         """combine GET and POST params to be passed to the controller"""
#         req = self.request
#         kwargs = dict(req.query_kwargs)
#         if req.has_body():
#             kwargs.update(req.body_kwargs)
# 
#         return kwargs

#     def get_controller_info(self):
#         '''
#         get info about finding a controller based off of the request info
# 
#         This method will use path info trying to find the longest module name it
#         can and then the class name, passing anything else that isn't the module
#         or the class as the args, with any query params as the kwargs
# 
#         You can modify a lot of the behavior of this method by overriding the
#         sub methods that it calls
# 
#         return -- dict -- all the gathered info about the controller
#         '''
#         d = {}
#         req = self.request
#         path_args = list(req.path_args)
#         router = self.router_class(self.controller_prefix, path_args)
# 
#         d['module'] = router.controller_module
#         d['module_name'] = router.controller_module_name
# 
#         d['class'] = router.controller_class
#         d['class_name'] = router.controller_class_name
#         d['path'] = router.controller_path
# 
#         d['method'] = self.get_normalized_method()
#         d['args'] = router.controller_method_args
#         d['kwargs'] = self.get_kwargs()
# 
#         if not d['class']:
#             raise TypeError(
#                 "could not find a valid controller with {}.{}.{}".format(
#                     d['module_name'],
#                     d['class_name'],
#                     d['method']
#                 )
#             )
# 
#         return d

#     def get_callback(self, controller_info):
#         """using the controller_info retrieved from get_controller_info(), get the
#         actual controller callback method that will be used to handle the request"""
#         callback = None
#         try:
#             self.request.controller_info = controller_info
#             instance = controller_info['class'](self.request, self.response)
#             instance.call = self
# 
#             callback = getattr(instance, controller_info['method'])
#             logger.debug("handling request with callback {}.{}.{}".format(
#                 controller_info['module_name'],
#                 controller_info['class_name'],
#                 controller_info['method'])
#             )
# 
#         except AttributeError as e:
#             logger.warning(str(e), exc_info=True)
#             r = self.request
#             raise CallError(405, "{} {} not supported".format(r.method, r.path))
# 
#         return callback

#     def get_callback_info(self):
#         '''
#         get the controller callback that will be used to complete the call
# 
#         return -- tuple -- (callback, callback_args, callback_kwargs), basically, everything you need to
#             call the controller: callback(*callback_args, **callback_kwargs)
#         '''
#         try:
#             d = self.get_controller_info()
# 
#         except IOError as e:
#             logger.warning(str(e), exc_info=True)
#             raise CallError(
#                 408,
#                 "The client went away before the request body was retrieved."
#             )
# 
#         except (ImportError, AttributeError, TypeError) as e:
#             exc_info = sys.exc_info()
#             logger.warning(str(e), exc_info=exc_info)
#             r = self.request
#             raise CallError(
#                 404,
#                 "{} not found because of {} \"{}\" on {}:{}".format(
#                     r.path,
#                     exc_info[0].__name__,
#                     str(e),
#                     os.path.basename(exc_info[2].tb_frame.f_code.co_filename),
#                     exc_info[2].tb_lineno
#                 )
#             )
# 
#         return self.get_callback(d), d['args'], d['kwargs'] 

#     def get_normalized_prefix(self):
#         """
#         do any normalization of the controller prefix and return it
# 
#         return -- string -- the full controller module prefix
#         """
#         return self.controller_prefix

#     def get_normalized_method(self):
#         """
#         perform any normalization of the controller's method
# 
#         return -- string -- the full method name to be used
#         """
#         method = self.request.method.upper()
#         version = self.version
#         if version:
#             method += "_{}".format(version)
# 
#         return method

#     def handle_controller(self, callback, callback_args, callback_kwargs):
#         body = callback(*callback_args, **callback_kwargs)
#         return body

#     def handle_error(self, e, **kwargs):
#         ret = None
#         if isinstance(e, CallStop):
#             logger.info(str(e), exc_info=True)
#             self.response.code = e.code
#             #self.response.body = e.body
#             self.response.add_headers(e.headers)
#             ret = e.body
# 
#         elif isinstance(e, Redirect):
#             #logger.exception(e)
#             logger.info(str(e), exc_info=True)
#             self.response.code = e.code
#             #self.response.body = None
#             self.response.add_headers(e.headers)
#             ret = None
# 
#         elif isinstance(e, (AccessDenied, CallError)):
#             #logger.debug("Request Path: {}".format(self.request.path))
#             logger.warning(str(e), exc_info=True)
#             self.response.code = e.code
#             #self.response.body = e
#             self.response.add_headers(e.headers)
#             ret = e
# 
#         elif isinstance(e, NotImplementedError):
#             logger.warning(str(e), exc_info=True)
#             self.response.code = 501
# 
#         elif isinstance(e, TypeError):
#             e_msg = unicode(e)
#             if e_msg.startswith(self.request.method) and 'argument' in e_msg:
#                 logger.debug(e_msg, exc_info=True)
#                 self.response.code = 404
# 
#             else:
#                 logger.exception(e)
#                 self.response.code = 500
# 
#         else:
#             logger.exception(e)
#             self.response.code = 500
#             ret = e
# 
#         return ret

#     def handle(self):
#         """returns a response where the controller is already evaluated
# 
#         return -- Response() -- the response object with a body already"""
#         body = None
#         callback = None
#         callback_args = []
#         callback_kwargs = {}
#         try:
#             self.response.set_header('Content-Type', "{};charset={}".format(self.content_type, self.charset))
#             self.response.charset = self.charset
#             callback, callback_args, callback_kwargs = self.get_callback_info()
#             body = self.handle_controller(callback, callback_args, callback_kwargs)
# 
#         except Exception as e:
#             body = self.handle_error(
#                 e,
#                 callback_args=callback_args,
#                 callback_kwargs=callback_kwargs,
#                 callback=callback
#             )
# 
#         finally:
#             self.response.body = body
#             if self.response.code == 204:
#                 self.response.headers.pop('Content-Type', None)
#                 self.response.body = None
# 
#         return self.response

