import os
import logging
import cgi
import json

from ..http import Request, Response
from ..call import Call


logger = logging.getLogger(__name__)


class BaseInterface(object):
    """all interfaces should extend this class to be able to interact correctly
    with the server"""
    def __init__(self, controller_prefix, request_class, response_class, call_class, **kwargs):
        self.controller_prefix = controller_prefix
        self.request_class = request_class
        self.response_class = response_class
        self.call_class = call_class

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
        raise NotImplemented()

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

    def handle(self, raw_request=None, **kwargs):
        c = self.create_call(raw_request=raw_request, **kwargs)
        return c.handle()

    def normalize_body_kwargs(self, content_type, body, raw_request):
        body_kwargs = {}
        ct = content_type.lower()
        if ct.rfind("json") >= 0:
            body_kwargs = json.loads(body)

        else:
        #elif ct.rfind(u"x-www-form-urlencoded") >= 0:
            body_fields = cgi.FieldStorage(
                fp=body,
                environ=raw_request,
                keep_blank_values=True
            )
            for field_name in body_fields.keys():
                body_field = body_fields[field_name]
                if body_field.filename:
                    body_kwargs[field_name] = body_field
                else:
                    body_kwargs[field_name] = body_field.value

        # elif ct.rfind(u"multipart/form-data") >= 0:
        return body_kwargs


class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers"""
    controller_prefix = ''
    """the controller prefix you want to use to find your Controller subclasses"""

    interface_class = None
    """the interface that should be used to translate between the supported server"""

    server_class = None
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

    def __init__(self, controller_prefix='', **kwargs):
        if controller_prefix:
            self.controller_prefix = controller_prefix
        if not self.controller_prefix:
            self.controller_prefix = os.environ.get('ENDPOINTS_PREFIX', '')

    def create_interface(self, **kwargs):
        kwargs.setdefault('call_class', self.call_class)
        kwargs.setdefault('request_class', self.request_class)
        kwargs.setdefault('response_class', self.response_class)
        kwargs.setdefault('controller_prefix', self.controller_prefix)
        return self.interface_class(**kwargs)

    def create_server(self, **kwargs):
        return self.server_class(**kwargs)

    def handle_request(self):
        raise NotImplemented()

    def serve_forever(self):
        self.prepare()
        try:
            while True: self.handle_request()
        except Exception as e:
            logger.exception(e)
            raise

    def serve_count(self, count):
        self.prepare()
        try:
            handle_count = 0
            while handle_count < count:
                self.handle_request()
                handle_count += 1
        except Exception as e:
            logger.exception(e)
            raise

    def prepare(self):
        """this should be called in all request handling methods to make sure the
        internal object is "ready" to process requests"""
        if not hasattr(self, "interface"):
            self.interface = self.create_interface()

        if not hasattr(self, "server"):
            self.server = self.create_server()

