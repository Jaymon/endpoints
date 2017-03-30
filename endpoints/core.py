# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import re
import logging
import time
import datetime

from .exception import CallError, Redirect, CallStop, AccessDenied


logger = logging.getLogger(__name__)


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

    cors = True
    """Activates CORS support, http://www.w3.org/TR/cors/"""

    content_type = "application/json"
    """the response content type this endpoint is going to send"""

    encoding = 'UTF-8'
    """the response charset of this endpoint"""

    def __init__(self, request, response, *args, **kwargs):
        self.request = request
        self.response = response
        super(Controller, self).__init__(*args, **kwargs)
        self.set_cors_common_headers()

    def OPTIONS(self, *args, **kwargs):
        if not self.cors:
            raise CallError(405)

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
        if not self.cors: return

        req = self.request
        origin = req.get_header('origin')
        if origin:
            self.response.set_header('Access-Control-Allow-Origin', origin)

    def handle(self):
        """handles the request and returns the response

        :returns: Response instance, the response object with a body already"""
        body = None
        start = time.time()
        try:
            self.log_start(start)
            self.response.set_header('Content-Type', "{};charset={}".format(
                self.content_type,
                self.encoding
            ))

            encoding = self.request.accept_encoding
            self.response.encoding = encoding if encoding else self.encoding

            controller_method = self.request.controller_info["method"]
            controller_args = self.request.controller_info["method_args"]
            controller_kwargs = self.request.controller_info["method_kwargs"]
            body = controller_method(*controller_args, **controller_kwargs)

        except Exception as e:
            body = self.handle_error(e)

        finally:
            self.log_stop(start)

        return body

    def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        return self.interface.handle_error(e, req=self.request, res=self.response, **kwargs)

    def log_start(self, start):
        """log all the headers and stuff at the start of the request"""
        if not logger.isEnabledFor(logging.INFO): return

        try:
            req = self.request

            logger.info("REQUEST {} {}?{}".format(req.method, req.path, req.query))
            logger.info(datetime.datetime.strftime(datetime.datetime.utcnow(), "DATE %Y-%m-%dT%H:%M:%S.%f"))

            ip = req.ip
            if ip:
                hs.append("\tIP ADDRESS: {}".format(ip))

            if 'authorization' in req.headers:
                logger.info('AUTH {}'.format(req.headers['authorization']))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            hs = ["Request Headers..."]
            for k, v in req.headers.items():
                if k not in ignore_hs:
                    hs.append("\t{}: {}".format(k, v))

            logger.info(os.linesep.join(hs))

        except Exception as e:
            logger.warn(e, exc_info=True)

    def log_stop(self, start):
        """log a summary line on how the request went"""
        if not logger.isEnabledFor(logging.INFO): return

        stop = time.time()
        get_elapsed = lambda start, stop, multiplier, rnd: round(abs(stop - start) * float(multiplier), rnd)
        elapsed = get_elapsed(start, stop, 1000.00, 1)
        total = u"%0.1f ms" % (elapsed)
        logger.info("RESPONSE {} {} in {}".format(self.response.code, self.response.status, total))

