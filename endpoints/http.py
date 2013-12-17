import urlparse
import urllib
import json


class Request(object):
    '''
    common interface that endpoints uses to decide what to do with the incoming request

    an instance of this class is used by the endpoints Call instance to decide where endpoints
    should route requests, so, many times, you'll need to write a glue function that takes however
    your request data is passed to Python and convert it into a Request instance that endpoints can
    understand

    properties --

    headers -- a dict of all the request headers in { header_name: header_val } format
    path -- the /path/part/of/the/url
    path_args -- tied to path, it's path, but divided by / so all the path bits are returned as a list
    query -- the ?name=val portion of a url
    query_kwargs -- tied to query, the values in query but converted to a dict {name: val}
    '''

    headers = None
    """all the http request headers in header: val format"""

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
            if query: self._query_kwargs = self._parse_query_str(query)

        return self._query_kwargs

    @query_kwargs.setter
    def query_kwargs(self, v):
        self._query_kwargs = v

    @property
    def body(self):
        """
        the request body, if this is a POST request

        this tries to do the right thing with the body, so if you have set the body and
        the content type is json, then it will return the body json decoded, if you need
        the original string body, use _body

        example --

            self.body = '{"foo":{"name":"bar"}}'
            b = self.body # dict with: {"foo": { "name": "bar"}}
            print self._body # string with: u'{"foo":{"name":"bar"}}'
        """
        if not hasattr(self, '_body'):
            self._body = None

        b = self._body
        if b is not None:
            # we are returning the body, let's try and be smart about it and match content type
            ct = self.get_header('content-type')
            if ct:
                ct = ct.lower()
                if ct.rfind(u"json") >= 0:
                    if b:
                        b = json.loads(b)
                    else:
                        b = None

                elif ct.rfind(u"x-www-form-urlencoded") >= 0:
                    b = self._parse_query_str(b)

        return b

    @body.setter
    def body(self, v):
        self._body = v

    def __init__(self):
        self.headers = {}

    def get_header(self, header_name, default_val=None):
        """try as hard as possible to get a a response header of header_name, return default_val if it can't be found"""
        ret = default_val
        headers = self.headers
        if header_name in headers:
            ret = headers[header_name]
        elif header_name.lower() in headers:
            ret = headers[header_name.lower()]
        elif header_name.title() in headers:
            ret = headers[header_name.title()]
        elif header_name.upper() in headers:
            ret = headers[header_name.upper()]
        elif header_name.capitalize() in headers:
            ret = headers[header_name.capitalize()]

        return ret

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        d = {}
        for k, kv in urlparse.parse_qs(query, True).iteritems():
            if len(kv) > 1:
                d[k] = kv
            else:
                d[k] = kv[0]

        return d


class Response(object):
    """
    an instance of this class is used to create the text response that will be sent 
    back to the client
    """
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

    headers = None
    """the http return headers in { header_name: header_val } format"""

    @property
    def code(self):
        """the http status code to return to the client, by default, 200 if a body is present otherwise 204"""
        code = getattr(self, '_code', None)
        if not code:
            body = getattr(self, '_body', None)
            if body:
                code = 200
            else:
                code = 204

        return code

    @code.setter
    def code(self, v):
        self._code = v

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
        is_error = isinstance(b, Exception)
        ct = self.headers.get('Content-Type', None)
        if ct:
            ct = ct.lower()
            if ct.rfind(u"json") >= 0: # fuzzy, not sure I like that
                if is_error:
                    b = json.dumps({
                        "errmsg": str(b),
                        "errno": self.code
                    })

                else:
                    # I don't like this, if we have a content type but it isn't one
                    # of the supported ones we were returning the exception, which threw
                    # Jarid off, but now it just returns a string, which is not best either
                    # my thought is we could have a body_type_subtype method that would 
                    # make it possible to easily handle custom types
                    # eg, "application/json" would become: self.body_application_json(b, is_error)
                    b = json.dumps(b)

            else:
                if is_error:
                    b = str(b)

        else:
            if is_error:
                b = str(b)

        return b

    @body.setter
    def body(self, v):
        self._body = v

    def __init__(self):
        self.headers = {}

    def set_cors_headers(self, request_headers, custom_response_headers=None):

        allow_headers = request_headers['Access-Control-Request-Headers']
        allow_method = request_headers['Access-Control-Request-Method']
        origin = request_headers['origin']

        cors_headers = {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Methods': allow_method,
            'Access-Control-Allow-Headers': allow_headers,
            'Access-Control-Max-Age': 3600
        }

        if custom_response_headers:
            cors_headers.update(custom_response_headers)

        self.headers.update(cors_headers)


