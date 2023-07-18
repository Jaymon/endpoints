# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import logging
import json
import sys
import functools
import io
import email
import time
import inspect

from datatypes import String, ReflectModule

from .. import environ
from ..call import Controller, Request, Response
from ..decorators import property
#from ..exception import CallError, Redirect, CallStop, AccessDenied

from ..exception import (
    CallError,
    Redirect,
    CallStop,
    AccessDenied,
    RouteError,
    VersionError,
    CloseConnection,
)

from ..utils import ByteString, JSONEncoder


logger = logging.getLogger(__name__)


class ApplicationABC(object):
    async def __call__(self, *args, **kwargs):
        raise NotImplementedError()


class BaseApplication(ApplicationABC):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually responsible
    for serving the requests, while the interface will translate the requests to
    and from endpoints itself into something the server backend can understand
    """
    controller_prefixes = None
    """the controller prefixes (python module paths) you want to use to find your
    Controller subclasses"""

    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    response_class = Response
    """the endpoints.http.Response compatible class that should be used to make
    Response() instances"""

    controller_class = Controller
    """Every defined controller has to be a child of this class"""

    def __init__(self, controller_prefixes=None, **kwargs):
        if controller_prefixes:
            self.controller_prefixes = controller_prefixes

        else:
            if "controller_prefix" in kwargs:
                self.controller_prefixes = [kwargs["controller_prefix"]]

            else:
                self.controller_prefixes = environ.get_controller_prefixes()

        for k, v in kwargs.items():
            if k.endswith("_class"):
                setattr(self, k, v)

    async def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints
        understands

        :params raw_request: mixed, this is the request given by backend
        :params **kwargs:
            :returns: an http.Request instance that endpoints understands
        """
        request = self.request_class()
        request.raw_request = raw_request
        return request

    async def set_request_body(self, request, body, **kwargs):
        """
        :returns: tuple[Any, list, dict], returns raw_body, body_args, body_kwargs
        """
        if request.headers.is_chunked():
            raise IOError("Chunked bodies are not supported")

        args = []
        kwargs = {}

        if body:
            if request.headers.is_json():
                jb = json.loads(body)

                if isinstance(jb, dict):
                    kwargs = jb

                elif isinstance(jb, list):
                    args = jb

                else:
                    args = [jb]

            elif request.headers.is_urlencoded():
                kwargs = request._parse_query_str(body)

            elif request.headers.is_multipart():
                em = email.message_from_bytes(bytes(request.headers) + body)
                for part in em.walk():
                    if not part.is_multipart():
                        data = part.get_payload(decode=True)
                        params = {}
                        for header_name in part:
                            for k, v in part.get_params(header=header_name)[1:]:
                                params[k] = v

                        if "name" not in params:
                            raise IOError("Bad body data")

                        if "filename" in params:
                            fp = io.BytesIO(data)
                            fp.filename = params["filename"]
                            kwargs[params["name"]] = fp

                        else:
                            kwargs[params["name"]] = String(data)

            elif request.headers.is_plain():
                body = String(body, encoding=request.encoding)

        request.body = body
        request.body_args = args
        request.body_kwargs = kwargs

    async def create_response(self, **kwargs):
        """create the endpoints understandable response instance that is used to
        return output to the client"""
        return self.response_class()

    async def get_response_body(self, response, json_encoder=JSONEncoder, **kwargs):
        """usually when iterating this object it means we are returning the response
        of a wsgi request, so this will iterate the body and make sure it is a bytes
        string because wsgiref requires an actual bytes instance, a child class
        won't work

        :returns: a generator that yields bytes strings
        """
        if response.has_body():

            body = response.body

            if response.is_file():
                if body.closed:
                    raise IOError(
                        "cannot read streaming body because pointer is closed"
                    )

                # http://stackoverflow.com/questions/15599639/
                for chunk in iter(functools.partial(body.read, 8192), ''):
                    yield ByteString(chunk, response.encoding).raw()

                # close the pointer since we've consumed it
                body.close()

            elif response.is_json():
                # TODO ???
                # I don't like this, if we have a content type but it isn't one
                # of the supported ones we were returning the exception, which
                # threw Jarid off, but now it just returns a string, which is not
                # best either my thought is we could have a body_type_subtype
                # method that would make it possible to easily handle custom
                # types, eg, "application/json" would become:
                #    self.body_application_json(b, is_error)
                body = json.dumps(body, cls=json_encoder)
                yield ByteString(body, response.encoding).raw()

            else:
                # just return a string representation of body if no content type
                yield ByteString(body, response.encoding).raw()

    @functools.cache
    def get_controller_module_paths(self):
        """get all the modules in the controller_prefixes

        :returns: set, a set of string module names (eg foo.bar, foo.che)
        """
        controller_modpaths = set()
        for controller_prefix in self.controller_prefixes:
            rm = ReflectModule(controller_prefix)
            controller_modpaths.update(rm.module_names())

        return controller_modpaths

    async def get_controller_class(self, module, class_name):
        """try and get the class_name from the module and make sure it is a valid
        controller"""
        # let's get the class
        class_name = class_name.capitalize()
        class_object = getattr(module, class_name, None)
        if not class_object or not issubclass(class_object, Controller):
            class_object = None

        return class_object

    async def find_controller_class(self, module, path_args, **kwargs):
        named_class = None
        default_class = None

        class_fallback = kwargs.get("class_fallback", "Default")

        if path_args:
            # look for a class name with the first path arg, this will be
            # used if a matching module isn't found
            named_class = await self.get_controller_class(
                module,
                path_args[0]
            )

        if not named_class:
            # look for the default class just in case, this is a first
            # match wins scenario. Basically, the first controller default
            # class found will be the class that answers the call unless
            # a class matching a path arg is found
            default_class = await self.get_controller_class(
                module,
                class_fallback,
            )

        return named_class, default_class

    async def find_controller_info(self, request, **kwargs):
        """returns all the information needed to create a controller and handle
        the request

        This is where all the routing magic happens, this takes the request.path
        and gathers the information needed to turn that path into a Controller

        we always translate an HTTP request using this pattern:

            METHOD /module/class/args?kwargs

        GET /foo -> controller_prefix.foo.Default.GET
        POST /foo/bar -> controller_prefix.foo.Bar.POST
        GET /foo/bar/che -> controller_prefix.foo.Bar.GET(che)
        POST /foo/bar/che?baz=foo -> controller_prefix.foo.Bar.POST(che, baz=foo)

        :param request: Request
        :param **kwargs:
            * class_fallback: str, the name of the default controller class, it
                defaults to Default and should probably never be changed
            * method_fallback: str, the name of the fallback controller method,
                it defaults to ANY and should probably never be changed
        :returns: dict
        """
        logger.debug("Compiling Controller info using path: {}".format(
            request.path
        ))

        ret = {
            "module_name": "",
            "module_path_args": [],
            "controller_path_args": [],
        }
        default_ret = {}
        named_ret = {}

        path_args = list(request.path_args)

        controller_modpaths = self.get_controller_module_paths()
        for controller_prefix in self.controller_prefixes:
            modpath = controller_prefix
            # using the path_args we are going to try and find the best module
            # path for the request
            while path_args:
                modpath += "." + path_args[0]
                if modpath in controller_modpaths:
                    ret["module_name"] = modpath
                    ret["module_path_args"].append(path_args[0])
                    ret["controller_path_args"].append(path_args.pop(0))
                    ret["controller_prefix"] = controller_prefix

                else:
                    break

            if ret["module_name"]:
                ret["module"] = ReflectModule(ret["module_name"]).module()

                named_class, default_class = await self.find_controller_class(
                    ret["module"],
                    path_args,
                )

                if named_class:
                    ret["class"] = named_class
                    ret["controller_path_args"].append(path_args.pop(0))

                elif default_class:
                    ret["class"] = default_class

                else:
                    raise TypeError(
                        " ".join([
                            "Could not find a valid module and Controller",
                            f"class for {request.path}"
                        ])
                    )

                break

            else:
                # we didn't find the correct module using module paths, so now
                # let's try class paths, first found class path wins
                if not named_ret or not default_ret:
                    controller_module = ReflectModule(
                        controller_prefix
                    ).module()

                    named_class, default_class = await self.find_controller_class(
                        controller_module,
                        path_args,
                    )

                    if named_class and not named_ret:
                        named_ret["class"] = named_class
                        named_ret["module"] = controller_module
                        named_ret["module_name"] = controller_prefix
                        named_ret["controller_prefix"] = controller_prefix
                        named_ret["controller_path_args"] = [path_args.pop(0)]

                    if default_class and not default_ret:
                        default_ret["class"] = default_class
                        default_ret["module"] = controller_module
                        default_ret["module_name"] = controller_prefix
                        default_ret["controller_prefix"] = controller_prefix

        if not ret["module_name"]:
            if named_ret:
                ret.update(named_ret)

            elif default_ret:
                ret.update(default_ret)

            else:
                raise TypeError(
                    " ".join([
                        "Could not find a valid module with path",
                        "{} and controller_prefixes {}".format(
                            request.path,
                            self.controller_prefixes
                        )
                    ])
                )

        ret["method_args"] = path_args
        # we merge the leftover path args with the body kwargs
        ret['method_args'].extend(request.body_args)

        ret['method_kwargs'] = request.kwargs

        ret["method_prefix"] = request.method.upper()
        ret["method_fallback"] = kwargs.get("method_fallback", "ANY")

        ret['module_path'] = "/".join(ret["module_path_args"])
        ret['class_name'] = ret["class"].__name__
        ret['class_path'] = "/".join(ret["controller_path_args"])

        return ret

    async def create_controller(self, request, response, **kwargs):
        """Create a controller to handle the request

        :returns: Controller, this Controller instance should be able to handle
            the request
        """
        try:
            request.controller_info = await self.find_controller_info(
                request,
                **kwargs
            )

        except (ImportError, AttributeError, TypeError) as e:
            raise CallError(
                404,
                "Path {} could not resolve to a controller".format(
                    request.path,
                ) 
            ) from e

        else:
            controller = request.controller_info['class'](
                request,
                response,
                **kwargs
            )

        return controller

    async def handle(self, request, response, **kwargs):
        """Called from the interface to actually handle the request."""
        controller = None
        start = time.time()

        try:
            controller = await self.create_controller(request, response)
            controller.log_start(start)

            controller_args = request.controller_info["method_args"]
            controller_kwargs = request.controller_info["method_kwargs"]
            controller_method = getattr(controller, "handle")

            logger.debug("Request handle method: {}.{}.{}".format(
                controller.__class__.__module__,
                controller.__class__.__name__,
                controller_method.__name__
            ))
            # TODO check for aysnc handle method
            await controller_method(*controller_args, **controller_kwargs)

        except CloseConnection:
            raise

        except Exception as e:
            await self.handle_error(
                request,
                response,
                e,
                controller,
                **kwargs
            )

        finally:
            if response.code == 204:
                response.headers.pop('Content-Type', None)
                response.body = None # just to be sure since body could've been ""

            if controller:
                controller.log_stop(start)

    async def handle_error(self, req, res, e, controller, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        This method will set the response body and then also calls
        Controller.handle_error for further customization if the Controller is
        available

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        res.body = e

        if isinstance(e, CallStop):
            logger.debug(String(e))
            res.code = e.code
            res.add_headers(e.headers)
            res.body = e.body

        elif isinstance(e, Redirect):
            logger.debug(String(e))
            res.code = e.code
            res.add_headers(e.headers)
            res.body = None

        elif isinstance(e, (AccessDenied, CallError)):
            logger.warning(String(e))
            res.code = e.code
            res.add_headers(e.headers)

        elif isinstance(e, NotImplementedError):
            logger.warning(String(e))
            res.code = 501

        elif isinstance(e, TypeError):
            e_msg = String(e)
            controller_info = req.controller_info

            # filter out TypeErrors raised from non handler methods
            correct_prefix = controller_info["method_name"] in e_msg
            if correct_prefix and 'argument' in e_msg:
                # there are subtle messaging differences between py2 and py3
                errs = [
                    "takes exactly",
                    "takes no arguments",
                    "positional argument"
                ]
                if (errs[0] in e_msg) or (errs[1] in e_msg) or (errs[2] in e_msg):
                    # TypeError: <METHOD>() takes exactly M argument (N given)
                    # TypeError: <METHOD>() takes no arguments (N given)
                    # TypeError: <METHOD>() takes M positional arguments but N were given
                    # TypeError: <METHOD>() takes 1 positional argument but N were given
                    # we shouldn't ever get the "takes no arguments" case because of self,
                    # but just in case
                    # check if there are path args, if there are then 404, if not then 405
                    #logger.debug(e_msg, exc_info=True)
                    logger.debug(e_msg)

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
                        inspect.getcallargs(
                            controller_info["method"],
                            *controller_info["method_args"]
                        )
                        res.code = 405

                        logger.warning("Controller method {}.{}.{}".format(
                            controller_info['module_name'],
                            controller_info['class_name'],
                            e_msg
                        ))

                    except TypeError:
                        res.code = 404

                elif "multiple values" in e_msg:
                    # TypeError: <METHOD>() got multiple values for keyword argument '<NAME>'
                    try:
                        inspect.getcallargs(
                            controller_info["method"],
                            *controller_info["method_args"]
                        )
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

        if controller:
            error_method = getattr(
                controller,
                "handle_{}_error".format(res.code),
                None
            )
            if not error_method:
                error_method = getattr(
                    controller,
                    "handle_{}_error".format(req.method),
                    None
                )
                if not error_method:
                    error_method = getattr(controller, "handle_error")

            logger.debug("Handle {} error using method: {}.{}".format(
                res.code,
                controller.__class__.__name__,
                error_method.__name__
            ))
            await error_method(e, **kwargs)









# TODO -- this is used by client.WebSocketClient
class Payload(object):
    """We have a problem with generic websocket support, websockets don't have an
    easy way to decide how they will send stuff back and forth like http (where you
    can set a content type header and things like that) so Payload solves that problem,
    the websocket client and the default interface of the servers will use Payload but
    it could be overridden and completely changed and then you would just need to set
    the class in the client and server interfaces and you could completely change the
    way the websockets interact with each other

    I thought about doing something with the accept header or content-type on a Request
    object, which maybe would work but you can also override the Request and Response
    objects and that would mean you would need to put the loads/dumps code in possibly
    two different places, which I don't love because I like DRY solutions so it would
    still be great to have a class like this that all the other interfaces wrap
    in order to send/receive data via websockets
    """
    @classmethod
    def loads(cls, raw):
        return json.loads(raw)

    @classmethod
    def dumps(cls, kwargs):
        return json.dumps(kwargs, cls=JSONEncoder)


class BaseWebsocketServer(BaseApplication):

    payload_class = Payload

    def create_websocket_request(self, request, raw_request=None):
        """create the websocket Request for this call using the original Request
        instance from the initial ws connection

        :param request: the original Request instance from the initial connection
        :param raw_request: this will be passed to self.payload_class to be 
            interpretted
        :returns: a new Request instance to be used for this specific call
        """
        ws_req = request.copy()
        ws_req.controller_info = None

        # just in case we need access to the original request object or the raw info
        ws_req.parent = request
        ws_req.raw_request = raw_request

        if raw_request:
            # path, body, method, uuid
            kwargs = self.payload_class.loads(raw_request)
            #kwargs.setdefault("body", None)
            kwargs.setdefault("path", request.path)
            kwargs.setdefault("headers", {})
            kwargs.setdefault("body", {})

            ws_req.environ["REQUEST_METHOD"] = kwargs["method"]
            ws_req.method = kwargs["method"]

            ws_req.environ["PATH_INFO"] = kwargs["path"]
            ws_req.path = kwargs["path"]

            ws_req.environ.pop("wsgi.input", None)

            ws_req.body = kwargs["body"]
            ws_req.body_kwargs = kwargs["body"]

            #ws_req.uuid = kwargs["uuid"] if "uuid" in kwargs else None
            ws_req.uuid = kwargs.get("uuid", request.uuid)

            ws_req.headers.update(kwargs["headers"])

        return ws_req

    def create_websocket_response_body(self, request, response, json_encoder=JSONEncoder, **kwargs):
        """Similar to create_response_body it prepares a response to be sent back
        down the wire using the payload_class variable

        :param request: the call's Request instance, this needs the request because
            of how websockets are sent back and forth
        :param response: the call's Response instance
        :returns: a generator that yields bytes strings
        """
        raw_response = {}

        raw_response["path"] = request.path
        if request.uuid:
            raw_response["uuid"] = request.uuid

        raw_response["code"] = response.code
        raw_response["body"] = response.body

        body = self.payload_class.dumps(raw_response)
        yield ByteString(body, response.encoding).raw()

    def connect_websocket_call(self, raw_request):
        """called during websocket handshake

        this should modify the request instance to use the CONNECT method so you
        can customize functionality in your controller using a CONNECT method

        NOTE -- this does not call create_websocket_request, it does call create_request

        :param raw_request: the raw request from the backend
        :returns: Call instance that can handle the request
        """
        c = self.create_call(raw_request)
        req = c.request

        # if there is an X-uuid header then set uuid and send it down
        # with every request using that header
        # https://stackoverflow.com/questions/18265128/what-is-sec-websocket-key-for
        uuid = None

        # first try and get the uuid from the body since javascript has limited
        # capability of setting headers for websockets
        kwargs = req.kwargs
        if "uuid" in kwargs:
            uuid = kwargs["uuid"]

        # next use X-UUID header, then the websocket key
        if not uuid:
            uuid = req.find_header(["X-UUID", "Sec-Websocket-Key"])

        req.uuid = uuid
        req.method = "CONNECT"
        return c

    def create_websocket_call(self, request, raw_request=None):
        """for every message sent back and forth over the websocket this should be
        called

        :param request: Request, the main request from the initial ws connection
        :param raw_request: mixed, the raw request pulled from some backend that
            should be acted on
        :returns: Call instance
        """
        req = self.create_websocket_request(request, raw_request)
        c = self.create_call(raw_request, request=req)
        return c

    def disconnect_websocket_call(self, request):
        """This handles a websocket disconnection

        this should modify the request instance to use the DISCONNECT method so you
        can customize functionality in your controller using a DISCONNECT method

        :param request: Request, the main request from the initial ws connection
        :returns: Call instance
        """
        #req = self.create_websocket_request(request)
        request.method = "DISCONNECT"
        c = self.create_call(None, request=request)
        return c

