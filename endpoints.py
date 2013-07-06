# stdlib modules
import urlparse
import urllib
import importlib
import json
import sys
import os
import inspect
import types

__version__ = '0.5'

class CallError(RuntimeError):
    """
    http errors can raise this with an HTTP status code and message
    """
    def __init__(self, code, msg):
        '''
        create the error

        code -- integer -- http status code
        msg -- string -- the message you want to accompany your status code
        '''
        self.code = code
        super(CallError, self).__init__(msg)

class Controller(object):
    """
    this is the interface for a Controller sub class

    I would suggest all your controllers extend this base class :)

    to activate a new endpoint, just add a module on your PYTHONPATH that has a class
    that extends this class, and then defines at least a get method, so if you wanted to create
    the endpoint /foo/bar, you would just need to:

    ---------------------------------------------------------------------------
    # foo.py
    import endpoints

    class Bar(endpoints.Controller):
        endpoint_public = True
        def get(self, *args, **kwargs):
            return "you just made a GET request"
    ---------------------------------------------------------------------------

    as you support more methods, like POST and PUT, you can just add post(self) and put(self)
    methods to your Bar class and Bar will support those methods. Although you can
    request any method, here is a list of rfc approved http request methods:

    http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods
    """

    request = None
    """holds a Request() instance"""

    response = None
    """holds a Response() instance"""

    call = None
    """holds the call() instance that invoked this Controller"""

    endpoint_public = False
    """set this to True if the controller should be made publicly available, this is
    handy for when you want to make base controllers that can't be accessed, like endpoints.Controller"""

    endpoint_options = None
    """the list of supported http method options the controller has"""

