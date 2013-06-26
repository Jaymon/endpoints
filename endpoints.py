# stdlib modules
import urlparse
import importlib

# 3rd party modules

# first party modules

def unicodify(s):
    '''
    make sure a string is a unicode string

    s -- string|unicode

    return -- unicode
    '''
    if not isinstance(s, unicode):
        s = s.decode('utf-8')

    # TODO: support lists and dicts of strings?

    return s

class CallError(RuntimeError):
    def __init__(self, code, msg):
        self.code = code
        super(CallError, self).__init__(msg)

class Controller(object):
    request = None
    response = None

    def get(self, *args, **kwargs):
        raise CallError(405, "GET not supported")

    def post(self, *args, **kwargs):
        raise CallError(405, "POST not supported")

    def put(self, *args, **kwargs):
        raise CallError(405, "PUT not supported")

    def head(self, *args, **kwargs):
        raise CallError(405, "HEAD not supported")

class Request(object):
    '''
    common interface that endpoints uses to decide what to do with the incoming request

    an instance of this class is passed to other endpoints methods to decide where endpoints
    should route requests, so many times, you need to write a glue function that takes however
    your request data is passed to Python and convert it into a Request instance so endpoints can
    deal with it
    '''

    # path part of a url (eg, http://host.com/path?query=string)
    path = u"" # /foo/bar
    path_args = [] # the path converted to list (eg /foo/bar becomes [foo, bar]

    # query_string part of a url (eg, http://host.com/path?query=string)
    query = u"" # foo=bar&baz=che
    query_kwargs = {} # {foo: bar, baz: che}

    # the http method (GET, POST)
    method = None

    # the module prefix that will be used to append to the controller to decide where to route the request
    prefix = ""

    @property
    def controller(self):
        return None

    @property
    def controller_args(self):
        return self.path_args

    @property
    def controller_kwargs(self):
        return self.query_kwargs

class Mongrel2Request(Request):

    def __init__(self, req):
        h = req.headers
        self.path = h[u'PATH']
        self.query = h[u'QUERY']
        self.method = h[u'METHOD']

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, v):
        self._path = unicodify(v)
        self.path_args = filter(None, v.split(u'/'))

    @property
    def query(self):
        return self._query

    @query.setter
    def query(self, v):
        self._query = unicodify(v)
        self.query_kwargs = {}
        # we only want true array query args to be arrays
        for k, kv in urlparse.parse_qs(v, True).iteritems():
            if len(kv) > 1:
                self.query_kwargs[k] = kv
            else:
                self.query_kwargs[k] = kv[0]


class Response(object):
    body = None

    # TODO: make body return appropriate stuff, so if body is a dict, and out header is json, then
    # resp.body should return json formatted body

class Call(object):

    controller_prefix = u""

    @property
    def request(self):
        if not self._request:
            self._request = Request()

        return self._request

    @request.setter
    def request(self, v):
        self._request = v

    @property
    def response(self):
        if not self._response:
            self._response = Response()

        return self._response

    @response.setter
    def response(self, v):
        self._response = v

    def __init__(self, controller_prefix=u"", *args, **kwargs):
        self.controller_prefix = controller_prefix
        self.args = args
        self.kwargs = kwargs

    @property
    def controller_info(self):
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

        controller_prefix = self.controller_prefix
        if controller_prefix:
            d['module'] = u".".join([controller_prefix, request_module])

        # the second arg is the Class
        if len(path_args) > 0:
            class_name = path_args.pop(0)
            d['class_name'] = class_name.title()

        d['args'] = path_args
        d['kwargs'] = req.query_kwargs

        return d

    @property
    def callback_info(self):
        d = self.controller_info

        # import module
        try:
            module = importlib.import_module(d['module'])

            module_class = getattr(module, d['class_name'])

            module_instance = module_class()
            module_instance.request = self.request
            module_instance.response = self.response

            callback = getattr(module_instance, d['method'])

        except (ImportError, AttributeError):
            r = self.request
            raise CallError(404, "{} not found".format(r.path))

        return callback, d['args'], d['kwargs']

    def handle(self):
        '''
        handle the request, return the headers and json that should be sent back to the client

        req -- Request() -- a Request instance to be used to translate the request to a controller
        resp -- Response() -- a Response instance to be returned from handle populated with info from controller

        #return -- tuple -- (headers, json)
        return -- Response() -- the response object, populated with info from running the controller
        '''

    #    /foo -> prefix.version.foo.Default.method
    #    /foo/bar -> prefix.version.foo.Bar.method
    #    /foo/bar/che -> prefix.version.foo.Bar.method(che)
    #    /foo/bar/che?baz=foo -> prefix.version.foo.Bar.method(che, baz=foo)
    #
    #    basically, we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs=v

        callback, callback_args, callback_kwargs = self.callback_info
        try:
            body = callback(*callback_args, **callback_kwargs)
            self.response.body = body

        except Exception, e:
            self.response.code = 500
            self.body = e.message

        return self.response























