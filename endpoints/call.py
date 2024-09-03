# -*- coding: utf-8 -*-
import time
import datetime
import logging
import os
import inspect
import json
import re
import io
import sys
from collections import defaultdict
import itertools

from .compat import *
from .utils import AcceptHeader
from .exception import (
    CallError,
    VersionError,
)
from .config import environ

from datatypes import (
    HTTPHeaders as Headers,
    property as cachedproperty,
    Dirpath,
    ReflectModule,
    ReflectPath,
    DictTree,
    Profiler,
    Boolean,
    ClasspathFinder,
    NamingConvention,
)

from .compat import *
from .utils import (
    AcceptHeader,
    MimeType,
    Base64,
    Deepcopy,
    Url,
    Status,
)


logger = logging.getLogger(__name__)


class Param(object):
    """Check a value against criteria

    this tries to be as similar to python's built-in argparse as possible

    :example:

        p = Param('name', type=int, action='store_list')
        args, kwargs = p.handle(args, kwargs)

    Check .__init__ to see what you can pass into the contructor. Check the
    decorators.utils.param to see how this is used
    """
    encoding = environ.ENCODING

    def __init__(self, *names, **flags):
        """
        :param name: str, the name of the query_param
        :param **flags:
            - dest: str, the key in kwargs this param will be set into
            - type: type, a python type like `int` or `float`
            - action: str, the possible string values are:
                - "store" - the default value
                - "store_false" - set if you want default param value to be
                    True, and False only if param is passed in
                - "store_true" - opposite of store_false
                - "store_list" - set to have a value like 1,2,3 be blown up to
                    ['1', '2', '3']
                - "append" - if multiple param values should be turned into an
                    array (eg, foo=1&foo=2 would become foo=[1, 2])
                - "append_list" - it's store_list + append, so foo=1&foo=2,3
                    would become foo=[1, 2, 3]
            - default: Any, the value that should be set if the param isn't
                there, if this is callable (eg, time.time or datetime.utcnow)
                then it will be called every time this param is checked for a
                value
            - required: bool, True if param is required, default is True
            - choices: set, a set of values to be in tested against (eg, val in
                choices)
            - value: str, it's the one-off of `choices`, equivalent to
                choices=["<VALUE>"]
            - allow_empty: bool, True allows values like False, 0, '' through,
                default is False, this will also let through any empty value
                that was set via the default flag
            - max_size: int, the maximum size of the param
            - min_size: int, the minimum size of the param
            - regex: regexObject, if you would like the param to be validated
                with a regular expression, uses the re.search() method
            - help: str, a helpful description for this param
        """
        self.normalize_type(names)
        self.normalize_flags(flags)

    def handle(self, args, kwargs):
        """this is where all the magic happens, this will try and find the
        param and put its value in kwargs if it has a default and stuff"""
        if self.is_kwarg:
            kwargs = self.normalize_kwarg(kwargs)

        else:
            args = self.normalize_arg(args)

        return args, kwargs

    def normalize_flags(self, flags):
        """normalize the flags to make sure needed values are there

        after this method is called self.flags is available

        :param flags: the flags that will be normalized
        """
        flags['type'] = flags.get('type', None)
        paction = flags.get('action', 'store')
        if paction == 'store_false':
            flags['default'] = True 
            flags['type'] = bool

        elif paction == 'store_true':
            flags['default'] = False
            flags['type'] = bool

        if 'default' in flags:
            prequired = False

        else:
            prequired = flags.get('required', True)

        flags["action"] = paction
        flags["required"] = prequired

        self.flags = flags

    def normalize_type(self, names):
        """Decide if this param is an arg or a kwarg and set appropriate
        internal flags"""
        self.name = names[0]
        self.is_kwarg = False
        self.is_arg = False
        self.names = []

        try:
            # http://stackoverflow.com/a/16488383/5006 uses ask forgiveness
            # because of py2/3 differences of integer check
            self.index = int(self.name)
            self.name = ""
            self.is_arg = True

        except ValueError:
            self.is_kwarg = True
            self.names = names

    def normalize_default(self, default):
        ret = default
        if isinstance(default, dict):
            ret = dict(default)

        elif isinstance(default, list):
            ret = list(default)

        else:
            if callable(default):
                ret = default()

        return ret

    def normalize_arg(self, args):
        flags = self.flags
        index = self.index
        args = list(args)

        paction = flags['action']
        if paction not in set(['store', 'store_false', 'store_true']):
            raise RuntimeError('unsupported positional param action {}'.format(
                paction
            ))

        if 'dest' in flags:
            logger.warning("dest is ignored in positional param")

        try:
            val = args.pop(index)

        except IndexError as e:
            if flags["required"]:
                raise ValueError(
                    f"Positional param at index {index} does not exist"
                ) from e

            else:
                val = self.normalize_default(flags.get('default', None))

        try:
            val = self.normalize_val(val)

        except ValueError as e:
            raise ValueError(
                "Positional arg {} failed with {}".format(index, String(e))
            ) from e

        args.insert(index, val)

        return args

    def find_kwarg(self, names, required, default, kwargs):
        """actually try to retrieve names key from params dict

        :param names: the names this kwarg can be
        :param required: True if a name has to be found in kwargs
        :param default: the default value if name isn't found
        :param kwargs: the kwargs that will be used to find the value
        :returns: tuple, found_name, val where found_name is the actual name
            kwargs contained
        """
        val = default
        found_name = ''
        for name in names:
            if name in kwargs:
                val = kwargs[name]
                found_name = name
                break

        if not found_name and required:
            raise ValueError("required param {} does not exist".format(
                self.name
            ))

        return found_name, val

    def normalize_kwarg(self, kwargs):
        flags = self.flags
        name = self.name

        try:
            pdefault = self.normalize_default(flags.get('default', None))
            prequired = flags['required']
            dest_name = flags.get('dest', name)

            has_val = True
            found_name, val = self.find_kwarg(
                self.names,
                prequired,
                pdefault,
                kwargs
            )
            if found_name:
                # we are going to replace found_name with dest_name
                kwargs.pop(found_name)

            else:
                # we still want to run a default value through normalization
                # but if we didn't find a value and don't have a default, don't
                # set any value
                has_val = 'default' in flags

            if has_val:
                    kwargs[dest_name] = self.normalize_val(val)

        except ValueError as e:
            raise ValueError(
                "{} failed with {}".format(name, String(e))
            ) from e

        return kwargs

    def normalize_val(self, val):
        """This will take the value and make sure it meets expectations

        :param val: the raw value pulled from kwargs or args
        :returns: val that has met all param checks
        :raises: ValueError if val fails any checks
        """
        flags = self.flags
        paction = flags['action']
        ptype = flags['type']
        pchoices = set(flags.get('choices', []))
        allow_empty = flags.get('allow_empty', False)
        min_size = flags.get('min_size', None)
        max_size = flags.get('max_size', None)
        regex = flags.get('regex', None)

        if paction in set(['store_list']):
            if isinstance(val, list) and len(val) > 1:
                raise ValueError("too many values for param")

            if isinstance(val, basestring):
                val = list(val.split(','))

            else:
                val = list(val)

        elif paction in set(['append', 'append_list']):
            if not isinstance(val, list):
                val = [val]

            if paction == 'append_list':
                vs = []
                for v in val:
                    if isinstance(v, basestring):
                        vs.extend(String(v).split(','))
                    else:
                        vs.append(v)

                val = vs

        else:
            if paction not in set(['store', 'store_false', 'store_true']):
                raise RuntimeError('unknown param action {}'.format(paction))

        if regex:
            failed = False
            if isinstance(regex, basestring):
                if not re.search(regex, val): failed = True
            else:
                if not regex.search(val): failed = True

            if failed:
                raise ValueError("param failed regex check")

        if ptype:
            if isinstance(val, list) and ptype != list:
                val = list(map(ptype, val))

            else:
                if isinstance(ptype, type):
                    if issubclass(ptype, bool):
                        val = Boolean(val)

                    elif issubclass(ptype, (bytes, bytearray)):
                        charset = flags.get("encoding", self.encoding)
                        val = ptype(ByteString(val, charset))

                    elif issubclass(ptype, basestring):
                        charset = flags.get("encoding", self.encoding)
                        val = ptype(String(val, charset))

                    else:
                        val = ptype(val)

                else:
                    val = ptype(val)


        if "value" in flags:
            pchoices.add(flags["value"])

        if pchoices:
            if isinstance(val, list) and ptype != list:
                for v in val:
                    if v not in pchoices:
                        raise ValueError(
                            "param value {} not in choices {}".format(
                                v,
                                pchoices
                            )
                        )

            else:
                if val not in pchoices:
                    raise ValueError(
                        "param value {} not in choices {}".format(
                            val,
                            pchoices
                        )
                    )

        if not allow_empty and val is not False and not val:
            if 'default' not in flags:
                raise ValueError("param was empty")

        if min_size is not None:
            failed = False
            if isinstance(val, (int, float)):
                if val < min_size:
                    failed = True

            else:
                if len(val) < min_size:
                    failed = True

            if failed:
                raise ValueError("param was smaller than {}".format(min_size))

        if max_size is not None:
            failed = False
            if isinstance(val, (int, float)):
                if val > max_size:
                    failed = True

            else:
                if len(val) > max_size:
                    failed = True

            if failed:
                raise ValueError("param was bigger than {}".format(max_size))

        return val


