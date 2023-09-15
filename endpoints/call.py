# -*- coding: utf-8 -*-
import time
import datetime
import logging
import os
import inspect
import json
import re
import io

from .compat import *
from .utils import AcceptHeader
from .exception import (
    CallError,
    RouteError,
    VersionError,
)
from .config import environ

from datatypes import (
    HTTPHeaders as Headers,
    property as cachedproperty,
)

from .compat import *
from .utils import (
    AcceptHeader,
    MimeType,
    Base64,
    Deepcopy,
    Url,
    Status,
)


logger = logging.getLogger(__name__)


class Controller(object):
    """
    this is the interface for a Controller sub class

    All your controllers MUST extend this base class, since it ensures a proper
    interface :)

    to activate a new endpoint, just add a module on your PYTHONPATH
    controller_prefix that has a class that extends this class, and then defines
    at least one http method (like GET or POST), so if you wanted to create the
    endpoint /foo/bar (with controller_prefix che), you would just need to:

    :Example:
        # che/foo.py
        import endpoints

        class Bar(endpoints.Controller):
            def GET(self, *args, **kwargs):
                return "you just made a GET request to /foo/bar"

    as you support more methods, like POST and PUT, you can just add POST() and
    PUT() methods to your Bar class and Bar will support those http methods.
    Although you can request any method (a method is valid if it is all
    uppercase), here is a list of rfc approved http request methods:

        http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

    If you would like to create a base controller that other controllers will
    extend and don't want that controller to be picked up by reflection, just
    start the classname with an underscore:

    :Example:
        import endpoints

        class _BaseController(endpoints.Controller):
            def GET(self, *args, **kwargs):
                return "every child that extends this will have this GET method"
    """
    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    private = False
    """set this to True if the controller should not be picked up by reflection,
    the controller will still be available, but reflection will not reveal it as
    an endpoint"""

    cors = True
    """Activates CORS support, http://www.w3.org/TR/cors/"""

    @cachedproperty(cached="_encoding")
    def encoding(self):
        """the response charset of this controller"""
        req = self.request
        encoding = req.accept_encoding
        return encoding if encoding else environ.ENCODING

    @cachedproperty(cached="_content_type")
    def content_type(self):
        """the response content type this controller will use"""
        req = self.request
        content_type = req.accept_content_type
        return content_type if content_type else environ.RESPONSE_CONTENT_TYPE

    def __init__(self, request, response, **kwargs):
        self.request = request
        self.response = response
        self.logger = self.create_logger(request, response)

    async def OPTIONS(self, *args, **kwargs):
        """Handles CORS requests for this controller

        if self.cors is False then this will raise a 405, otherwise it sets
        everything necessary to satisfy the request in self.response
        """
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

    async def prepare_response(self):
        """Called at the beginning of the handle() call, use to prepare the
        response instance with defaults that can be overridden in the
        controller's actual http handle method"""
        req = self.request
        res = self.response

        encoding = self.encoding
        content_type = self.content_type

        res.encoding = encoding
        res.set_header('Content-Type', "{};charset={}".format(
            content_type,
            encoding
        ))

    async def handle_origin(self, origin):
        """Check the origin and decide if it is valid

        :param origin: string, this can be empty or None, so you'll need to handle
            the empty case if you are overriding this
        :returns: bool, True if the origin is acceptable, False otherwise
        """
        return True

    async def handle_cors(self):
        """This will set the headers that are needed for any cors request
        (OPTIONS or real) """
        req = self.request
        origin = req.get_header('origin')
        if await self.handle_origin(origin):
            if origin:
                # your server must read the value of the request's Origin header
                # and use that value to set Access-Control-Allow-Origin, and must
                # also set a Vary: Origin header to indicate that some headers
                # are being set dynamically depending on the origin.
                # https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS/Errors/CORSMissingAllowOrigin
                # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Origin
                self.response.set_header('Access-Control-Allow-Origin', origin)
                self.response.set_header('Vary', "Origin")

        else:
            # RFC6455 - If the origin indicated is unacceptable to the server,
            # then it SHOULD respond to the WebSocket handshake with a reply
            # containing HTTP 403 Forbidden status code.
            # https://stackoverflow.com/q/28553580/5006
            raise CallError(403)

    async def handle(self, *controller_args, **controller_kwargs):
        """handles the request and returns the response

        This should set any response information directly onto self.response

        this method has the same signature as the request handling methods
        (eg, GET, POST) so subclasses can override this method and add decorators

        :param *controller_args: tuple, the path arguments that will be passed to
            the request handling method (eg, GET, POST)
        :param **controller_kwargs: dict, the query and body params merged together
        """
        if self.cors:
            await self.handle_cors()

        await self.prepare_response()

        req = self.request
        res = self.response

        # the @route* and @version decorators have a catastrophic error handler
        # that will be called if all found methods failed to resolve
        res_error_handler = None

        controller_methods = await self.find_methods()
        for controller_method_name, controller_method in controller_methods:
            req.controller_info["method_name"] = controller_method_name
            req.controller_info["method"] = controller_method
            # VersionError and RouteError handling is here because they can be
            # raised multiple times in this one request and handled each time,
            # any exceptions that can't be handled are bubbled up
            try:
                self.logger.debug("Request Controller method: {}.{}.{}".format(
                    req.controller_info['module_name'],
                    req.controller_info['class_name'],
                    controller_method_name
                ))

                if inspect.iscoroutinefunction(controller_method):
                    res.body = await controller_method(
                        *controller_args,
                        **controller_kwargs
                    )

                else:
                    res.body = controller_method(
                        *controller_args,
                        **controller_kwargs
                    )

                res_error_handler = None
                break

            except VersionError as e:
                if not res_error_handler:
                    res_error_handler = getattr(
                        e.instance,
                        "handle_failure",
                        None
                    )

                self.logger.debug(
                    " ".join([
                        "Request Controller method: {}.{}.{}".format(
                            req.controller_info['module_name'],
                            req.controller_info['class_name'],
                            controller_method_name,
                        ),
                        "failed version check [{} not in {}]".format(
                            e.request_version,
                            e.versions,
                        ),
                    ])
                )

            except RouteError as e:
                if not res_error_handler:
                    res_error_handler = getattr(
                        e.instance,
                        "handle_failure",
                        None
                    )

                self.logger.debug(
                    " ".join([
                        "Request Controller method: {}.{}.{}".format(
                            req.controller_info['module_name'],
                            req.controller_info['class_name'],
                            controller_method_name,
                        ),
                        "failed routing check",
                    ])
                )

        if res_error_handler:
            await res_error_handler(self)

    async def handle_error(self, e, **kwargs):
        """if an exception is raised while trying to handle the request it will
        go through this method, this method is called from the Call instance

        :param e: Exception, the error that was raised
        :param **kwargs: dict, any other information that might be handy
        """
        pass

    async def find_methods(self):
        """Find the methods that could satisfy this request

        This will go through and find any method that starts with the request.method,
        so if the request was GET /foo then this would find any methods that start
        with GET

        https://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html

        :returns: list of tuples (method_name, method), all the found methods
        """
        methods = []
        req = self.request
        controller_info = req.controller_info
        method_name = controller_info["method_prefix"]
        method_names = set()

        members = inspect.getmembers(self)
        for member_name, member in members:
            if member_name.startswith(method_name):
                if member:
                    methods.append((member_name, member))
                    method_names.add(member_name)

        if len(methods) == 0:
            fallback_method_name = controller_info["method_fallback"]
            any_method = getattr(self, fallback_method_name, "")
            if any_method:
                methods.append((fallback_method_name, any_method))

            else:
                if len(controller_info["method_args"]):
                    # if we have method args and we don't have a method to even
                    # answer the request it should be a 404 since the path is
                    # invalid
                    raise CallError(
                        404,
                        "Could not find a {} method for path {}".format(
                            method_name,
                            req.path,
                        )
                    )

                else:
                    # https://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1
                    # and 501 (Not Implemented) if the method is unrecognized or not
                    # implemented by the origin server
                    self.logger.warning(
                        "No methods to handle {} found".format(method_name)
                    )
                    raise CallError(
                        501,
                        "{} {} not implemented".format(req.method, req.path)
                    )

        elif len(methods) > 1 and method_name in method_names:
            raise ValueError(
                " ".join([
                    "A multi method {} request should not have any methods named {}.",
                    "Instead, all {} methods should use use an appropriate decorator",
                    "like @route or @version and have a unique name starting with {}_"
                ]).format(
                    method_name,
                    method_name,
                    method_name,
                    method_name
                )
            )

        return methods

    def create_logger(self, request, response):
        # we use self.logger and set the name to endpoints.call.module.class so
        # you can filter all controllers using endpoints.call, filter all
        # controllers in a certain module using endpoints.call.module or just a
        # specific controller using endpoints.call.module.class
        logger_name = logger.name
        module_name = self.__class__.__module__
        class_name = self.__class__.__name__
        return logging.getLogger("{}.{}.{}".format(
            logger_name,
            module_name,
            class_name,
        ))

    def log_start(self, start):
        """log all the headers and stuff at the start of the request"""
        if not self.logger.isEnabledFor(logging.INFO): return

        try:
            req = self.request
            uuid = getattr(req, "uuid", "")
            if uuid:
                uuid += " "

            if req.query:
                self.logger.info("Request {}method: {} {}?{}".format(
                    uuid,
                    req.method,
                    req.path,
                    req.query
                ))

            else:
                self.logger.info("Request {}method: {} {}".format(
                    uuid,
                    req.method,
                    req.path
                ))

            self.logger.info("Request {}date: {}".format(
                uuid,
                datetime.datetime.utcfromtimestamp(start).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                ),
            ))

            ip = req.ip
            if ip:
                self.logger.info("Request {}IP address: {}".format(uuid, ip))

            if 'authorization' in req.headers:
                self.logger.info('Request {}auth: {}'.format(
                    uuid,
                    req.headers['authorization']
                ))

            ignore_hs = set([
                'accept-language',
                'accept-encoding',
                'connection',
                'authorization',
                'host',
                'x-forwarded-for'
            ])
            #hs = []
            for k, v in req.headers.items():
                if k not in ignore_hs:
                    self.logger.info("Request {}header {}: {}".format(uuid, k, v))
                    #hs.append("Request header: {}: {}".format(k, v))

            #self.logger.info(os.linesep.join(hs))
            self.log_start_body()

        except Exception as e:
            self.logger.warn(e, exc_info=True)

    def log_start_body(self):
        """Log the request body

        this is separate from log_start so it can be easily overridden in children
        """
        if not self.logger.isEnabledFor(logging.DEBUG): return

        req = self.request
        uuid = getattr(req, "uuid", "")
        if uuid:
            uuid += " "

        if req.has_body():
            try:
                self.logger.debug("Request {}body: {}".format(uuid, req.body_kwargs))

            except Exception:
                self.logger.debug("Request {}body raw: {}".format(uuid, req.body))
                #logger.debug("RAW REQUEST: {}".format(req.raw_request))
                raise

    def log_stop(self, start):
        """log a summary line on how the request went"""
        if not self.logger.isEnabledFor(logging.INFO): return

        res = self.response
        req = self.request
        if uuid := getattr(req, "uuid", ""):
            uuid += " "

        for k, v in res.headers.items():
            self.logger.info("Response {}header {}: {}".format(uuid, k, v))

        stop = time.time()
        def get_elapsed(start, stop, multiplier, rnd):
            return round(abs(stop - start) * float(multiplier), rnd)
        elapsed = get_elapsed(start, stop, 1000.00, 1)
        total = "%0.1f ms" % (elapsed)
        self.logger.info("Response {}{} {} in {}".format(
            uuid,
            self.response.code,
            self.response.status,
            total
        ))


