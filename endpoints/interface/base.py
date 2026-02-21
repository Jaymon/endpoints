# -*- coding: utf-8 -*-
import logging
import json
import functools
import io
import email
import time
import inspect
import os
import datetime
from typing import Any
from types import ModuleType
from collections.abc import Iterable

from datatypes import (
    String,
    ReflectModule,
    ReflectPath,
    Dirpath,
    Profiler,
    ClassFinder,
    ReflectCallable,
)
from datatypes.http import Multipart

from ..compat import *
from ..config import environ
from ..call import (
    Controller,
    Request,
    Response,
#     Router,
)
from ..reflection.inspect import Pathfinder
from ..exception import (
    CloseConnection,
)

from ..utils import ByteString, JSONEncoder


logger = logging.getLogger(__name__)


class InterfaceABC(object):
    def __call__(self, *args, **kwargs) -> Any:
        """The interface will want to customize this, whatever this call
        signature is, the `.create_request` will probably want to match
        it"""
        raise NotImplementedError()

    def create_request(self, *args, **kwargs) -> Request:
        """Create a request

        this is the method that translates an interface request
        to one that Endpoints can understand. The call signature will most
        likely change to match `.__call__` in the child class, but the
        return value **cannot** change
        """
        raise NotImplementedError()

    def is_websocket_recv(self, data: Any, **kwargs) -> bool:
        raise NotImplementedError()

    def is_websocket_close(self, data: Any, **kwargs) -> bool:
        raise NotImplementedError()


class Interface(InterfaceABC):
    def __init__(self, application):
        self.application = application

    def __init_subclass__(cls, *args, **kwargs):
        rc = ReflectCallable(cls.__call__)
        sig_info = rc.get_signature_info()

        if (
            "scope" in sig_info["indexes"]
            and "receive" in sig_info["indexes"]
            and "send" in sig_info["indexes"]
        ):
            Application.interface_classes["asgi"] = cls

        elif (
            "environ" in sig_info["indexes"]
            and "start_response" in sig_info["indexes"]
        ):
            Application.interface_classes["wsgi"] = cls

        else:
            raise ValueError("Unknown Interface.__call__ method")

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints
        understands

        :params raw_request: mixed, this is the request given by backend
        :params **kwargs:
        :returns: an http.Request instance that endpoints understands
        """
        request = self.application.request_class()
        request.raw_request = raw_request
        return request

    def create_response(self, **kwargs):
        """create the endpoints understandable response instance that is used
        to return output to the client"""
        return self.application.response_class()

    async def handle_websocket_connect(self, **kwargs):
        """This handles calling <FOUND CONTROLLER>.CONNECT
        """
        request = self.create_request(**kwargs)
        response = self.create_response(**kwargs)

        request.method = "CONNECT"

        await self.application.handle(request, response, **kwargs)
        await self.send_websocket_connect(request, response, **kwargs)

    async def handle_websocket_disconnect(self, **kwargs):
        """This handles calling <FOUND CONTROLLER>.DISCONNECT
        """
        request = self.create_request(**kwargs)
        response = self.create_response(**kwargs)

        response.code = kwargs.get("code", 1000)
        request.method = "DISCONNECT"

        await self.application.handle(request, response)
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
            # daphne was burying the error and I'm not sure why, so I'm going
            # to leave this here for right now just in case
            logger.exception(e)
            raise

        finally:
            if disconnect:
                await self.handle_websocket_disconnect(**kwargs)


class Application(object):
    """Create an application that can handle ASGI and WSGI requests

    :example:
        # mymodule.py
        application = Application()
        # application path: mymodule:application

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