class Pathfinder(ClasspathFinder):
    """Internal class used by Router. This holds the tree of all the
    controllers so Router can resolve the path"""
    def _get_node_module_info(self, key, **kwargs):
        """Handle normalizing each module key to kebabcase"""
        key = NamingConvention(key).kebabcase()
        return super()._get_node_module_info(key, **kwargs)

    def _get_node_class_info(self, key, **kwargs):
        """Handle normalizing each class key. If it's the destination key
        then it will use the controller class's .get_name method for the
        key. If it's a waypoint key then it will normalize to kebab case
        """
        if "class" in kwargs:
            if key in self.kwargs["ignore_class_keys"]:
                key = None
                keys = kwargs["keys"]

            else:
                key = kwargs["class"].get_name()
                keys = kwargs["keys"] + [key]

            logger.debug(
                "Registering path: /{} to controller: {}:{}".format(
                    "/".join(keys),
                    kwargs["class"].__module__,
                    kwargs["class"].__qualname__
                )
            )

        else:
            key = NamingConvention(key).kebabcase()

        key, value = super()._get_node_class_info(key, **kwargs)

        if "class" in value:
            value["method_names"] = value["class"].get_method_names()

        return key, value


class Router(object):
    """Handle Controller caching and routing

    This handles caching and figuring out the route for each incoming request
    """
    def __init__(self, controller_prefixes=None, paths=None, **kwargs):
        """Create a Router instance, all caching is done in this method so if
        this returns then all controllers will be cached and ready to be
        requested

        It loads the controllers using the module prefixes or paths and then
        loads all the controllers from Controller.controller_classes which is
        populated by Controller.__init_subclass__ when a new child class is
        loaded into memory

        :param controller_prefixes: list, the controller module prefixes to use
            to find controllers to answer requests (eg, if you pass in `foo.bar`
            then any submodules will be stripped of `foo.bar` and use the rest
            of the module path to figure out the full requestable path, so 
            `foo.bar.che.Boo` would have `che/boo` as its path
        :param paths: list, the paths to check for controllers. This looks for
            a module named `controllers` in the paths, the first found module
            wins
        :param **kwargs:
            - controller_class: Controller, the child class to use to find
                controller classes
        """
        self.controller_class = kwargs.get(
            "controller_class",
            Controller
        )

        self.pathfinder_class = kwargs.get(
            "pathfinder_class",
            Pathfinder,
        )

        self.controller_modules = self.find_modules(
            prefixes=controller_prefixes,
            paths=paths,
            **kwargs
        )

        self.controller_method_names = {}
        self.pathfinder = self.create_pathfinder(**kwargs)

    def find_modules(self, prefixes, paths, **kwargs):
        if not paths and not self.controller_class.controller_classes:
            paths = [Dirpath.cwd()]

        return self.pathfinder_class.find_modules(
            prefixes,
            paths,
            kwargs.get("autodiscover_name", environ.AUTODISCOVER_NAME)
        )

    def create_pathfinder(self, **kwargs):
        """Internal method. Create the tree that will be used to resolve a
        requested path to a found controller

        The class fallback is the name of the default controller class, it
        defaults to `Default` and should probably never be changed

        :returns: DictTree, basically a dictionary of dictionaries where each
            key represents a part of a path, the final key will contain the
            controller class that can answer a request
        """
        pathfinder = self.pathfinder_class(
            list(self.controller_modules.keys()),
            ignore_class_keys=set(["Default"])
        )

        controller_classes = self.controller_class.controller_classes
        for controller_class in controller_classes.values():
            if not controller_class.is_private():
                pathfinder.add_class(controller_class)

        return pathfinder

    def create_controller(self, request, response, **kwargs):
        """Create a controller to handle the request

        :param request: Request
        :param response: Response
        :returns: Controller
        """
        request.controller_info = self.find_controller_info(
            request,
            **kwargs
        )

        return request.controller_info['class'](
            request,
            response,
            **kwargs
        )

    def find_controller(self, path_args):
        """Where all the magic happens, this takes a requested path_args and
        checks the internal tree to find the right path or raises a TypeError
        if the path can't be resolved

        :param path_args: list[str], so path `/foo/bar/che` would be passed to
            this method as `["foo", "bar", "che"]`
        :returns: tuple[Controller, list[str], dict[str, Any]], a tuple of
            controller_class, controller_args, and node value
        """
        keys = list(path_args)
        controller_args = []
        controller_class = None
        value = {}
        pathfinder = self.pathfinder

        while not controller_class:
            value = pathfinder.get(keys, {})
            if "class" in value:
                controller_class = value["class"]

            else:
                if keys:
                    controller_args.insert(0, keys.pop(-1))

                else:
                    raise TypeError(
                        "Unknown controller with path /{}".format(
                            "/".join(path_args),
                        )
                    )

        return controller_class, controller_args, value

    def find_controller_info(self, request, **kwargs):
        """returns all the information needed to create a controller and handle
        the request

        This is where all the routing magic happens, this takes the
        request.path and gathers the information needed to turn that path into
        a Controller

        we always translate an HTTP request using this pattern:

            METHOD /module/class/args?kwargs

        :param request: Request
        :param **kwargs:
        :returns: dict
        """
        ret = {}

        logger.debug("Compiling Controller info using path: {}".format(
            request.path
        ))

        controller_class, controller_args, value = self.find_controller(
            request.path_args
        )

        ret["method_args"] = controller_args

        # we merge the leftover path args with the body kwargs
        ret['method_args'].extend(request.body_args)

        ret['method_kwargs'] = request.kwargs

        if method_names := value["method_names"].get(request.method.upper()):
            ret['method_names'] = method_names

        elif method_names := value["method_names"].get("ANY"):
            ret['method_names'] = method_names

        else:
            if len(ret["method_args"]) > 0:
                # if we have method args and we don't have a method to even
                # answer the request it should be a 404 since the path is
                # invalid
                raise TypeError(
                    "Could not find a {} method for path {}".format(
                        request.method,
                        request.path,
                    )
                )

            else:
                # https://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1
                # and 501 (Not Implemented) if the method is unrecognized or
                # not implemented by the origin server
                raise NotImplementedError(
                    "{} {} not implemented".format(
                        request.method,
                        request.path
                    )
                )

        ret['method_name'] = "handle"

        ret["module_name"] = controller_class.__module__
        ret['module_path'] = "/".join(value["module_keys"])

        ret["class"] = controller_class
        ret['class_name'] = ret["class"].__name__
        ret['class_path'] = "/".join(itertools.chain(
            value["module_keys"],
            value["class_keys"]
        ))

        return ret


