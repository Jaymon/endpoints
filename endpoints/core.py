import inspect
import re

from .exception import CallError


class CorsMixin(object):
    """
    Use this mixin if you want your controller to support cross site scripting
    requests. Adding this to your controller should be all you need to do to allow
    the endpoint to start accepting CORS requests

    ---------------------------------------------------------------------------
    import endpoints

    class Cors(endpoints.Controller, endpoints.CorsMixin):
        def POST(self, *args, **kwargs):
            return "you just made a POST preflighted cors request"
    ---------------------------------------------------------------------------

    spec -- http://www.w3.org/TR/cors/
    """
    def __init__(self, *args, **kwargs):
        super(CorsMixin, self).__init__(*args, **kwargs)
        self.set_cors_common_headers()

    def OPTIONS(self, *args, **kwargs):
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

    def set_cors_common_headers(self):
        """
        This will set the headers that are needed for any cors request (OPTIONS or real)
        """
        req = self.request
        origin = req.get_header('origin')
        if origin:
            self.response.set_header('Access-Control-Allow-Origin', origin)


class Controller(object):
    """
    this is the interface for a Controller sub class

    All your controllers MUST extend this base class, since it ensures a proper interface :)

    to activate a new endpoint, just add a module on your PYTHONPATH.controller_prefix that has a class
    that extends this class, and then defines at least one option method (like GET or POST), so if you
    wanted to create the endpoint /foo/bar (with controller_prefix che), you would just need to:

    ---------------------------------------------------------------------------
    # che/foo.py
    import endpoints

    class Bar(endpoints.Controller):
        def GET(self, *args, **kwargs):
            return "you just made a GET request to /foo/bar"
    ---------------------------------------------------------------------------

    as you support more methods, like POST and PUT, you can just add POST() and PUT()
    methods to your Bar class and Bar will support those http methods. Although you can
    request any method (a method is valid if it is all uppercase), here is a list of
    rfc approved http request methods:

    http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

    If you would like to create a base controller that other controllers will extend and don't
    want that controller to be picked up by reflection, just start the classname with an underscore:

    ---------------------------------------------------------------------------
    import endpoints

    class _BaseController(endpoints.Controller):
        def GET(self, *args, **kwargs):
            return "every controller that extends this will have this GET method"
    ---------------------------------------------------------------------------
    """
    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    call = None
    """holds the call() instance that invoked this Controller"""

    private = False
    """set this to True if the controller should not be picked up by reflection, the controller
    will still be available, but reflection will not reveal it as an endpoint"""

    def __init__(self, request, response, *args, **kwargs):
        self.request = request
        self.response = response
        super(Controller, self).__init__(*args, **kwargs)

