import os

from ..http import Request
from ..call import Call

class BaseInterface(object):
    """all interfaces should extend this class to be able to interact correctly
    with the server"""
    def __init__(self, controller_prefix, request_class, call_class, **kwargs):
        self.controller_prefix = controller_prefix
        self.request_class = request_class
        self.call_class = call_class

    def create_request(self, raw_request, **kwargs):
        raise NotImplemented()

    def create_call(self, raw_request, **kwargs):
        c = self.call_class(self.controller_prefix)
        c.request = self.create_request(raw_request, **kwargs)
        return c

    def handle(self, raw_request=None, **kwargs):
        c = self.create_call(raw_request=raw_request, **kwargs)
        return c.ghandle()


class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers"""
    controller_prefix = ''
    """the controller prefix you want to use to find your Controller subclasses"""

    interface_class = None
    """the interface that should be used to translate between the supported server"""

    server_class = None
    """the supported server's interface"""

    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    call_class = Call
    """the endpoints.call.Call compatible class that should be used to make a
    Call() instance"""

    def __init__(self, controller_prefix='', interface_class=None, server_class=None, request_class=None, call_class=None, **kwargs):
        if controller_prefix:
            self.controller_prefix = controller_prefix
        else:
            self.controller_prefix = os.environ.get('ENDPOINTS_PREFIX', '')

        if interface_class:
            self.interface_class = interface_class

        if server_class:
            self.server_class = server_class

        if request_class:
            self.request_class = request_class

        if call_class:
            self.call_class = call_class

        self.interface = self.create_interface(**kwargs)
        self.server = self.create_server(**kwargs)

    def create_interface(self, **kwargs):
        kwargs.setdefault('call_class', self.call_class)
        kwargs.setdefault('request_class', self.request_class)
        kwargs.setdefault('controller_prefix', self.controller_prefix)
        return self.interface_class(**kwargs)

    def create_server(self, **kwargs):
        return self.server_class(**kwargs)

    def handle_request(self):
        raise NotImplemented()

    def serve_forever(self):
        while True: self.handle_request()

    def serve_count(self, count):
        handle_count = 0
        while handle_count < count:
            self.handle_request()
            handle_count += 1