class Controller(object):
    """This is the interface for a Controller sub class

    All your controllers MUST extend this base class, since it ensures a proper
    interface :)

    To activate a new endpoint, just add a module on your PYTHONPATH
    controller_prefix that has a class that extends this class, and then
    defines at least one http method (like GET or POST), so if you wanted to
    create the endpoint `/foo/bar` (with controller_prefix `che`), you would
    just need to:

    :Example:
        # che/foo.py
        import endpoints

        class Bar(endpoints.Controller):
            def GET(self, *args, **kwargs):
                return "you just made a GET request to /foo/bar"

    As you support more methods, like POST and PUT, you can just add POST() and
    PUT() methods to your `Bar` class and `Bar` will support those http
    methods.

    If you would like to create a base controller that other controllers will
    extend and don't want that controller to be picked up by reflection, just
    start the classname with an underscore (eg `_Foo`) or end it with a
    "Controller" suffix (eg, `FooController`). See .is_private docblock for
    examples.

    The default routing converts underscores and camelcase names to be
    separated by dashes. See .get_name docblock for examples.
    """
    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    private = False
    """set this to True if the controller is not designed to be requested"""

    cors = True
    """Activates CORS support, http://www.w3.org/TR/cors/"""

    controller_classes = {}
    """Holds all the controller classes that have been loaded into memory, the
    classpath is the key and the class object is the value, see
    __init_subclass__"""

    @cachedproperty(cached="_encoding")
    def encoding(self):
        """the response charset of this controller"""
        req = self.request
        encoding = req.accept_encoding
        return encoding if encoding else environ.ENCODING

    @cachedproperty(cached="_content_type")
    def content_type(self):
        """the response content type this controller will use"""
        req = self.request
        content_type = req.accept_content_type
        return content_type if content_type else environ.RESPONSE_CONTENT_TYPE

    @classmethod
    def is_private(cls):
        """Return True if this class is considered private and is not
        requestable

        This is useful if you want to have certain parent controllers that
        shouldn't actually be able to handle requests

        :Example:
            class _Foo(Controller):
                # this class is private because it starts with an underscore
                pass

            _Foo.is_private() # True

            class FooController(Controller):
                # this class is private because it ends with Controller
                pass

            FooController.is_private() # True

            class Foo(Controller):
                # this class is private because it set the .private class
                # property
                private = True

            Foo.is_private() # True

        :returns: bool, True if private/internal, False if requestable
        """
        return (
            cls.private
            or cls.__name__.startswith("_")
            or cls.__name__.endswith("Controller")
        )

    @classmethod
    def get_name(cls):
        """Get the controller name.

        This is used in Pathfinder to decide the path part for this controller

        :Example:
            # foo_bar module
            class CheBaz(Controller):
                # This controller would answer /foo-bar/che-baz requests
                pass

        If you would like your request to have an extension, you can do that
        by using an underscore:

        :Example:
            class FooBar_txt(Controller):
                # This controller will satisfy foo-bar.txt requests
                pass

            class Robots_txt(Controller): pass
            print(Robots.get_name()) # "robots.txt"

        :returns: str, the basename in kebab case, with a ".ext" if
            applicable
        """
        name = cls.__name__

        if not name.startswith("_"):
            parts = cls.__name__.split("_", 1)

            if len(parts) == 1:
                name = NamingConvention(parts[0]).kebabcase()

            elif len(parts) == 2:
                name = NamingConvention(parts[0]).kebabcase()
                if parts[1]:
                    name = f"{name}.{parts[1].lower()}"

            else:
                raise ValueError(
                    "Controller class names can only have one underscore,"
                    f" {name} has {len(parts)} underscores"
                )

        return name

    @classmethod
    def get_method_names(cls):
        """An HTTP method (eg GET or POST) needs to be handled by a controller
        class. So a controller can have a method named GET and that will be
        called when GET <PATH-TO-CONTROLLER> is called. But wait, there's more,
        there can actually be multiple methods defined that all start with
        <HTTP-METHOD> (eg, GET_1, GET_2, etc)

        Although you can define any http methods (a method is valid if it is
        all uppercase), here is a list of rfc approved http request methods:

            http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

        :returns: dict[str, list[str]], the keys are the HTTP method and the
            values are all the method names that satisfy that HTTP method.
            these method names will be in alphabetical order to make it so they
            can always be checked in the same order
        """
        method_names = defaultdict(set)

        members = inspect.getmembers(cls)
        for member_name, member in members:
            prefix, sep, postfix = member_name.partition("_")
            if prefix.isupper() and callable(member):
                if prefix != "OPTIONS" or cls.cors:
                    method_names[prefix].add(member_name)

        # after compiling them put them in alphabetical order
        for prefix in method_names.keys():
            method_names[prefix] = list(method_names[prefix])
            method_names[prefix].sort()

        return method_names

    def __init__(self, request, response, **kwargs):
        self.request = request
        self.response = response
        self.logger = self.create_logger(request, response)

    def __init_subclass__(cls):
        """When a child class is loaded into memory it will be saved into
        .controller_classes, this way every controller class knows about all
        the other classes, this is the method that makes a lot of the magic
        of endpoints possible

        https://peps.python.org/pep-0487/
        """
        super().__init_subclass__()
        cls.controller_classes[f"{cls.__module__}:{cls.__qualname__}"] = cls

    def prepare_response(self):
        """Called at the beginning of the handle() call, use to prepare the
        response instance with defaults that can be overridden in the
        controller's actual http handle method"""
        res = self.response

        res.encoding = self.encoding

        if content_type := self.content_type:
            res.set_header("Content-Type", "{};charset={}".format(
                content_type,
                res.encoding
            ))

    def handle_origin(self, origin):
        """Check the origin and decide if it is valid

        :param origin: string, this can be empty or None, so you'll need to
            handle the empty case if you are overriding this
        :returns: bool, True if the origin is acceptable, False otherwise
        """
        return True

    def handle_cors(self):
        """This will set the headers that are needed for any cors request
        (OPTIONS or real) """
        req = self.request
        origin = req.get_header('origin')
        if self.handle_origin(origin):
            if origin:
                # your server must read the value of the request's Origin
                # header and use that value to set Access-Control-Allow-Origin,
                # and must also set a Vary: Origin header to indicate that some
                # headers are being set dynamically depending on the origin.
                # https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS/Errors/CORSMissingAllowOrigin
                # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Origin
                self.response.set_header('Access-Control-Allow-Origin', origin)
                self.response.set_header('Vary', "Origin")

        else:
            # RFC6455 - If the origin indicated is unacceptable to the server,
            # then it SHOULD respond to the WebSocket handshake with a reply
            # containing HTTP 403 Forbidden status code.
            # https://stackoverflow.com/q/28553580/5006
            raise CallError(403)

    async def OPTIONS(self, *args, **kwargs):
        """Handles CORS requests for this controller

        if self.cors is False then this will raise a 405, otherwise it sets
        everything necessary to satisfy the request in self.response
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

    def get_access_token(self, *args, **kwargs):
        """return an Oauth 2.0 Bearer access token if it can be found

        This was moved here from Request.access_token on 2024-04-24 because
        the controller can mess with the controller params and so it didn't
        make sense to have the controller decorators try to pull the
        access token from the request when the controller could've
        customized it in some way

        :param *args: the controller args that will be passed to the
            controller's handler method
        :param **kwargs: the controller kwargs that will be passed to the
            controller's handler method
        :returns: str, the access token
        """
        access_token = self.request.get_auth_bearer()

        if not access_token:
            access_token = kwargs.get("access_token", "")

        return access_token

    def get_client_tokens(self, *args, **kwargs):
        """try and get Oauth 2.0 client id and secret first from basic auth
        header, then from GET or POST parameters

        see .get_access_token for why this method is here instead of on
        the Request instance

        :param *args: the controller args that will be passed to the
            controller's handler method
        :param **kwargs: the controller kwargs that will be passed to the
            controller's handler method
        :returns: tuple[str, str], client_id, client_secret
        """
        client_id, client_secret = self.request.get_auth_basic()

        if not client_id:
            client_id = kwargs.get(
                "client_id",
                ""
            )

        if not client_secret:
            client_secret = kwargs.get(
                "client_secret",
                ""
            )

        return client_id, client_secret

    async def get_controller_params(self, *controller_args, **controller_kwargs):
        """Called right before the controller's requested method is called
        (eg GET, POST). It's meant for children controllers to be able to
        customize the arguments that are passed into the method

        This is ran before any decorators

        :param *controller_args:
        :param **controller_kwargs:
        :returns: tuple[tuple, dict], whatever is returned from this method is
            passed into the controller request method as *args, **kwargs
        """
        return controller_args, controller_kwargs

    async def get_response_body(self, body):
        """Called right after the controller's request method (eg GET, POST)
        returns with the body that it returned

        This is called after all similar decorators methods, it's the last
        stop before body is sent to the client by the interface

        NOTE -- this is called before Response.body is set, the value returned
        from this method will be set in Response.body

        :param body: Any, the value returned from the requested method before
            it is set into Response.body
        :return: Any
        """
        return body

    async def handle(self, *controller_args, **controller_kwargs):
        """handles the request and sets the response

        This should set any response information directly onto self.response

        NOTE -- This method relies on .request.controller_info being populated

        :param controller_method_names: list[str], a list of controller
            method names to be ran, if one of them succeeds then the request is
            considered successful, if all raise an error than an error will be
            raised
        :param *controller_args: tuple, the path arguments that will be passed
            to the request handling method (eg, GET, POST)
        :param **controller_kwargs: dict, the query and body params merged
            together
        """
        if self.cors:
            self.handle_cors()

        self.prepare_response()

        req = self.request
        res = self.response
        exceptions = defaultdict(list)

        controller_method_names = req.controller_info["method_names"]

        controller_args, controller_kwargs = await self.get_controller_params(
            *controller_args,
            **controller_kwargs
        )

        for controller_method_name in controller_method_names:
            controller_method = getattr(self, controller_method_name)

            # we update the controller info so error handlers know what
            # method failed, which is useful for determining how to handle
            # the error
            req.controller_info["method_name"] = controller_method_name
            req.controller_info["method"] = controller_method

            try:
                self.logger.debug(
                    "Request Controller method: {}:{}.{}".format(
                        req.controller_info['module_name'],
                        req.controller_info['class_name'],
                        controller_method_name
                    )
                )

                body = controller_method(
                    *controller_args,
                    **controller_kwargs
                )

                while inspect.iscoroutine(body):
                    body = await body

                exceptions = None
                break

            except Exception as e:
                exceptions[e.__class__.__name__].append(e)

        if exceptions:
            if len(exceptions) == 1:
                raise list(exceptions.values())[0][0]

            else:
                raise CallError(
                    400,
                    "Could not find a method to satisfy {} {}".format(
                        req.method,
                        req.path
                    )
                )

        else:
            res.set_body(await self.get_response_body(body))

    async def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        pass

    def create_logger(self, request, response):
        # we use self.logger and set the name to endpoints.call.module.class so
        # you can filter all controllers using endpoints.call, filter all
        # controllers in a certain module using endpoints.call.module or just a
        # specific controller using endpoints.call.module.class
        logger_name = logger.name
        module_name = self.__class__.__module__
        class_name = self.__class__.__name__
        return logging.getLogger("{}.{}.{}".format(
            logger_name,
            module_name,
            class_name,
        ))

    def log_start(self, start):
        """log all the headers and stuff at the start of the request"""
        if not self.logger.isEnabledFor(logging.INFO):
            return

        try:
            req = self.request
            if uuid := getattr(req, "uuid", ""):
                uuid += " "

            self.logger.info("Request {}{} {}{}".format(
                uuid,
                req.method,
                req.path,
                f"?{String(req.query)}" if req.query else "",
            ))

            self.logger.info("Request {}date: {}".format(
                uuid,
                datetime.datetime.utcfromtimestamp(start).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                ),
            ))

            ip = req.ip
            if ip:
                self.logger.info("Request {}IP address: {}".format(uuid, ip))

            if 'authorization' in req.headers:
                self.logger.info('Request {}auth: {}'.format(
                    uuid,
                    req.headers['authorization']
                ))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            for k, v in req.headers.items():
                if k not in ignore_hs:
                    self.logger.info(
                        "Request {}header {}: {}".format(uuid, k, v)
                    )

            self.log_start_body()

        except Exception as e:
            self.logger.warn(e, exc_info=True)

    def log_start_body(self):
        """Log the request body

        this is separate from log_start so it can be easily overridden in
        children
        """
        if not self.logger.isEnabledFor(logging.DEBUG):
            return

        req = self.request
        if uuid := getattr(req, "uuid", ""):
            uuid += " "

        try:
            if req.has_body():
                body_args = req.body_args
                body_kwargs = req.body_kwargs

                if body_args or body_kwargs:
                    self.logger.debug(
                        "Request {}body args: {}, body kwargs: {}".format(
                            uuid,
                            req.body_args,
                            req.body_kwargs
                        )
                    )

                else:
                    self.logger.debug(
                        "Request {}body: {}".format(
                            uuid,
                            req.body,
                        )
                    )

            elif req.should_have_body():
                self.logger.debug(
                    "Request {}body: <EMPTY>".format(uuid)
                )

        except Exception:
            self.logger.debug(
                "Request {}body raw: {}".format(uuid, req.body)
            )
            raise

    def log_stop(self, start):
        """log a summary line on how the request went"""
        if not self.logger.isEnabledFor(logging.INFO):
            return

        res = self.response
        req = self.request
        if uuid := getattr(req, "uuid", ""):
            uuid += " "

        for k, v in res.headers.items():
            self.logger.info("Response {}header {}: {}".format(uuid, k, v))

        stop = time.time()

        self.logger.info(
            "Response {}{} {} in {} for Request {} {}{}".format(
                uuid,
                self.response.code,
                self.response.status,
                Profiler.get_output(start, stop),
                req.method,
                req.path,
                f"?{String(req.query)}" if req.query else "",
            )
        )


class Call(object):
    headers_class = Headers

    body = None
    """Any, Holds the body for this instance"""

    def __init__(self):
        self.headers = self.headers_class()

    def has_header(self, header_name):
        """return true if the header is set"""
        return header_name in self.headers

    def set_headers(self, headers):
        """replace all headers with passed in headers"""
        self.headers = Headers(headers)

    def add_headers(self, headers, **kwargs):
        self.headers.update(headers, **kwargs)

    def set_header(self, header_name, val):
        self.headers[header_name] = val

    def add_header(self, header_name, val, **params):
        self.headers.add_header(header_name, val, **params)

    def get_header(self, header_name, default_val=None, allow_empty=True):
        """try as hard as possible to get a a response header of header_name,
        return default_val if it can't be found"""
        v = self.headers.get(header_name, default_val)
        if v:
            return v

        else:
            if not allow_empty:
                return default_val

    def find_header(self, header_names, default_val=None, allow_empty=True):
        """given a list of headers return the first one you can, default_val if
        you don't find any

        :param header_names: list, a list of headers, first one found is
            returned
        :param default_val: mixed, returned if no matching header is found
        :returns: mixed, the value of the header or default_val
        """
        ret = default_val
        for header_name in header_names:
            if self.has_header(header_name):
                ret = self.get_header(header_name, default_val)
                if ret or allow_empty:
                    break

        if not ret and not allow_empty:
            ret = default_val

        return ret

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        u = Url(query=query)
        return u.query_kwargs

    def copy(self):
        """nice handy wrapper around the deepcopy"""
        return self.__deepcopy__()

    def __deepcopy__(self, memodict=None):
        memodict = memodict or {}

        memodict.setdefault("controller_info", None)
        memodict.setdefault("raw_request", None)
        memodict.setdefault("body", getattr(self, "body", None))

        #return Deepcopy(ignore_private=True).copy(self, memodict)
        return Deepcopy().copy(self, memodict)

    def is_json(self):
        return self.headers.is_json()


