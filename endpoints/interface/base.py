# -*- coding: utf-8 -*-
import logging
import json
import functools
import io
import email
import time
import inspect

from datatypes import String, ReflectModule

from ..config import environ
from ..call import Controller, Request, Response
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
    """Child classes should extend BaseApplication but this class contains
    the methods that a child interface will most likely want to override so
    they are all here for convenience"""
    def normalize_call_kwargs(self, *args, **kwargs):
        raise NotImplementedError()

    async def handle_http(self, *args, **kwargs):
        raise NotImplementedError()

    async def create_request(self, raw_request, **kwargs):
        raise NotImplementedError()

    def is_http_call(self, *args, **kwargs):
        return True

    def is_websocket_call(self, *args, **kwargs):
        return False

    def is_websocket_recv(self, data, **kwargs):
        raise NotImplementedError()

    def is_websocket_close(self, data, **kwargs):
        raise NotImplementedError()

    async def handle_websocket_recv(self, data, **kwargs):
        raise NotImplementedError()

    async def send_websocket(self, request, response, **kwargs):
        raise NotImplementedError()

    async def handle_websocket_connect(self, *args, **kwargs):
        raise NotImplementedError()

    async def send_websocket_connect(self, request, response, **kwargs):
        raise NotImplementedError()

    async def handle_websocket_disconnect(self, *args, **kwargs):
        raise NotImplementedError()

    async def send_websocket_disconnect(self, *args, **kwargs):
        raise NotImplementedError()

    async def recv_websocket(self, *args, **kwargs):
        raise NotImplementedError()


class BaseApplication(ApplicationABC):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually
    responsible for serving the requests, while the interface will translate the
    requests to and from endpoints itself into something the server backend can
    understand

    webSocket protocol: https://www.rfc-editor.org/rfc/rfc6455

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

    async def __call__(self, *args, **kwargs):
        """this is what will be called for each request that the server handles
        """
        call_kwargs = self.normalize_call_kwargs(*args, **kwargs)

        if self.is_http_call(**call_kwargs):
            return await self.handle_http(**call_kwargs)

        elif self.is_websocket_call(**call_kwargs):
            return await self.handle_websocket(**call_kwargs)

        else:
            logger.warning("Request was not HTTP or WebSocket")

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
        :returns: tuple[Any, list, dict], returns raw_body, body_args, and
            body_kwargs
        """
        if request.headers.is_chunked():
            raise IOError("Chunked bodies are not supported")

        if isinstance(body, io.IOBase):
            length = int(request.get_header(
                "Content-Length",
                -1,
                allow_empty=False
            ))
            if length > 0:
                body = body.read(length)

            else:
                # since there is no content length we can conclude that we don't
                # actually have a body
                body = None

        args = []
        kwargs = {}

        if body:
            if isinstance(body, dict):
                kwargs = body

            elif isinstance(body, list):
                args = body

            elif request.headers.is_json():
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
        """usually when iterating this object it means we are returning the
        response of a wsgi request, so this will iterate the body and make sure
        it is a bytes string because wsgiref requires an actual bytes instance,
        a child class won't work

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
        """try and get the class_name from the module and make sure it is a
        valid controller"""
        class_name = class_name.capitalize()
        class_object = getattr(module, class_name, None)
        if not class_object or not issubclass(class_object, Controller):
            class_object = None

        return class_object

    async def find_controller_class(self, module, path_args, **kwargs):
        named_class = None
        default_class = None

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
                kwargs.get("class_fallback", "Default"),
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
                ret["module"] = ReflectModule(ret["module_name"]).get_module()

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
                    ).get_module()

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
            await controller_method(*controller_args, **controller_kwargs)

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
        res.error = e

        if isinstance(e, CloseConnection):
            raise

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

    @classmethod
    def get_websocket_dumps(cls, **kwargs):
        """Similar to create_response_body it prepares a response to be sent
        back down the wire using the payload_class variable

        This isn't asyncronouse because it is used in ..client.WebSocketClient
        to create websocket bodies

        This is the sister method to .get_websocket_loads() and should be a
        mirror of that method

        :param request: the call's Request instance, this needs the request
            because of how websockets are sent back and forth
        :param response: the call's Response instance
        :returns: str
        """
        d = {}

        d["path"] = kwargs["path"]

        if uuid := kwargs.get("uuid", ""):
            d["uuid"] = uuid

        if code := kwargs.get("code", 0):
            d["code"] = code

        if method := kwargs.get("method", ""):
            d["method"] = method

        if "code" not in d and "method" not in d:
            raise ValueError("A websocket payload needs a method or code")

        if headers := kwargs.get("headers", {}):
            d["headers"] = headers

        body = kwargs.get("body", None)
        if body is not None:
            d["body"] = body

        body = json.dumps(
            d,
            cls=kwargs.get("json_encoder", JSONEncoder),
        )
        return body

    @classmethod
    def get_websocket_loads(cls, body):
        """Given a received websocket body this will convert it back into a dict

        This isn't asyncronouse because it is used in ..client.WebSocketClient
        to read websocket bodies sent from the server

        This is the sister method to .get_websocket_dumps() and should be a
        mirror of that method

        :param body: str
        :returns: dict
        """
        d = json.loads(body)

        if "code" not in d and "method" not in d:
            raise ValueError("A websocket payload needs a method or code")

        if "path" not in d:
            raise ValueError("A websocket payload must have a path")

        if "body" not in d:
            d["body"] = None

        if "headers" not in d:
            d["headers"] = {}

        return d

    async def handle_websocket_connect(self, **kwargs):
        """This handles calling <FOUND CONTROLLER>.CONNECT
        """
        request = await self.create_request(**kwargs)
        response = await self.create_response(**kwargs)

        request.method = "CONNECT"

        await self.handle(request, response, **kwargs)
        await self.send_websocket_connect(request, response, **kwargs)

    async def handle_websocket_disconnect(self, **kwargs):
        """This handles calling <FOUND CONTROLLER>.DISCONNECT
        """
        request = await self.create_request(**kwargs)
        response = await self.create_response(**kwargs)

        response.code = kwargs.get("code", 1000)
        request.method = "DISCONNECT"

        await self.handle(request, response)
        await self.send_websocket_disconnect(request, response, **kwargs)

    async def handle_websocket(self, **kwargs):
        """Handle the lifecycle of a websocket connection. Child interfaces
        should override methods that this calls but shouldn't override this
        method unless they really need to
        """
        await self.handle_websocket_connect(**kwargs)
        disconnect = True

        try:
            while True:
                data = await self.recv_websocket(**kwargs)

                if self.is_websocket_recv(data, **kwargs):
                    await self.handle_websocket_recv(data, **kwargs)

                elif self.is_websocket_close(data, **kwargs):
                    disconnect = False
                    break

                else:
                    logger.warning("Websocket data was unrecognized")

        except CloseConnection as e:
            disconnect = True

        except Exception as e:
            # daphne was buring the error and I'm not sure why, so I'm going to
            # leave this here for right now just in case
            logger.exception(e)
            raise

        finally:
            if disconnect:
                await self.handle_websocket_disconnect(**kwargs)

