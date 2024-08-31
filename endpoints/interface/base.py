# -*- coding: utf-8 -*-
import logging
import json
import functools
import io
import email
import time
import inspect
import os

from datatypes import String, ReflectModule, ReflectPath, Dirpath

from ..config import environ
from ..call import Controller, Request, Response, Router
from ..exception import (
    CallError,
    Redirect,
    CallStop,
    AccessDenied,
    VersionError,
    CloseConnection,
)

from ..utils import ByteString, JSONEncoder


logger = logging.getLogger(__name__)


class ApplicationABC(object):
    """Child classes should extend BaseApplication but this class contains
    the methods that a child interface will most likely want to override so
    they are all here for convenience"""
    def is_http_call(self, *args, **kwargs):
        return True

    def is_websocket_call(self, *args, **kwargs):
        return False

    def normalize_call_kwargs(self, *args, **kwargs):
        """This is a method for child interfaces to use to normalize their raw
        request information into something that all the other methods can
        understand and use.

        It takes in whatever was passed to __call__ and converts it into kwargs
        that can then be passed to the other methods

        You might notice that all the methods in this class take *args and
        **kwargs, that's because the base interface has no idea what the actual
        child interface will receive. If you check the child interfaces you'll
        see that the methods that they implement change the signatures to
        something more concrete, this method helps by normalizing the received
        arguments and converting them all to keyword arguments that can be
        passed to the other methods

        :param *args: passed into __call__ as positional arguments
        :param **kwargs: passed into __call__ as keyword arguments
        :returns: dict[str, Any], a dict that can be used as **kwargs to
            further downstream methods in the child interface
        """
        raise NotImplementedError()

    def create_request(self, raw_request, **kwargs):
        raise NotImplementedError()

    def is_websocket_recv(self, data, **kwargs):
        raise NotImplementedError()

    def is_websocket_close(self, data, **kwargs):
        raise NotImplementedError()

    async def handle_http(self, *args, **kwargs):
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
    """all servers should extend this and implemented the NotImplemented
    methods, this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually
    responsible for serving the requests, while the interface will translate
    the requests to and from endpoints itself into something the server backend
    can understand

    webSocket protocol: https://www.rfc-editor.org/rfc/rfc6455

    """
    controller_prefixes = None
    """the controller prefixes (python module paths) you want to use to find
    your Controller subclasses"""

    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    response_class = Response
    """the endpoints.http.Response compatible class that should be used to make
    Response() instances"""

    controller_class = Controller
    """Every defined controller has to be a child of this class"""

    router_class = Router
    """Handles caching of Controllers and route finding for converting a
    requested path into a Controller"""

    def __init__(self, controller_prefixes=None, **kwargs):
        if controller_prefixes:
            if isinstance(controller_prefixes, str):
                controller_prefixes = environ.split_value(controller_prefixes)

            self.controller_prefixes = controller_prefixes

        else:
            if "controller_prefix" in kwargs:
                self.controller_prefixes = [kwargs["controller_prefix"]]

            else:
                self.controller_prefixes = environ.get_controller_prefixes()

        for k, v in kwargs.items():
            if k.endswith("_class"):
                setattr(self, k, v)

        self.router = self.create_router()

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

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints
        understands

        :params raw_request: mixed, this is the request given by backend
        :params **kwargs:
        :returns: an http.Request instance that endpoints understands
        """
        request = self.request_class()
        request.raw_request = raw_request
        return request

    def get_request_urlencoded(self, request, body, **kwargs):
        """Parse a form encoded body

        A form encoded body has a content-type of:

            application/x-www-form-urlencoded

        :param request: Request
        :param body: str|bytes
        :returns: dict
        """
        return request._parse_query_str(body)

    def get_request_json(self, request, body, **kwargs):
        """Parse a json encoded body

        A json encoded body has a content-type of:

            application/json

        :param request: Request
        :param body: str|bytes
        :returns: dict|list|Any
        """
        return json.loads(body)

    def get_request_multipart(self, request, body, **kwargs):
        """Parse a multipart form encoded body, this usually means the body
        contains an uploaded file

        A form encoded body has a content-type of:

            multipart/form-data

        :param request: Request
        :param body: str|bytes
        :returns: dict
        """
        ret = {}
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
                    ret[params["name"]] = fp

                else:
                    ret[params["name"]] = String(data)

        return ret

    def get_request_plain(self, request, body, **kwargs):
        """Parse a plain encoded body

        A plain encoded body has a content-type of:

            text/plain

        :param request: Request
        :param body: str|bytes
        :returns: str
        """
        return String(body, encoding=request.encoding)

    def get_request_chunked(self, request, body, **kwargs):
        """Do something with a chunked body, right now this just fails

        A body is chunked if the Transfer-Encoding header has a value of
        chunked

        :param request: Request
        :param body: str|bytes
        :returns: str, if this actually returned something it should be the
            raw body that can be processed further
        """
        raise IOError("Chunked bodies are not supported")

    def get_request_file(self, request, body, **kwargs):
        """Read the body into memory since it's a file pointer

        :param request: Request
        :param body: IOBase
        :returns: str, the raw body that can be processed further
        """
        length = int(request.get_header(
            "Content-Length",
            -1,
            allow_empty=False
        ))
        if length > 0:
            body = body.read(length)

        else:
            # since there is no content length we can conclude that we
            # don't actually have a body
            body = None

        return body

    def set_request_body(self, request, body, **kwargs):
        """
        :returns: tuple[Any, list, dict], returns raw_body, body_args, and
            body_kwargs
        """
        if request.headers.is_chunked():
            body = self.get_request_chunked(request, body, **kwargs)

        if isinstance(body, io.IOBase):
            body = self.get_request_file(request, body, **kwargs)

        args = []
        kwargs = {}

        if body:
            if isinstance(body, dict):
                kwargs = body

            elif isinstance(body, list):
                args = body

            elif request.headers.is_json():
                jb = self.get_request_json(request, body, **kwargs)

                if isinstance(jb, dict):
                    kwargs = jb

                elif isinstance(jb, list):
                    args = jb

                else:
                    args = [jb]

            elif request.headers.is_urlencoded():
                kwargs = self.get_request_urlencoded(request, body, **kwargs)

            elif request.headers.is_multipart():
                kwargs = self.get_request_multipart(request, body, **kwargs)

            elif request.headers.is_plain():
                body = String(body, encoding=request.encoding)
                args = [body]

        request.set_body(body, args, kwargs)

    def create_response(self, **kwargs):
        """create the endpoints understandable response instance that is used
        to return output to the client"""
        return self.response_class()

    async def get_response_body(self, response, **kwargs):
        """usually when iterating this object it means we are returning the
        response of a wsgi request, so this will iterate the body and make sure
        it is a bytes string because wsgiref requires an actual bytes instance,
        a child class won't work

        This will call one of three internal methods:

            * get_response_file - if response body is a file
            * get_response_json - if response body is a jsonable object
            * get_response_value - catchall for any other response bodies

        :param **kwargs: passed through to one of the three internal methods
        :returns: generator[bytes], a generator that yields bytes strings
        """
        if response.has_body():
            if response.is_file():
                chunks = self.get_response_file(response, **kwargs)

            elif response.is_json():
                chunks = self.get_response_json(response, **kwargs)

            else:
                chunks = self.get_response_value(response, **kwargs)

            async for chunk in chunks:
                yield chunk

    async def get_response_file(self, response, **kwargs):
        """Internal method called when response body is a file

        :returns: generator[bytes], a generator that yields bytes strings
        """
        body = response.body

        if body.closed:
            raise IOError(
                "cannot read streaming body because pointer is closed"
            )

        body_iterator = functools.partial(body.read, 8192)
        try:
            if "b" in body.mode:
                for chunk in iter(body_iterator, b""):
                    yield chunk

            else:
                # http://stackoverflow.com/questions/15599639/
                for chunk in iter(body_iterator, ""):
                    yield ByteString(chunk, response.encoding).raw()

        finally:
            # close the pointer since we've consumed it
            body.close()

    async def get_response_json(self, response, **kwargs):
        """Internal method called when response body should be dumped to
        json

        :param **kwargs:
            * json_encoder: JSONEncoder
        :returns: generator[bytes], a generator that yields bytes strings
        """
        body = response.body
        json_encoder = kwargs.get("json_encoder", JSONEncoder)
        body = json.dumps(body, cls=json_encoder)
        yield ByteString(body, response.encoding).raw()

    async def get_response_value(self, response, **kwargs):
        """Internal method called when response body is unknown, it will be
        treated like a string by default but child classes could customize
        this method if they want to

        :returns: generator[bytes], a generator that yields bytes strings
        """
        yield ByteString(response.body, response.encoding).raw()

    def create_router(self):
        return self.router_class(
            controller_prefixes=self.controller_prefixes,
            controller_class=self.controller_class,
        )

    def create_controller(self, request, response, **kwargs):
        """Create a controller to handle the request

        :returns: Controller, this Controller instance should be able to handle
            the request
        """
        return self.router.create_controller(
            request,
            response,
            **kwargs
        )

    async def handle(self, request, response, **kwargs):
        """Called from the interface to actually handle the request."""
        controller = None
        start = time.time()

        try:
            controller = self.create_controller(request, response)
            controller.log_start(start)

            controller_args = request.controller_info["method_args"]
            controller_kwargs = request.controller_info["method_kwargs"]
            controller_method = getattr(
                controller,
                request.controller_info["method_name"]
            )

            logger.debug("Request handle method: {}.{}.{}".format(
                controller.__class__.__module__,
                controller.__class__.__name__,
                controller_method.__name__
            ))
            await controller_method(
                *controller_args,
                **controller_kwargs
            )

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
                # just to be sure since body could've been ""
                response.body = None

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

        res.set_body(e)

        def log_error_warning(e):
            if logger.isEnabledFor(logging.DEBUG):
                logger.warning(e, exc_info=True)

            elif logger.isEnabledFor(logging.INFO):
                e_msg = String(e)
                ce = e
                while ce := getattr(ce, "__cause__", None):
                    e_msg += " caused by " + String(ce)
                logger.warning(e_msg)

            else:
                logger.warning(e)

        if isinstance(e, CallStop):
            logger.debug(String(e))
            res.code = e.code
            res.add_headers(e.headers)
            res.set_body(e.body)

        elif isinstance(e, Redirect):
            logger.debug(String(e))
            res.code = e.code
            res.add_headers(e.headers)
            res.set_body(None)

        elif isinstance(e, (AccessDenied, CallError)):
            log_error_warning(e)

            res.code = e.code
            res.add_headers(e.headers)

        elif isinstance(e, NotImplementedError):
            log_error_warning(e)
            res.code = 501

        elif isinstance(e, TypeError):
            e_msg = String(e)
            controller_info = req.controller_info

            if controller_info:
                # filter out TypeErrors raised from non handler methods
                correct_prefix = controller_info["method_name"] in e_msg
                if correct_prefix and 'argument' in e_msg:
                    # there are subtle messaging differences between py2 and
                    # py3
                    errs = [
                        "takes exactly",
                        "takes no arguments",
                        "positional argument"
                    ]
                    if (
                        errs[0] in e_msg
                        or errs[1] in e_msg
                        or errs[2] in e_msg
                    ):
                        # TypeError: <METHOD>() takes exactly M argument (N
                        #   given)
                        # TypeError: <METHOD>() takes no arguments (N given)
                        # TypeError: <METHOD>() takes M positional arguments
                        #   but N were given
                        # TypeError: <METHOD>() takes 1 positional argument but
                        #   N were given
                        # we shouldn't ever get the "takes no arguments" case
                        # because of self, but just in case check if there are
                        # path args, if there are then 404, if not then 405
                        #logger.debug(e_msg, exc_info=True)
                        logger.debug(e_msg)

                        if len(controller_info["method_args"]):
                            res.code = 404

                        else:
                            res.code = 405

                    elif "unexpected keyword argument" in e_msg:
                        # TypeError: <METHOD>() got an unexpected keyword
                        # argument '<NAME>'

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
                        # TypeError: <METHOD>() got multiple values for keyword
                        # argument '<NAME>'
                        try:
                            inspect.getcallargs(
                                controller_info["method"],
                                *controller_info["method_args"]
                            )
                            res.code = 409

                            log_error_warning(e)

                        except TypeError:
                            res.code = 404

                    else:
                        res.code = 500
                        logger.exception(e)

                else:
                    res.code = 500
                    logger.exception(e)

            else:
                res.code = 404
                log_error_warning(e)

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
        back down the wire

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
        """Given a received websocket body this will convert it back into a
        dict

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
        request = self.create_request(**kwargs)
        response = self.create_response(**kwargs)

        request.method = "CONNECT"

        await self.handle(request, response, **kwargs)
        await self.send_websocket_connect(request, response, **kwargs)

    async def handle_websocket_disconnect(self, **kwargs):
        """This handles calling <FOUND CONTROLLER>.DISCONNECT
        """
        request = self.create_request(**kwargs)
        response = self.create_response(**kwargs)

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