class Request(object):
    '''
    common interface that endpoints uses to decide what to do with the incoming request

    an instance of this class is used by the endpoints Call instance to decide where endpoints
    should route requests, so, many times, you'll need to write a glue function that takes however
    your request data is passed to Python and convert it into a Request instance that endpoints can
    understand
    '''

    @property
    def headers(self):
        """all the http request headers in header: val format"""
        if not getattr(self, '_headers', None): self._headers = {}
        return self._headers
    
    @headers.setter
    def headers(self, v):
        self._headers = v

    method = None
    """the http method (GET, POST)"""

    @property
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        if not hasattr(self, '_path'):
            path_args = self.path_args
            self._path = u"/{}".format(u"/".join(path_args))

        return self._path

    @path.setter
    def path(self, v):
        self._path = v

    @property
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        if not hasattr(self, '_path_args'):
            path = self.path
            self._path_args = filter(None, path.split(u'/'))

        return self._path_args

    @path_args.setter
    def path_args(self, v):
        self._path_args = v

    @property
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)"""
        if not hasattr(self, '_query'):
            self._query = u""
            query_kwargs = self.query_kwargs
            if query_kwargs:
                self._query = urllib.urlencode(query_kwargs, doseq=True)

        return self._query

    @query.setter
    def query(self, v):
        self._query = v

    @property
    def query_kwargs(self):
        """{foo: bar, baz: che}"""
        if not hasattr(self, '_query_kwargs'):
            self._query_kwargs = {}
            query = self.query
            if query:
                # we only want true array query args to be arrays
                for k, kv in urlparse.parse_qs(query, True).iteritems():
                    if len(kv) > 1:
                        self._query_kwargs[k] = kv
                    else:
                        self._query_kwargs[k] = kv[0]

        return self._query_kwargs

    @query_kwargs.setter
    def query_kwargs(self, v):
        self._query_kwargs = v

class Response(object):
    """
    an instance of this class is used to create the text response that will be sent 
    back to the client
    """

    code = 200
    """the http status code to return to the client"""

    statuses = {
        100: 'Continue',
        101: 'Switching Protocols',
        102: 'Processing', # RFC2518
        200: 'OK',
        201: 'Created',
        202: 'Accepted',
        203: 'Non-Authoritative Information',
        204: 'No Content',
        205: 'Reset Content',
        206: 'Partial Content',
        207: 'Multi-Status', # RFC4918
        208: 'Already Reported', # RFC5842
        226: 'IM Used', # RFC3229
        300: 'Multiple Choices',
        301: 'Moved Permanently',
        302: 'Found',
        303: 'See Other',
        304: 'Not Modified',
        305: 'Use Proxy',
        306: 'Reserved',
        307: 'Temporary Redirect',
        308: 'Permanent Redirect', # RFC-reschke-http-status-308-07
        400: 'Bad Request',
        401: 'Unauthorized',
        402: 'Payment Required',
        403: 'Forbidden',
        404: 'Not Found',
        405: 'Method Not Allowed',
        406: 'Not Acceptable',
        407: 'Proxy Authentication Required',
        408: 'Request Timeout',
        409: 'Conflict',
        410: 'Gone',
        411: 'Length Required',
        412: 'Precondition Failed',
        413: 'Request Entity Too Large',
        414: 'Request-URI Too Long',
        415: 'Unsupported Media Type',
        416: 'Requested Range Not Satisfiable',
        417: 'Expectation Failed',
        418: 'I\'m a teapot', # RFC2324
        422: 'Unprocessable Entity', # RFC4918
        423: 'Locked', # RFC4918
        424: 'Failed Dependency', # RFC4918
        425: 'Reserved for WebDAV advanced collections expired proposal', # RFC2817
        426: 'Upgrade Required', # RFC2817
        428: 'Precondition Required', # RFC6585
        429: 'Too Many Requests', # RFC6585
        431: 'Request Header Fields Too Large', # RFC6585
        500: 'Internal Server Error',
        501: 'Not Implemented',
        502: 'Bad Gateway',
        503: 'Service Unavailable',
        504: 'Gateway Timeout',
        505: 'HTTP Version Not Supported',
        506: 'Variant Also Negotiates (Experimental)', # RFC2295
        507: 'Insufficient Storage', # RFC4918
        508: 'Loop Detected', # RFC5842
        510: 'Not Extended', # RFC2774
        511: 'Network Authentication Required', # RFC6585
    }
    """default status code messages

    shamefully ripped from Symfony HttpFoundation Response (shoulders of giants)
    https://github.com/symfony/HttpFoundation/blob/master/Response.php
    """

    @property
    def headers(self):
        """response headers in header: value format"""
        if not getattr(self, '_headers', None): self._headers = {}
        return self._headers
    
    @headers.setter
    def headers(self, v):
        self._headers = v

    @property
    def status(self):
        if not getattr(self, '_status', None):
            c = self.code
            msg = self.statuses.get(self.code, "UNKNOWN")
            self._status = msg

        return self._status
    
    @status.setter
    def status(self, v):
        self._status = v

    @property
    def body(self):
        """return the body, formatted to the appropriate content type"""
        if not hasattr(self, '_body'): return None

        b = self._body
        ct = self.headers.get('Content-Type', None)
        if ct:
            ct = ct.lower()
            if ct.rfind(u"json") >= 0: # fuzzy, not sure I like that
                b = json.dumps(b)

        return b
    
    @body.setter
    def body(self, v):
        self._body = v

class Call(object):
    """
    Where all the routing magic happens

    we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs

    GET /foo -> controller_prefix.version.foo.Default.get
    POST /foo/bar -> controller_prefix.version.foo.Bar.post
    GET /foo/bar/che -> controller_prefix.version.foo.Bar.get(che)
    POST /foo/bar/che?baz=foo -> controller_prefix.version.foo.Bar.post(che, baz=foo)
    """

    controller_prefix = u""
    """since endpoints interprets requests as /module/class, you can use this to do: controller_prefix.module.class"""

    content_type = "application/json"
    """the content type this call is going to represent"""

    @property
    def request(self):
        '''
        Call.request, this request object is used to decide how to route the client request

        a Request instance to be used to translate the request to a controller
        '''
        if not hasattr(self, "_request"):
            self._request = Request()

        return self._request

    @request.setter
    def request(self, v):
        self._request = v

    @property
    def response(self):
        '''
        Call.response, this object is used to decide how to answer the client

        a Response instance to be returned from handle populated with info from controller
        '''
        if not hasattr(self, "_response"):
            self._response = Response()

        return self._response

    @response.setter
    def response(self, v):
        self._response = v

    def __init__(self, controller_prefix=u"", *args, **kwargs):
        '''
        create the instance

        controller_prefix -- string -- the module path where all your controller modules live
        *args -- tuple -- convenience, in case you extend and need something in another method
        **kwargs -- dict -- convenience, in case you extend
        '''
        self.controller_prefix = controller_prefix
        self.args = args
        self.kwargs = kwargs

    def get_controller_info(self):
        '''
        get info about finding a controller based off of the request info

        return -- dict -- all the gathered info about the controller
        '''
        d = {}
        req = self.request
        path_args = list(req.path_args)
        d['module'] = u"default"
        d['class_name'] = u"Default"
        d['method'] = req.method.lower()
        d['args'] = []
        d['kwargs'] = {}

        # the first arg is the module
        if len(path_args) > 0:
            d['module'] = path_args.pop(0)

        controller_prefix = self.get_normalized_prefix()
        if controller_prefix:
            d['module'] = u".".join([controller_prefix, d['module']])

        # the second arg is the Class
        if len(path_args) > 0:
            class_name = path_args.pop(0)
            d['class_name'] = class_name.title()

        d['args'] = path_args
        d['kwargs'] = req.query_kwargs

        return d

    def get_callback_info(self):
        '''
        get the controller callback that will be used to complete the call

        return -- tuple -- (callback, callback_args, callback_kwargs), basically, everything you need to
            call the controller: callback(*callback_args, **callback_kwargs)
        '''
        d = self.get_controller_info()

        try:
            module = importlib.import_module(d['module'])
            module_class = getattr(module, d['class_name'])

            if not getattr(module_class, 'endpoint_public'):
                r = self.request
                raise ImportError('{} is not public'.format(r.path))

        except (ImportError, AttributeError), e:
            r = self.request
            raise CallError(404, "{} not found because of error: {}".format(r.path, e.message))

        try:
            module_instance = module_class()
            module_instance.request = self.request
            module_instance.response = self.response
            module_instance.call = self

            callback = getattr(module_instance, d['method'])

        except AttributeError, e:
            r = self.request
            raise CallError(405, "{} {} not supported".format(r.method, r.path))

        return callback, d['args'], d['kwargs']

    def get_normalized_prefix(self):
        """
        do any normalization of the controller prefix and return it

        return -- string -- the full controller module prefix
        """
        return self.controller_prefix

    def handle(self):
        '''
        handle the request

        return -- Response() -- the response object, populated with info from running the controller
        '''
        try:
            callback, callback_args, callback_kwargs = self.get_callback_info()
            self.response.headers['Content-Type'] = self.content_type
            body = callback(*callback_args, **callback_kwargs)
            self.response.body = body

        except CallError, e:
            self.response.code = e.code
            self.response.body = e.message

        except Exception, e:
            self.response.code = 500
            self.response.body = e.message

        return self.response

class VersionCall(Call):
    """
    versioning is based off of this post: http://urthen.github.io/2013/05/09/ways-to-version-your-api/
    """

    default_version = None
    """set this to the default version if you want a fallback version, if this is None then version check is enforced"""

    def get_normalized_prefix(self):
        cp = u""
        if hasattr(self, "controller_prefix"):
            cp = self.controller_prefix
        v = self.get_version()
        if cp:
            cp += u".{}".format(v)
        else:
            cp = v

        return cp

    def get_version(self):
        if not self.content_type:
            raise ValueError("You are versioning a call with no content_type")

        v = None
        h = self.request.headers
        accept_header = h.get('accept', u"")
        if not accept_header:
            raise CallError(406, "Expected accept header with {} media type".format(self.content_type))

        a = AcceptHeader(accept_header)
        for mt in a.filter(self.content_type):
            v = mt[2].get(u"version", None)
            if v: break

        if not v:
            v = self.default_version
            if not v:
                raise CallError(406, "Expected accept header with {};version=vN media type".format(self.content_type))

        return v

class AcceptHeader(object):
    """
    wraps the Accept header to allow easier versioning

    provides methods to return the accept media types in the correct order
    """
    def __init__(self, header):
        self.header = header
        self.media_types = []

        if header:
            accepts = header.split(u',')
            for accept in accepts:
                accept = accept.strip()
                a = accept.split(u';')

                # first item is the media type:
                media_type = self._split_media_type(a[0])

                # all other items should be in key=val so let's add them to a dict:
                params = {}
                q = 1.0 # default according to spec
                for p in a[1:]:
                    pk, pv = p.strip().split(u'=')
                    if pk == u'q':
                        q = float(pv)
                    else:
                        params[pk] = pv

                #pout.v(media_type, q, params)
                self.media_types.append((media_type, q, params, accept))

    def _split_media_type(self, media_type):
        """return type, subtype from media type: type/subtype"""
        media_type_bits = media_type.split(u'/')
        return media_type_bits

    def _sort(self, a, b):
        '''
        sort the headers according to rfc 2616 so when __iter__ is called, the accept media types are
        in order from most preferred to least preferred
        '''
        ret = 0

        # first we check q, higher values win:
        if a[1] != b[1]:
            ret = cmp(a[1], b[1])
        else:
            found = False
            for i in xrange(2):
                ai = a[0][i]
                bi = b[0][i]
                if ai == u'*':
                    if bi != u'*':
                        ret = -1
                        found = True
                        break
                    else:
                        # both *, more verbose params win
                        ret = cmp(len(a[2]), len(b[2]))
                        found = True
                        break
                elif bi == u'*':
                    ret = 1
                    found = True
                    break

            if not found:
                ret = cmp(len(a[2]), len(b[2]))

        return ret

    def __iter__(self):
        sorted_media_types = sorted(self.media_types, self._sort, reverse=True)
        for x in sorted_media_types:
            yield x

    def filter(self, media_type, **params):
        """
        iterate all the accept media types that match media_type

        media_type -- string -- the media type to filter by
        **params -- dict -- further filter by key: val

        return -- generator -- yields all matching media type info things
        """
        mtype, msubtype = self._split_media_type(media_type)
        for x in self.__iter__():

            # all the params have to match to make the media type valid
            matched = True
            for k, v in params.iteritems():
                if x[2].get(k, None) != v:
                    matched = False
                    break

            if matched:
                if mtype == u'*':
                    if msubtype == u'*':
                        yield x
                    else:
                        if x[0][1] == msubtype:
                            yield x
                elif x[0][0] == mtype:
                    if msubtype == u'*':
                        yield x
                    elif x[0][1] == msubtype:
                        yield x

class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    def __init__(self, controller_prefix, content_type=None):
        self.controller_prefix = controller_prefix
        self.content_type = content_type

    def normalize_endpoint(self, endpoint, *args, **kwargs):
        """
        handy for adding any args, or kwargs accumulated through all the calls to the endpoint

        endpoint -- dict -- the endpoint information dict
        """
        return endpoint

    def normalize_controller_module(self, controller_prefix, fname, *args, **kwargs):
        """
        normalize controller bits to a python module

        example -- controller_prefix="foo", fname="bar" --> return "foo.bar"

        return -- string -- the full.python.module that can be imported
        """
        return u".".join([controller_prefix, fname])

    def walk_files(self, controller_path):
        """
        walk all the controllers that are submodules of controller_path

        controller_path -- string -- the path to where the controllers are

        return -- generator -- (file, args, kwargs) it yields each file and any extra info
        """
        for root, dirs, files in os.walk(controller_path, topdown=True):
            for f in files:
                yield f, [], {}
            break

    def get_controller_modules(self):
        """
        get all the controller modules

        this will find any valid controller modules and yield all the endpoints in them

        return -- generator -- endpoint info found in each controller module file
        """
        controller_path = self.find_controller_path()
        controller_prefix = self.controller_prefix
        for f, args, kwargs in self.walk_files(controller_path):
                fname, fext = os.path.splitext(f)
                if fext.lower() != u".py": continue
                if fname == u"__init__": continue

                controller_module = self.normalize_controller_module(controller_prefix, fname, *args, **kwargs)

                for endpoint, args, kwargs in self.get_endpoints_in_controller(controller_module, *args, **kwargs):
                    yield endpoint, args, kwargs

    def get_endpoints(self):
        """
        go through all the controllers in controller prefix and return them

        return -- list -- a list of endpoints found
        """
        pre_module_names = set(sys.modules.keys())

        l = []

        for endpoint, args, kwargs in self.get_controller_modules():
            l.append(self.normalize_endpoint(endpoint, *args, **kwargs))

        new_module_names = set(sys.modules.keys()) - pre_module_names

        # remove any new modules that were added when this was run
        for n in new_module_names: sys.modules.pop(n, None)

        return l

    def find_controller_path(self):
        """
        find the base controller path using this class's set controller_prefix

        return -- string -- the controller base directory
        """
        controller_prefix = self.controller_prefix
        if not controller_prefix:
            raise ValueError("reflect only works when you use a controller_prefix")

        controller_path = u""
        controller_dirs = controller_prefix.split(u".")
        for p in sys.path:
            fullp = os.path.join(p, *controller_dirs)
            if os.path.isdir(fullp):
                controller_path = fullp
                break

        if not controller_path:
            raise IOError("could not find a valid path for controllers in module: {}".format(controller_prefix))

        return controller_path

    def get_endpoints_in_controller(self, controller, *args, **kwargs):
        """
        get all the endpoints in this controller

        return -- list -- a list of dicts with information about each endpoint in the controller
        """
        module = importlib.import_module(controller)
        classes = inspect.getmembers(module, inspect.isclass)
        options = set(['get', 'head', 'post', 'put', 'delete', 'trace', 'options', 'connect', 'patch'])
        for k, v in classes:
            k = k.lower()
            public = getattr(v, 'endpoint_public', False)
            if public:
                v_options = getattr(v, 'endpoint_options', [])
                if not v_options:
                    v_options = []
                    for option in options:
                        if hasattr(v, option):
                            v_options.append(option.upper())

                doc = inspect.getdoc(v)
                name = controller.rpartition(".")[2].lower()
                endpoint = [u""]
                for n in [name, k]:
                    if n != 'default': endpoint.append(n)
                if len(endpoint) == 1:
                    endpoint = u"/"
                else:
                    endpoint = u"/".join(endpoint)

                d = {
                    'endpoint': endpoint,
                    'options': v_options,
                    'doc': doc if doc else u""
                }
                yield d, args, kwargs

class VersionReflect(Reflect):
    """
    same as Reflect, but for VersionCall
    """
    def normalize_controller_module(self, controller_prefix, fname, version, *args, **kwargs):
        return u".".join([controller_prefix, version, fname])

    def normalize_endpoint(self, endpoint, version, *args, **kwargs):
        endpoint['headers'] = {}
        endpoint['headers']['Accept'] = "{};version={}".format(self.content_type, version)
        return endpoint

    def walk_files(self, controller_path):
        for root, versions, _ in os.walk(controller_path, topdown=True):
            for version in versions:
                for root,  _, files in os.walk(os.path.join(controller_path, version), topdown=True):
                    for f in files:
                        yield f, [], {'version': version}


