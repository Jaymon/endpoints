
from . import BaseInterface
from ..http import Request as BaseRequest


class Request(BaseRequest):
    pass

class Mongrel2(BaseInterface):

    request_class = Request

    def create_request(self, raw_request, *args, **kwargs):
        """
        create instance of request

        raw_request -- mongrel2.request.Request() -- the request object retrieved from mongrel2
        """
        r = kwargs['request_class']()
        r.raw_request = raw_request

        # separate environ from headers
        environ = {}
        headers = {}

        environ_ks = set([
            'PATTERN',
            'PATH',
            'QUERY',
            'URI',
            'METHOD',
            'VERSION',
            'URL_SCHEME',
            'REMOTE_ADDR'
        ])
        for k, v in raw_request.headers.iteritems():
            if k in environ_ks:
                environ[k] = v

            else:
                headers[k] = v

        r.headers = headers
        r.environ = environ

        r.path = environ.get(u'PATH', u"/")
        r.query = environ.get(u'QUERY', u"")
        r.method = environ.get(u'METHOD', u"GET")

        # make sure body is None if it is empty
        body = getattr(raw_request, 'body', None)
        if not body: body = None
        r.body = body

        return r

