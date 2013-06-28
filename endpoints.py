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

        except CallError, e:
            self.response.code = e.code
            self.response.body = e.message

        except Exception, e:
            self.response.code = 500
            self.body = e.message

        return self.response

class VersionCall(Call):
    """
    versioning is based off of this post: http://urthen.github.io/2013/05/09/ways-to-version-your-api/
    """

    default_version = None
    """set this to the default version if you want a fallback version, if this is None then version check is enforced"""

    version_media_type = u""
    """the media type that should be versioned, usually something like application/json"""

    @property
    def controller_prefix(self):
        cp = u""
        if hasattr(self, "_controller_prefix"):
            cp = self._controller_prefix
        v = self.get_version()
        if cp:
            cp += u".{}".format(v)
        else:
            cp = v

        return cp

    @controller_prefix.setter
    def controller_prefix(self, v):
        self._controller_prefix = v

    def get_version(self):
        if not self.version_media_type:
            raise ValueError("You are versioning a call with no version_media_type")

        v = None
        h = self.request.headers
        accept_header = h.get('accept', u"")
        if not accept_header:
            raise CallError(406, "Expected accept header with {} media type".format(self.version_media_type))

        a = AcceptHeader(accept_header)
        for mt in a.filter(self.version_media_type):
            v = mt[2].get(u"version", None)
            if v: break

        if not v:
            v = self.default_version
            if not v:
                raise CallError(406, "Expected accept header with {};version=N media type".format(self.version_media_type))

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