#     router_class = Router
    """Handles caching of Controllers and route finding for converting a
    requested path into a Controller"""

    pathfinder_class = Pathfinder
    """Used by router, handles finding and reflecting controllers"""

    interface_classes: dict[str, Interface] = {}
    """This is populated in `Interface.__init_subclass__` and should never
    be touched"""

    interface: Interface = None
    """Holds the interface created from the interfaces found in
    `.interface_classes`"""

    _asgi_single_callable = True
    """asgiref thing. This is to make the `daphne` server a little more
    predictable. If this is not set then `daphne` considers `.__call__` a
    double callable and will call `.__call__` with `scope` and nothing else
    and expected a callable, then it will call that callable with `receive`
    and `send`.

    I have no idea why it does that, since this functionality is completely
    different than any other ASGI server. I'm guessing this is an older
    ASGI problem. This is checked in `asgiref.compatibility.is_double_callable`
    """

    @classmethod
    def get_websocket_dumps(cls, **kwargs):
        """Similar to create_response_body it prepares a response to be sent
        back down the wire

        This isn't asyncronouse because it is used in ..client.WebSocketClient
        to create websocket bodies

        This is the sister method to .get_websocket_loads() and should be a
        mirror of that method

        :keyword path: Optional[str], the path (eg, `/foo/bar`)
        :keyword code: Optional[int], the response code
        :keyword method: Optional[str], the http method (eg, `GET`)
        :keyword headers: Optional[dict[str, str]], headers to send
        :keyword body: Any, the body to send
        :raises: ValueError if both code and method are missing
        :returns: bytes, json
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

        return cls.controller_class.dump_json(d)

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
        d = cls.controller_class.load_json(body)

        if "code" not in d and "method" not in d:
            raise ValueError("A websocket payload needs a method or code")

        if "path" not in d:
            raise ValueError("A websocket payload must have a path")

        if "body" not in d:
            d["body"] = None

        if "headers" not in d:
            d["headers"] = {}

        return d

    def __init__(
        self,
        controller_prefixes: Iterable[str]|str|None = None,
        paths: Iterable[str]|None = None,
        **kwargs,
    ):
        """Create an Application instance

        This loads the controllers using `.find_modules` and then loads all
        the controllers into the pathfinder in `.create_pathfinder`

        :param controller_prefixes: the controller module prefixes to use
            to find controllers to answer requests (eg, if you pass in 
            `foo.bar` then any submodules will be stripped of `foo.bar` and use
            the rest of the module path to figure out the full requestable
            path, so `foo.bar.che.Boo` would have `che/boo` as its path
        :param paths: the paths to check for controllers. This looks for
            a module named `controllers` in the paths, the first found module
            wins
        """
        for k, v in kwargs.items():
            if k.endswith("_class"):
                setattr(self, k, v)

        self.controller_modules = self.find_modules(
            controller_prefixes=controller_prefixes,
            paths=paths,
            **kwargs,
        )

        self.pathfinder = self.create_pathfinder(**kwargs)
#         self.router = self.create_router()

    def __call__(self, *args, **kwargs) -> Any:
        """Factory method

        This will create the interface and can also transparently answer
        requests using the internal interface if needed
        """
        if self.interface:
            return self.interface(*args, **kwargs)

        else:
            if args:
                if "asgi" in args[0]:
                    # hypercorn passes in the lifecycle right off
                    self.interface = self.create_asgi_interface()
                    return self.__call__(*args, **kwargs)

                elif "wsgi.version" in args[0]:
                    self.interface = self.create_wsgi_interface()
                    return self.__call__(*args, **kwargs)

                else:
                    raise ValueError("Unknown interface")

            else:
                self.interface = self.create_asgi_interface()

                if kwargs:
                    # daphne single callable passes in scope, receive, and
                    # send in kwargs
                    return self.__call__(*args, **kwargs)

                else:
                    # uvicorn and granian use this as a factory method (when
                    # configured correctly)
                    return self.interface

    def create_asgi_interface(self) -> Interface:
        """Create an ASGI interface that can answer ASGI requests

        :example:
            application = Application().create_asgi_interface()
        """
        interface_classes = type(self).interface_classes

        if "asgi" not in interface_classes:
            from .asgi import Interface

        return interface_classes["asgi"](self)

    def create_wsgi_interface(self) -> Interface:
        """Create a WSGI interface that can answer WSGI requests

        :example:
            application = Application().create_wsgi_interface()
        """
        interface_classes = type(self).interface_classes

        if "wsgi" not in interface_classes:
            from .wsgi import Interface

        return interface_classes["wsgi"](self)

    def log_start(self, request, response):
        """log all the headers and stuff at the start of the request"""
        if not logger.isEnabledFor(logging.INFO):
            return

        try:
            if uuid := getattr(request, "uuid", ""):
                uuid += " "

            logger.info("Request {}{} {}".format(
                uuid,
                request.method,
                request.uri,
            ))

            logger.info("Request {}date: {}".format(
                uuid,
                datetime.datetime.fromtimestamp(
                    response.start,
                    datetime.timezone.utc,
                ).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
            ))

            ip = request.ip
            if ip:
                logger.info("Request {}IP address: {}".format(uuid, ip))

            if 'authorization' in request.headers:
                logger.info('Request {}auth: {}'.format(
                    uuid,
                    request.headers['authorization']
                ))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            for k, v in request.headers.items():
                if k not in ignore_hs:
                    logger.info(
                        "Request {}header - {}: {}".format(uuid, k, v)
                    )

            self.log_start_body(request, response)

        except Exception as e:
            logger.warning(e, exc_info=True)

    def log_start_body(self, request, response):
        """Log the request body

        this is separate from log_start so it can be easily overridden in
        children
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return

        if uuid := getattr(request, "uuid", ""):
            uuid += " "

        try:
            if request.has_body():
                if isinstance(request.body, io.IOBase):
                    if request.body.seekable():
                        offset = request.body.tell()
                        body = request.body.read()
                        request.body.seek(offset)

                    else:
                        body = "Unseekable io.IOBase body"

                else:
                    body = request.body

                logger.debug(
                    "Request {}body: {}".format(
                        uuid,
                        body,
                        #repr(body) if isinstance(body, bytes) else body
                    )
                )

            elif request.should_have_body():
                logger.debug(
                    "Request {}body: <EMPTY>".format(uuid)
                )

        except Exception as e:
            logger.debug(
                "Request {}body raw: {}".format(uuid, request.body),
            )
            logger.exception(e)

    def log_stop(self, request, response):
        """log a summary line on how the request went"""
        if not logger.isEnabledFor(logging.INFO):
            return

        if uuid := getattr(request, "uuid", ""):
            uuid += " "

        for k, v in response.headers.items():
            logger.info("Response {}header - {}: {}".format(uuid, k, v))

        response.stop = time.time()

        logger.info(
            "Response {}{} {} in {} for Request {} {}".format(
                uuid,
                response.code,
                response.status,
                Profiler.get_output(response.start, response.stop),
                request.method,
                request.uri,
            )
        )

    def create_pathfinder(self, **kwargs) -> Pathfinder:
        """Internal method. Create the tree that will be used to resolve a
        requested path to a found controller

        :returns: basically a dictionary of dictionaries where each
            key represents a part of a path, the final key will contain the
            controller class that can answer a request
        """
        pathfinder = self.pathfinder_class(
            list(self.controller_modules.keys()),
        )

        controller_classes = self.controller_class.controller_classes
        for controller_class in controller_classes.values():
            if not controller_class.is_private():
                pathfinder.add_class(controller_class)

        return pathfinder

    def find_controller_info(self, request, **kwargs):
        """returns all the information needed to create a controller and
        handle the request

        This is where all the routing magic happens, this takes the
        request.path and gathers the information needed to turn that path into
        a Controller

        This uses the requested path_args and checks the internal tree to find
        the right path or raises a TypeError if the path can't be resolved

        we always translate an HTTP request using this pattern:

            METHOD /module/class/args?kwargs

        :param request: Request
        :param **kwargs:
        :returns: dict
        """
        ret = {}

        logger.debug("Compiling Controller info using path: %s", request.path)

        rc_classes = []
        leftover_path_args = list(filter(None, request.path.split('/')))
        node = self.pathfinder

        while node is not None:
            if node.value and "class" in node.value:
                rc_classes.append(node.value["reflect_class"])

            if leftover_path_args:
                try:
                    node = node.get_node(leftover_path_args[0])
                    leftover_path_args = leftover_path_args[1:]

                except KeyError:
                    node = None

            else:
                node = None

        if rc_classes:
            request.path_positionals = leftover_path_args
            request.reflect_class = rc_classes[-1]

            ret["leftover_path_args"] = leftover_path_args
            ret["reflect_class"] = rc_classes[-1]

        else:
            raise TypeError(f"Unknown controller with path: {request.path}")

        return ret

    def find_modules(
        self,
        controller_prefixes: list[str],
        paths: list[str],
        **kwargs
        ) -> Iterable[ModuleType]:
        """Internal method. Finds all the modules

        This loads the controllers using the `controller_prefixes` or `paths`
        and returns all the found modules

        Controllers get loaded into memory using `Controller.__init_subclass__`
        so just finding all the modules will load the controllers that
        can be used to answer requests
        """
        if controller_prefixes:
            if isinstance(controller_prefixes, str):
                controller_prefixes = environ.split_value(controller_prefixes)

        else:
            controller_prefixes = environ.get_controller_prefixes()

        if not paths and not self.controller_class.controller_classes:
            paths = [Dirpath.cwd()]

        if controller_prefixes and logger.isEnabledFor(logging.DEBUG):
            for cp in controller_prefixes:
                logger.debug("Checking controller prefix: %s", cp)

#         pout.v(controller_prefixes, paths)

        return self.pathfinder_class.find_modules(
            controller_prefixes,
            paths,
            kwargs.get("autodiscover_name", environ.AUTODISCOVER_NAME),
        )

#     def create_router(self):
#         return self.router_class(
#             controller_prefixes=self.controller_prefixes,
#             controller_class=self.controller_class,
#             pathfinder_class=self.pathfinder_class,
#         )

    def create_controller(self, request, response, **kwargs):
        """Create a controller to handle the request

        :param request: Request
        :param response: Response
        :returns: Controller, this Controller instance should be able to
            handle the request
        """
        if "controller_class" in kwargs:
            controller_class = kwargs["controller_class"]

        else:
            request.controller_info = self.find_controller_info(
                request,
                **kwargs
            )

            rc = request.controller_info["reflect_class"]
            controller_class = rc.get_target()

        controller = controller_class(
            request,
            response,
            **kwargs
        )

        controller.application = self
        return controller

    def create_error_controller(self, request, response, **kwargs):
        if "controller_class" not in kwargs:
            controller_info = request.controller_info or {}
            if rc := controller_info.get("reflect_class", None):
                kwargs["controller_class"] = rc.get_target()

            else:
                kwargs["controller_class"] = self.controller_class

        return self.create_controller(request, response, **kwargs)

    async def handle(self, request, response, **kwargs) -> Controller:
        """Called from the interface to actually handle the request."""
        response.start = time.time()
        self.log_start(request, response)
        controller = None

        try:
            controller = self.create_controller(request, response)
            await controller.handle()

        except Exception as e:
            if controller is None:
                controller = self.create_error_controller(request, response)

            await controller.handle_error(e)
            #await self.handle_error(request, response, e, **kwargs)

        self.log_stop(request, response)

        return controller