class Call(object):
    header_class = Headers

    def __init__(self):
        self.headers = Headers()

    def has_header(self, header_name):
        """return true if the header is set"""
        return header_name in self.headers

    def set_headers(self, headers):
        """replace all headers with passed in headers"""
        self.headers = Headers(headers)

    def add_headers(self, headers, **kwargs):
        self.headers.update(headers, **kwargs)

    def set_header(self, header_name, val):
        self.headers[header_name] = val

    def add_header(self, header_name, val, **params):
        self.headers.add_header(header_name, val, **params)

    def get_header(self, header_name, default_val=None, allow_empty=True):
        """try as hard as possible to get a a response header of header_name,
        return default_val if it can't be found"""
        v = self.headers.get(header_name, default_val)
        if v:
            return v

        else:
            if not allow_empty:
                return default_val

    def find_header(self, header_names, default_val=None, allow_empty=True):
        """given a list of headers return the first one you can, default_val if
        you don't find any

        :param header_names: list, a list of headers, first one found is
            returned
        :param default_val: mixed, returned if no matching header is found
        :returns: mixed, the value of the header or default_val
        """
        ret = default_val
        for header_name in header_names:
            if self.has_header(header_name):
                ret = self.get_header(header_name, default_val)
                if ret or allow_empty:
                    break

        if not ret and not allow_empty:
            ret = default_val

        return ret

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        u = Url(query=query)
        return u.query_kwargs

    def _build_body_str(self, b):
        # we are returning the body, let's try and be smart about it and match
        # content type
        ct = self.get_header('content-type')
        if ct:
            ct = ct.lower()
            if ct.rfind("json") >= 0:
                if b:
                    b = json.dumps(b)
                else:
                    b = None

            elif ct.rfind("x-www-form-urlencoded") >= 0:
                b = urlencode(b, doseq=True)

        return b

    def copy(self):
        """nice handy wrapper around the deepcopy"""
        return self.__deepcopy__()

    def __deepcopy__(self, memodict=None):
        memodict = memodict or {}

        memodict.setdefault("controller_info", None)
        memodict.setdefault("raw_request", None)
        memodict.setdefault("body", getattr(self, "body", None))

        #return Deepcopy(ignore_private=True).copy(self, memodict)
        return Deepcopy().copy(self, memodict)

    def is_json(self):
        return self.headers.is_json()