class Request(Call):
    '''
    common interface that endpoints uses to decide what to do with the incoming
    request

    an instance of this class is used by the endpoints Call instance to decide
    where endpoints should route requests, so, many times, you'll need to write
    a glue function that takes however your request data is passed to Python
    and convert it into a Request instance that endpoints can understand

    properties:
        * headers -- a dict of all the request headers
        * path -- the /path/part/of/the/url
        * path_args -- tied to path, it's path, but divided by / so all the
            path bits are returned as a list
        * query -- the ?name=val portion of a url
        * query_kwargs -- tied to query, the values in query but converted to a
            dict {name: val}
    '''
    raw_request = None
    """the original raw request that was filtered through one of the interfaces
    """

    method = None
    """the http method (GET, POST)"""

    controller_info = None
    """will hold the controller information for the request, populated from the
    Call"""

    @cachedproperty(cached="_uuid")
    def uuid(self):
        # if there is an X-uuid header then set uuid and send it down
        # with every request using that header
        # https://stackoverflow.com/questions/18265128/what-is-sec-websocket-key-for
        uuid = None

        # first try and get the uuid from the body since javascript has limited
        # capability of setting headers for websockets
        kwargs = self.kwargs
        if "uuid" in kwargs:
            uuid = kwargs["uuid"]

        # next use X-UUID header, then the websocket key
        if not uuid:
            uuid = self.find_header(["X-UUID", "Sec-Websocket-Key"])

        return uuid or ""

    @cachedproperty(cached="_accept_content_type")
    def accept_content_type(self):
        """Return the requested content type

        https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

        :returns: string, empty if a suitable content type wasn't found, this
            will only check the first accept content type and then only if that
            content type has no wildcards
        """
        v = ""
        accept_header = self.get_header('accept', "")
        if accept_header:
            a = AcceptHeader(accept_header)
            for mt in a:
                # we only care about the first value, and only if it has no
                # wildcards
                if "*" not in mt[0]:
                    v = "/".join(mt[0])
                break

        return v

    @cachedproperty(cached="_accept_encoding")
    def accept_encoding(self):
        """The encoding the client requested the response to use"""
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Charset
        ret = ""
        accept_encoding = self.get_header("Accept-Charset", "")
        if accept_encoding:
            bits = re.split(r"\s+", accept_encoding)
            bits = bits[0].split(";")
            ret = bits[0]
        return ret

    @cachedproperty(cached="_encoding")
    def encoding(self):
        """the character encoding of the request, usually only set in POST type
        requests"""
        encoding = None
        ct = self.get_header('content-type')
        if ct:
            ah = AcceptHeader(ct)
            if ah.media_types:
                encoding = ah.media_types[0][2].get("charset", None)

        return encoding

    @cachedproperty(read_only="_ips")
    def ips(self):
        """return all the possible ips of this request, this will include
        public and private ips"""
        r = []
        names = ['X_FORWARDED_FOR', 'CLIENT_IP', 'X_REAL_IP', 'X_FORWARDED', 
            'X_CLUSTER_CLIENT_IP', 'FORWARDED_FOR', 'FORWARDED', 'VIA',
            'REMOTE_ADDR'
        ]

        for name in names:
            vs = self.get_header(name, '')
            if vs:
                r.extend(map(lambda v: v.strip(), vs.split(',')))

        return r

    @cachedproperty(read_only="_ip")
    def ip(self):
        """return the public ip address"""
        r = ''

        # this was compiled from here:
        # https://github.com/un33k/django-ipware
        # http://www.ietf.org/rfc/rfc3330.txt (IPv4)
        # http://www.ietf.org/rfc/rfc5156.txt (IPv6)
        # https://en.wikipedia.org/wiki/Reserved_IP_addresses
        format_regex = re.compile(r'\s')
        ip_regex = re.compile(r'^(?:{})'.format(r'|'.join([
            r'0\.', # reserved for 'self-identification'
            r'10\.', # class A
            r'169\.254', # link local block
            r'172\.(?:1[6-9]|2[0-9]|3[0-1])\.', # class B
            r'192\.0\.2\.', # documentation/examples
            r'192\.168', # class C
            r'255\.{3}', # broadcast address
            r'2001\:db8', # documentation/examples
            r'fc00\:', # private
            r'fe80\:', # link local unicast
            r'ff00\:', # multicast
            r'127\.', # localhost
            r'\:\:1' # localhost
        ])))

        ips = self.ips
        for ip in ips:
            if not format_regex.search(ip) and not ip_regex.match(ip):
                r = ip
                break

        return r

    @cachedproperty(cached="_host")
    def host(self):
        """return the request host"""
        return self.get_header("host")

    @cachedproperty(cached="_scheme")
    def scheme(self):
        """return the request scheme (eg, http, https)"""
        return "http"

    @cachedproperty(cached="_port")
    def port(self):
        """return the server port"""
        _, port = Url.split_hostname_from_port(self.host)
        return port

    @property
    def url(self):
        """return the full request url as an Url() instance"""
        scheme = self.scheme
        host = self.host
        path = self.path
        query = self.query
        port = self.port

        # normalize the port
        hostname, host_port = Url.split_hostname_from_port(host)
        if host_port:
            port = host_port

        class_path = ""
        module_path = ""
        if self.controller_info:
            class_path = self.controller_info.get("class_path", "")
            module_path = self.controller_info.get("module_path", "")

        u = Url(
            scheme=scheme,
            hostname=hostname,
            path=path,
            query=query,
            port=port,
            controller_class_path=class_path,
            controller_module_path=module_path
        )
        return u

    @cachedproperty(cached="_path")
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        self._path = ''
        path_args = self.path_args
        path = "/{}".format("/".join(path_args))
        return path

    @cachedproperty(cached="_path_args")
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        self._path_args = []
        path = self.path
        path_args = list(filter(None, path.split('/')))
        return path_args

    @cachedproperty(cached="_query")
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)
        """
        self._query = query = ""

        query_kwargs = self.query_kwargs
        if query_kwargs: query = urlencode(query_kwargs, doseq=True)
        return query

    @cachedproperty(cached="_query_kwargs")
    def query_kwargs(self):
        """{foo: bar, baz: che}"""
        self._query_kwargs = query_kwargs = {}
        query = self.query
        if query: query_kwargs = self._parse_query_str(query)
        return query_kwargs

    @property
    def kwargs(self):
        """combine GET and POST params to be passed to the controller"""
        kwargs = dict(self.query_kwargs)
        kwargs.update(self.body_kwargs or {})
        return kwargs

    def __init__(self):
        # Holds the parsed positional arguments parsed from .body
        self.body_args = []

        # Holds the parsed keyword arguments parsed from .body
        self.body_kwargs = {}

        super().__init__()

    def get(self, name="", default_val=None, **kwargs):
        """Get a value

        Order of preference: body, query, header

        :param name: str, the name of the query or body key to check, a header
            named "X-<NAME>" will also be checked if name is not found in the
            body or query parameters
        :param default_val: Any, the default value if the name isn't found
            anywhere
                * names: list[str], want to check multiple names instead of
                    just one name?
                * header_names: list[str], similar to names, check multiple
                    header names in one call
                * query_kwargs: dict, children can customize query kwargs so
                    this allows them to be passed in so children's internal
                    methods can customize behavior
                * body_kwargs: dict, same as query_kwargs
        :returns: Any
        """
        header_names = kwargs.get("header_names", [])
        if v := kwargs.get("header_name", None):
            header_names.append(header_name)

        names = kwargs.get("names", [])
        if name:
            names.append(name)

        kwargs = {}
        if query_kwargs := kwargs.get("query_kwargs", {}):
            kwargs = query_kwargs

        if body_kwargs := kwargs.get("body_kwargs", {}):
            kwargs.update(body_kwargs)

        if not kwargs:
            kwargs = self.kwargs

        for name in names:
            if v := kwargs.get(name, None):
                return v

            header_names.append(f"X-{name}")

        return self.find_header(header_names, default_val)

    def version(self, content_type="*/*"):
        """by default, versioning is based off of this post 
        http://urthen.github.io/2013/05/09/ways-to-version-your-api/
        https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

        This can be extended to implement versioning in any other way though,
        this is used with the @version decorator

        :param content_type: string, the content type you want to check version
            info, by default this checks all content types, which is probably
            what most want, since if you're doing accept header versioning
            you're probably only passing up one content type
        :returns: str, the found version
        """
        v = ""
        accept_header = self.get_header('accept', "")
        if accept_header:
            a = AcceptHeader(accept_header)
            for mt in a.filter(content_type):
                v = mt[2].get("version", "")
                if v:
                    break

        return v

    def is_method(self, method):
        """return True if the request method matches the passed in method

        :param method: str, something like "GET" or "POST"
        :return: bool
        """
        return self.method.upper() == method.upper()

    def is_get(self):
        """Return true if the request is a GET request"""
        return self.is_method("GET")

    def is_post(self):
        """Return True if the request is a POST request"""
        return self.is_method("POST")

    def set_body(self, body, body_args=None, body_kwargs=None):
        """Set the body onto this instance

        Interfaces are responsible for parsing the body so should always pass
        body_args and body_kwargs

        :param body: Any, the raw body for the request
        :param body_args: list, any parsed positional arguments from `body`
        :param body_kwargs: dict, any parsed keyword arguments from `body`
        """
        self.body = body
        self.body_args = body_args or []
        self.body_kwargs = body_kwargs or {}

    def has_body(self):
        return True if self.body else False

    def should_have_body(self):
        """Returns True if the request should normally have a body"""
        return self.method.upper() in set(["POST", "PATCH", "PUT"])

    def get_auth_bearer(self):
        """return the bearer token in the authorization header if it exists"""
        access_token = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^Bearer\s+(\S+)$", auth_header, re.I)
            if m: access_token = m.group(1)

        return access_token

    def get_auth_basic(self):
        """return the username and password of a basic auth header if it exists
        """
        username = ''
        password = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^Basic\s+(\S+)$", auth_header, re.I)
            if m:
                auth_str = Base64.decode(m.group(1))
                username, password = auth_str.split(':', 1)

        return username, password

    def get_auth_scheme(self):
        """The authorization header is defined like:

            Authorization = credentials
            credentials = auth-scheme TOKEN_VALUE
            auth-scheme = token

        which roughly translates to:

            Authorization: token TOKEN_VALUE

        This returns the token part of the auth header's value

        :returns: string, the authentication scheme (eg, Bearer, Basic)
        """
        scheme = ""
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^(\S+)\s+", auth_header)
            if m:
                scheme = m.group(1)
        return scheme

    def is_auth(self, scheme):
        """Return True if scheme matches the authorization scheme

        :Example:
            # Authorization: Basic FOOBAR
            request.is_auth("basic") # True
            request.is_auth("bearer") # False
        """
        ret = False
        scheme = scheme.lower()
        auth_scheme = self.get_auth_scheme().lower()

        if scheme == auth_scheme:
            ret = True

        else:
            token_schemes = set(["bearer", "token", "access"])
            client_schemes = set(["basic", "client"])
            if auth_scheme in token_schemes:
                ret = scheme in token_schemes

            elif auth_scheme in client_schemes:
                ret = scheme in client_schemes

        return ret


class Response(Call):
    """The Response object, every request instance that comes in will get a
    corresponding Response instance that answers the Request.

    an instance of this class is used to create the text response that will be
    sent back to the client

    Request has a ._body and .body, the ._body property is the raw value that
    is returned from the Controller method that handled the request, the .body
    property is a string that is ready to be sent back to the client, so it is
    _body converted to a string. The reason _body isn't name body_kwargs is
    because _body can be almost anything (not just a dict)
    """
    encoding = ""

    error = None
    """Will contain any raised exception"""

    @cachedproperty(cached="_code", onget=False)
    def code(self):
        """the http status code to return to the client, by default, 200 if a
        body is present otherwise 204"""
        if self.has_body():
            code = 200
        else:
            code = 204

        return code

    @code.setter
    def code(self, v):
        self._code = v
        try:
            del(self.status)

        except AttributeError:
            pass

    @cachedproperty(cached="_code")
    def status_code(self):
        return self.code

    @cachedproperty(cached="_status", onget=False)
    def status(self):
        """The full http status (the first line of the headers in a server
        response)"""
        return Status(self.code)

    def set_body(self, body):
        """Set the body onto this instance

        :param body: Any, the raw body for the response
        """
        self.body = body
        if self.is_file():
            filepath = getattr(body, "name", "")
            if filepath:
                mt = MimeType.find_type(filepath)
                filesize = os.path.getsize(filepath)
                self.set_header("Content-Type", mt)
                self.set_header("Content-Length", filesize)
                logger.debug(" ".join([
                    f"Response body set to file: \"{filepath}\"",
                    f"with mimetype: \"{mt}\"",
                    f"and size: {filesize}",
                ]))

            else:
                logger.warn(
                    "Response body is a filestream with no .filepath property"
                )

    def has_body(self):
        """return True if there is an actual response body"""
        return self.body is not None

    def is_file(self):
        """return True if the response body is a file pointer"""
        # http://stackoverflow.com/questions/1661262/check-if-object-is-file-like-in-python
        return isinstance(self.body, io.IOBase)
        #return hasattr(self._body, "read") if self.has_body() else False

    def is_success(self):
        """return True if this response is considered a "successful" response
        """
        code = self.code
        return code < 400

    def is_successful(self):
        return self.is_success()

