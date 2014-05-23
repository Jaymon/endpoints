import os

from ..http import Request
from ..call import Call

class BaseInterface(object):
    request_class = Request
    """the endpoints.http.Request compatible class that should be used to make
    Request() instances"""

    call_class = Call
    """the endpoints.call.Call compatible class that should be used to make a
    Call() instance"""

    def __init__(self, controller_prefix='', request_class=None, call_class=None, *args, **kwargs):
        self.controller_prefix = controller_prefix

        if request_class:
            self.request_class = request_class

        if call_class:
            self.call_class = call_class

    def create_request(self, *args, **kwargs):
        raise NotImplemented()

    def create_call(self, *args, **kwargs):
        kwargs.setdefault('call_class', self.call_class)
        kwargs.setdefault('request_class', self.request_class)

        if not self.controller_prefix:
            self.controller_prefix = os.environ.get('ENDPOINTS_PREFIX', '')

        call_class = kwargs['call_class']
        c = call_class(self.controller_prefix)
        c.request = self.create_request(*args, **kwargs)
        return c

    def handle(self, *args, **kwargs):
        c = self.create_call(*args, **kwargs)
        return c.ghandle()