class Request(Call):
    '''
    common interface that endpoints uses to decide what to do with the incoming
    request

    an instance of this class is used by the endpoints Call instance to decide
    where endpoints should route requests, so, many times, you'll need to write
    a glue function that takes however your request data is passed to Python and
    convert it into a Request instance that endpoints can understand

    properties:
        * headers -- a dict of all the request headers
        * path -- the /path/part/of/the/url
        * path_args -- tied to path, it's path, but divided by / so all the path
            bits are returned as a list
        * query -- the ?name=val portion of a url
        * query_kwargs -- tied to query, the values in query but converted to a
            dict {name: val}
    '''
    raw_request = None
    """the original raw request that was filtered through one of the interfaces"""

    method = None
    """the http method (GET, POST)"""

    controller_info = None
    """will hold the controller information for the request, populated from the Call"""

    @cachedproperty(cached="_uuid")
    def uuid(self):
        # if there is an X-uuid header then set uuid and send it down
        # with every request using that header
        # https://stackoverflow.com/questions/18265128/what-is-sec-websocket-key-for
        uuid = None

        # first try and get the uuid from the body since javascript has limited
        # capability of setting headers for websockets
        kwargs = self.kwargs
        if "uuid" in kwargs:
            uuid = kwargs["uuid"]

        # next use X-UUID header, then the websocket key
        if not uuid:
            uuid = self.find_header(["X-UUID", "Sec-Websocket-Key"])

        return uuid or ""

    @cachedproperty(cached="_accept_content_type")
    def accept_content_type(self):
        """Return the requested content type

        https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

        :returns: string, empty if a suitable content type wasn't found, this will
            only check the first accept content type and then only if that content
            type has no wildcards
        """
        v = ""
        accept_header = self.get_header('accept', "")
        if accept_header:
            a = AcceptHeader(accept_header)
            for mt in a:
                # we only care about the first value, and only if it has no wildcards
                if "*" not in mt[0]:
                    v = "/".join(mt[0])
                break

        return v

    @cachedproperty(cached="_accept_encoding")
    def accept_encoding(self):
        """The encoding the client requested the response to use"""
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Charset
        ret = ""
        accept_encoding = self.get_header("Accept-Charset", "")
        if accept_encoding:
            bits = re.split(r"\s+", accept_encoding)
            bits = bits[0].split(";")
            ret = bits[0]
        return ret

    @cachedproperty(cached="_encoding")
    def encoding(self):
        """the character encoding of the request, usually only set in POST type requests"""
        encoding = None
        ct = self.get_header('content-type')
        if ct:
            ah = AcceptHeader(ct)
            if ah.media_types:
                encoding = ah.media_types[0][2].get("charset", None)

        return encoding

    @property
    def access_token(self):
        """return an Oauth 2.0 Bearer access token if it can be found"""
        access_token = self.get_auth_bearer()
        if not access_token:
            access_token = self.query_kwargs.get('access_token', '')
            if not access_token:
                access_token = self.body_kwargs.get('access_token', '')

        return access_token

    @property
    def client_tokens(self):
        """try and get Oauth 2.0 client id and secret first from basic auth header,
        then from GET or POST parameters

        return -- tuple -- client_id, client_secret
        """
        client_id, client_secret = self.get_auth_basic()

        if not client_id:
            client_id = self.query_kwargs.get('client_id', '')
            if not client_id:
                client_id = self.body_kwargs.get('client_id', '')

        if not client_secret:
            client_secret = self.query_kwargs.get('client_secret', '')
            if not client_secret:
                client_secret = self.body_kwargs.get('client_secret', '')

        return client_id, client_secret

    @cachedproperty(read_only="_ips")
    def ips(self):
        """return all the possible ips of this request, this will include public
        and private ips"""
        r = []
        names = ['X_FORWARDED_FOR', 'CLIENT_IP', 'X_REAL_IP', 'X_FORWARDED', 
               'X_CLUSTER_CLIENT_IP', 'FORWARDED_FOR', 'FORWARDED', 'VIA',
               'REMOTE_ADDR']

        for name in names:
            vs = self.get_header(name, '')
            if vs:
                r.extend(map(lambda v: v.strip(), vs.split(',')))

        return r

    @cachedproperty(read_only="_ip")
    def ip(self):
        """return the public ip address"""
        r = ''

        # this was compiled from here:
        # https://github.com/un33k/django-ipware
        # http://www.ietf.org/rfc/rfc3330.txt (IPv4)
        # http://www.ietf.org/rfc/rfc5156.txt (IPv6)
        # https://en.wikipedia.org/wiki/Reserved_IP_addresses
        format_regex = re.compile(r'\s')
        ip_regex = re.compile(r'^(?:{})'.format(r'|'.join([
            r'0\.', # reserved for 'self-identification'
            r'10\.', # class A
            r'169\.254', # link local block
            r'172\.(?:1[6-9]|2[0-9]|3[0-1])\.', # class B
            r'192\.0\.2\.', # documentation/examples
            r'192\.168', # class C
            r'255\.{3}', # broadcast address
            r'2001\:db8', # documentation/examples
            r'fc00\:', # private
            r'fe80\:', # link local unicast
            r'ff00\:', # multicast
            r'127\.', # localhost
            r'\:\:1' # localhost
        ])))

        ips = self.ips
        for ip in ips:
            if not format_regex.search(ip) and not ip_regex.match(ip):
                r = ip
                break

        return r

    @cachedproperty(cached="_host")
    def host(self):
        """return the request host"""
        return self.get_header("host")

    @cachedproperty(cached="_scheme")
    def scheme(self):
        """return the request scheme (eg, http, https)"""
        return "http"

    @cachedproperty(cached="_port")
    def port(self):
        """return the server port"""
        _, port = Url.split_hostname_from_port(self.host)
        return port

    @property
    def url(self):
        """return the full request url as an Url() instance"""
        scheme = self.scheme
        host = self.host
        path = self.path
        query = self.query
        port = self.port

        # normalize the port
        hostname, host_port = Url.split_hostname_from_port(host)
        if host_port:
            port = host_port

        class_path = ""
        module_path = ""
        if self.controller_info:
            class_path = self.controller_info.get("class_path", "")
            module_path = self.controller_info.get("module_path", "")

        u = Url(
            scheme=scheme,
            hostname=hostname,
            path=path,
            query=query,
            port=port,
            class_path=class_path,
            module_path=module_path
        )
        return u

    @cachedproperty(cached="_path")
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        self._path = ''
        path_args = self.path_args
        path = "/{}".format("/".join(path_args))
        return path

    @cachedproperty(cached="_path_args")
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        self._path_args = []
        path = self.path
        path_args = list(filter(None, path.split('/')))
        return path_args

    @cachedproperty(cached="_query")
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)"""
        self._query = query = ""

        query_kwargs = self.query_kwargs
        if query_kwargs: query = urlencode(query_kwargs, doseq=True)
        return query

    @cachedproperty(cached="_query_kwargs")
    def query_kwargs(self):
        """{foo: bar, baz: che}"""
        self._query_kwargs = query_kwargs = {}
        query = self.query
        if query: query_kwargs = self._parse_query_str(query)
        return query_kwargs

    @property
    def kwargs(self):
        """combine GET and POST params to be passed to the controller"""
        kwargs = dict(self.query_kwargs)
        kwargs.update(self.body_kwargs)
        return kwargs

    def __init__(self):
        self.body = None
        self.body_args = []
        self.body_kwargs = {}
        super().__init__()

    def version(self, content_type="*/*"):
        """by default, versioning is based off of this post 
        http://urthen.github.io/2013/05/09/ways-to-version-your-api/
        https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

        This can be extended to implement versioning in any other way though,
        this is used with the @version decorator

        :param content_type: string, the content type you want to check version
            info, by default this checks all content types, which is probably
            what most want, since if you're doing accept header versioning
            you're probably only passing up one content type
        :returns: string, the found version
        """
        v = ""
        accept_header = self.get_header('accept', "")
        if accept_header:
            a = AcceptHeader(accept_header)
            for mt in a.filter(content_type):
                v = mt[2].get("version", "")
                if v: break

        return v

    def is_method(self, method):
        """return True if the request method matches the passed in method"""
        return self.method.upper() == method.upper()

    def has_body(self):
        #return self.method.upper() in set(['POST', 'PUT'])
        return True if (self.body_kwargs or self.body_args) else False
        #return True if self.body_kwargs else False
        #return self.method.upper() not in set(['GET'])

    def get_auth_bearer(self):
        """return the bearer token in the authorization header if it exists"""
        access_token = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^Bearer\s+(\S+)$", auth_header, re.I)
            if m: access_token = m.group(1)

        return access_token

    def get_auth_basic(self):
        """return the username and password of a basic auth header if it exists
        """
        username = ''
        password = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^Basic\s+(\S+)$", auth_header, re.I)
            if m:
                auth_str = Base64.decode(m.group(1))
                username, password = auth_str.split(':', 1)

        return username, password

    def get_auth_scheme(self):
        """The authorization header is defined like:

            Authorization = credentials
            credentials = auth-scheme TOKEN_VALUE
            auth-scheme = token

        which roughly translates to:

            Authorization: token TOKEN_VALUE

        This returns the token part of the auth header's value

        :returns: string, the authentication scheme (eg, Bearer, Basic)
        """
        scheme = ""
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(r"^(\S+)\s+", auth_header)
            if m:
                scheme = m.group(1)
        return scheme

    def is_auth(self, scheme):
        """Return True if scheme matches the authorization scheme

        :Example:
            # Authorization: Basic FOOBAR
            request.is_auth("basic") # True
            request.is_auth("bearer") # False
        """
        return scheme.lower() == self.get_auth_scheme().lower()

    def is_oauth(self, scheme):
        """Similar to .is_auth() but checks for a wider range of names and also
        will check for values like "client_id" and "client_secret" being passed
        up in the body because javascript doesn't want to set headers in
        websocket connections

        :param scheme: string, the scheme you want to check, usually "basic" or
            "bearer"
        :return: boolean
        """
        scheme = scheme.lower()
        if scheme in set(["bearer", "token", "access"]):
            access_token = self.access_token
            return True if access_token else False

        elif scheme in set(["basic", "client"]):
            client_id, client_secret = self.client_tokens
            return True if (client_id and client_secret) else False


class Response(Call):
    """The Response object, every request instance that comes in will get a
    corresponding Response instance that answers the Request.

    an instance of this class is used to create the text response that will be
    sent back to the client

    Request has a ._body and .body, the ._body property is the raw value that is
    returned from the Controller method that handled the request, the .body
    property is a string that is ready to be sent back to the client, so it is
    _body converted to a string. The reason _body isn't name body_kwargs is
    because _body can be almost anything (not just a dict)
    """
    encoding = ""

    error = None
    """Will contain any raised exception"""

    @cachedproperty(cached="_code", onget=False)
    def code(self):
        """the http status code to return to the client, by default, 200 if a
        body is present otherwise 204"""
        if self.has_body():
            code = 200
        else:
            code = 204

        return code

    @code.setter
    def code(self, v):
        self._code = v
        try:
            del(self.status)

        except AttributeError:
            pass

    @cachedproperty(cached="_code")
    def status_code(self):
        return self.code

    @cachedproperty(cached="_status", onget=False)
    def status(self):
        """The full http status (the first line of the headers in a server
        response)"""
        return Status(self.code)

    @cachedproperty(setter="_body")
    def body(self, v):
        self._body = v
        if self.is_file():
            filepath = getattr(v, "name", "")
            if filepath:
                mt = MimeType.find_type(filepath)
                filesize = os.path.getsize(filepath)
                self.set_header("Content-Type", mt)
                self.set_header("Content-Length", filesize)
                logger.debug(" ".join([
                    f"Response body set to file: \"{filepath}\"",
                    f"with mimetype: \"{mt}\"",
                    f"and size: {filesize}",
                ]))

            else:
                logger.warn(
                    "Response body is a filestream that has no .filepath property"
                )

    def has_body(self):
        """return True if there is an actual response body"""
        return getattr(self, "_body", None) is not None

    def is_file(self):
        """return True if the response body is a file pointer"""
        # http://stackoverflow.com/questions/1661262/check-if-object-is-file-like-in-python
        return isinstance(getattr(self, "_body", None), io.IOBase)
        #return hasattr(self._body, "read") if self.has_body() else False

    def is_success(self):
        """return True if this response is considered a "successful" response"""
        code = self.code
        return code < 400

    def is_successful(self):
        return self.is_success()

