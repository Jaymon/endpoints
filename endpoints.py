# stdlib modules
import urlparse
import urllib
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
    """

    request = None
    """holds a Request() instance"""
    
    response = None
    """holds a Response() instance"""

    def get(self, *args, **kwargs):
        '''handle GET requests for this Controller endpoint'''
        raise CallError(405, "GET not supported")

    def post(self, *args, **kwargs):
        '''handle POST requests for this Controller endpoint'''
        raise CallError(405, "POST not supported")

class Request(object):
    '''
    common interface that endpoints uses to decide what to do with the incoming request

    an instance of this class is used by the endpoints Call instance to decide where endpoints
    should route requests, so many times, you need to write a glue function that takes however
    your request data is passed to Python and convert it into a Request instance that endpoints can
    understand
    '''
    headers = {}
    """all the http request headers in header: val format"""

    #path = u"" # /foo/bar

    #path_args = []
    """the path converted to list (eg /foo/bar becomes [foo, bar])"""

    #query = u"" # foo=bar&baz=che
    """query_string part of a url (eg, http://host.com/path?query=string)"""

    #query_kwargs = {}
    """{foo: bar, baz: che}"""

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

#class Mongrel2Request(Request):
#
#    def __init__(self, req):
#        h = req.headers
#        self.path = h[u'PATH']
#        self.query = h[u'QUERY']
#        self.method = h[u'METHOD']
#
#    @property
#    def path(self):
#        return self._path
#
#    @path.setter
#    def path(self, v):
#        self._path = unicodify(v)
#        self.path_args = filter(None, v.split(u'/'))
#
#    @property
#    def query(self):
#        return self._query
#
#    @query.setter
#    def query(self, v):
#        self._query = unicodify(v)
#        self.query_kwargs = {}
#        # we only want true array query args to be arrays
#        for k, kv in urlparse.parse_qs(v, True).iteritems():
#            if len(kv) > 1:
#                self.query_kwargs[k] = kv
#            else:
#                self.query_kwargs[k] = kv[0]
#

class Response(object):
    """
    an instance of this class is used to create the text response that will be sent 
    back to the client
    """

    code = 200
    """the http status code to return to the client"""
    
    body = None
    """the body to return to the client"""

    # TODO: make body return appropriate stuff, so if body is a dict, and out header is json, then
    # resp.body should return json formatted body

class Call(object):
    """
    Where all the routing magic happens

    /foo -> prefix.version.foo.Default.method
    /foo/bar -> prefix.version.foo.Bar.method
    /foo/bar/che -> prefix.version.foo.Bar.method(che)
    /foo/bar/che?baz=foo -> prefix.version.foo.Bar.method(che, baz=foo)

    basically, we always translate an HTTP request using this pattern: METHOD /module/class/args?kwargs=v
    """

    controller_prefix = u""
    """since endpoints interprets requests as /module/class, you can use this to do: controller_prefix.module.class"""

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

        except (ImportError, AttributeError), e:
            r = self.request
            raise CallError(404, "{} not found because {}".format(r.path, e.message))

        try:
            module_instance = module_class()
            module_instance.request = self.request
            module_instance.response = self.response

            callback = getattr(module_instance, d['method'])

        except AttributeError, e:
            r = self.request
            raise CallError(405, "{} {} not supported".format(r.method, r.path))

        return callback, d['args'], d['kwargs']

    def handle(self):
        '''
        handle the request, return the headers and json that should be sent back to the client

        return -- Response() -- the response object, populated with info from running the controller
        '''
        callback, callback_args, callback_kwargs = self.get_callback_info()
        try:
            body = callback(*callback_args, **callback_kwargs)
            self.response.body = body

        except CallError:
            raise

        except Exception, e:
            self.response.code = 500
            self.body = e.message

        return self.response

