import os
import logging
import cgi
import json

from ..http import Request, Response
from ..call import Call, Router
from ..decorators import _property
from ..exception import CallError, Redirect, CallStop, AccessDenied


logger = logging.getLogger(__name__)


class BaseInterface(object):
    """all interfaces should extend this class to be able to interact correctly
    with the server

    The interface is what will translate raw requests into something that can be
    understood by endpoints
    """
    @_property
    def router(self):
        return self.create_router()

    def __init__(self, controller_prefix, request_class, response_class, call_class, router_class, **kwargs):
        self.controller_prefix = controller_prefix
        self.request_class = request_class
        self.response_class = response_class
        self.call_class = call_class
        self.router_class = router_class

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
        raise NotImplementedError()

    def create_response(self, **kwargs):
        """create the endpoints understandable response instance that is used to
        return output to the client"""
        return self.response_class()

    def create_call(self, raw_request, **kwargs):
        """create a call object that has endpoints understandable request and response
        instances"""
        c = self.call_class(self.controller_prefix)
        c.request = self.create_request(raw_request, **kwargs)
        c.response = self.create_response(**kwargs)
        return c

    def create_router(self, **kwargs):
        kwargs.setdefault('controller_prefix', self.controller_prefix)
        r = self.router_class(**kwargs)
        return r

    def _handle(self, req, res, rou):
        body = None
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

        finally:
            res.controller_info = controller_info
            controller_info['instance'].router = rou
            controller_info['instance'].interface = self

            logger.debug("handling request with callback {}.{}.{}".format(
                controller_info['module_name'],
                controller_info['class_name'],
                controller_info['method_name']
            ))

            body = controller_info['instance'].handle()

        return body

    def handle(self, raw_request=None, **kwargs):
        body, res, req = None, None, None

        try:
            req = self.create_request(raw_request, **kwargs)
            res = self.create_response(**kwargs)
            rou = self.router
            body = self._handle(req, res, rou)

        except Exception as e:
            # if anything gets to here we've messed up because we threw an error before
            # the controller's error handler could handle it :(
            body = self.handle_error(e, req=req, res=res)

        finally:
            if res.code == 204:
                res.headers.pop('Content-Type', None)
                res.body = None
            else:
                res.body = body

        return res

    def handle_error(self, e, req=None, res=None, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        ret = None
        if isinstance(e, CallStop):
            logger.info(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            ret = e.body

        elif isinstance(e, Redirect):
            logger.info(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            ret = None

        elif isinstance(e, (AccessDenied, CallError)):
            logger.warning(str(e), exc_info=True)
            res.code = e.code
            res.add_headers(e.headers)
            ret = e

        elif isinstance(e, NotImplementedError):
            logger.warning(str(e), exc_info=True)
            res.code = 501

        elif isinstance(e, TypeError):
            e_msg = unicode(e)
            if e_msg.startswith(req.method) and 'argument' in e_msg:
                logger.debug(e_msg, exc_info=True)
                res.code = 404

            else:
                logger.exception(e)
                res.code = 500

        else:
            logger.exception(e)
            res.code = 500
            ret = e

        return ret


class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers

    A server is different from the interface because the server is actually responsible
    for serving the requests, while the interface will translate the requests to
    and from endpoints itself into something the server backend can understand

    So the path is backend -> Server (this class) -> interface request -> endpoints
    -> interface response -> Server (this class) -> backend
    """
    controller_prefix = ''
    """the controller prefix you want to use to find your Controller subclasses"""

    interface_class = None
    """the interface that should be used to translate between the supported server"""

    backend_class = None
    """the supported server's interface, there is no common interface for this class.
    Basically it is the raw backend class that the BaseServer child is translating
    for endpoints compatibility"""

    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    response_class = Response
    """the endpoints.http.Response compatible class that should be used to make
    Response() instances"""

    call_class = Call
    """the endpoints.call.Call compatible class that should be used to make a
    Call() instance"""

    router_class = Router
    """the endpoints.call.Router compatible class that hadnles translating a request
    into the Controller class and method that will actual run"""

    @_property
    def interface(self):
        return self.create_interface()

    @_property
    def backend(self):
        return self.create_backend()

    def __init__(self, controller_prefix='', **kwargs):
        if controller_prefix:
            self.controller_prefix = controller_prefix
        else:
            self.controller_prefix = os.environ.get('ENDPOINTS_PREFIX', '')

        classes = [
            "interface_class",
            "backend_class",
            "request_class",
            "response_class",
            "call_class",
            "router_class",
        ]
        for k in classes:
            if k in kwargs:
                setattr(self, k, kwargs[k])

    def create_interface(self, **kwargs):
        kwargs.setdefault('call_class', self.call_class)
        kwargs.setdefault('request_class', self.request_class)
        kwargs.setdefault('response_class', self.response_class)
        kwargs.setdefault('router_class', self.router_class)
        kwargs.setdefault('controller_prefix', self.controller_prefix)
        return self.interface_class(**kwargs)

    def create_backend(self, **kwargs):
        return self.backend_class(**kwargs)

    def handle_request(self):
        raise NotImplementedError()

    def serve_forever(self):
        try:
            while True: self.handle_request()
        except Exception as e:
            logger.exception(e)
            raise

    def serve_count(self, count):
        try:
            handle_count = 0
            while handle_count < count:
                self.handle_request()
                handle_count += 1
        except Exception as e:
            logger.exception(e)
            raise

