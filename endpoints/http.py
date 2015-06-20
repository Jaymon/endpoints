import urlparse
import urllib
import json
import types
import cgi
import re
import base64
from BaseHTTPServer import BaseHTTPRequestHandler

from .decorators import _property
from .utils import AcceptHeader


class Headers(dict):
    """Handles normalizing of header names, the problem with headers is they can
    be in many different forms and cases and stuff (eg, CONTENT_TYPE and Content-Type),
    so this handles normalizing the header names so you can request Content-Type
    or CONTENT_TYPE and get the same value"""

    def genkeys(self, k):
        """here is where all the magic happens, this will generate all the different
        variations of the header name looking for one that is set"""
        yield k

        kupper = k.upper()
        yield kupper.replace('-', '_')
        yield kupper.replace('_', '-')

        klower = k.lower()
        klower_norm = klower.replace('-', '_')
        yield klower_norm

        yield klower.replace('_', '-')

        bits = klower_norm.split('_')
        yield "-".join((bit.title() for bit in bits))

        yield "{}-{}".format(bits[0].title(), "-".join(bits[1:]))
        yield "{}_{}".format(bits[0].title(), "_".join(bits[1:]))

    def __getitem__(self, k):

        v = None
        for nk in self.genkeys(k):
            try:
                v = super(Headers, self).__getitem__(nk)
            except KeyError as e:
                pass
            else:
                break

        # raise a key error if we couldn't find the header
        if v is None:
            v = super(Headers, self).__getitem__(k)

        return v

    def __setitem__(self, k, v):
        knorm = k.upper().replace('-', '_')
        super(Headers, self).__setitem__(knorm, v)

    def __contains__(self, k):
        ret = False
        for nk in self.genkeys(k):
            ret = super(Headers, self).__contains__(nk)
            if ret: break

        return ret

    def get(self, k, dv=None):
        try:
            v = self[k]
        except KeyError:
            v = dv

        return v

    def update(self, d):
        for k, v in d.items():
            self[k] = v


class Body(object):
    """this is the normalized request environment that every interface needs to
    conform to, it primarily acts like a wsgi environment, which is compatible with
    python's internal cgi.FieldStorage stuff"""

    # https://hg.python.org/cpython/file/2.7/Lib/cgi.py#l325

    def __init__(self, fp, headers, environ):
        self.headers = headers
        self.environ = environ
        self.fp = fp

        # make sure environ has the bare minimum to work
        for k in ["REQUEST_METHOD", "QUERY_STRING"]:
            if k not in self.environ:
                raise ValueError("environ dict does not contain {}".format(k))

    def __iter__(self):
        body_fields = cgi.FieldStorage(
            fp=self.fp,
            headers=self.headers,
            environ=self.environ,
            keep_blank_values=True
        )

        for field_name in body_fields.keys():
            body_field = body_fields[field_name]
            if body_field.filename:
                yield field_name, body_field

            else:
                yield field_name, body_field.value


class Url(object):
    """a url object on steriods, this is here to make it easy to manipulate urls"""

    @property
    def base(self):
        """the full url without the query or fragment, returns new Url() instance"""
        return self._create(urlparse.urlunsplit((
            self.scheme,
            self.netloc,
            self.path,
            "",
            ""
        )))

    @property
    def hostloc(self):
        """return just the host:port, basically netloc without username and pass info"""
        hostloc = self.hostname
        if self.port:
            hostloc = '{}:{}'.format(hostloc, self.port)
        return hostloc

    @property
    def host(self):
        """just another way to get just the host, I like this better than hostname"""
        return self.hostname

    @property
    def anchor(self):
        """alternative name for fragment"""
        return self.fragment

    @property
    def uri(self):
        """return the uri, which is everything but base (no scheme, host, etc)"""
        uristring = self.path
        if self.query:
            uristring += "?{}".format(self.query)
        if self.fragment:
            uristring += "#{}".format(self.fragment)

        return uristring

    @property
    def query_kwargs(self):
        """return the query arguments as a dictionary"""
        return self._parse_query(self.query) if self.query else {}

    def __init__(self, urlstring=None, **kwargs):
        self._update_url(urlstring)
        for k, v in kwargs.items():
            setattr(self, k, v)

        if not self.netloc:
            self.netloc = self.hostloc

    def modify(self, *paths, **query_kwargs):
        """return a new Url instance with paths and query_kwargs changed, basically
        this will update the current information with the passed in information and
        return a whole new instance"""
        urlstring = self.base.geturl()
        if paths:
            path = "/".join(paths)
            urlstring = urlparse.urljoin(urlstring, path)

        url_query_kwargs = self.query_kwargs
        url_query_kwargs.update(query_kwargs)
        query = self._unparse_query(url_query_kwargs)
        return self._create(urlstring, query=query, fragment=self.fragment)

    def update(self, *paths, **query_kwargs):
        """similar to modify, but updates this instance internally"""
        o = self.modify(*paths, **query_kwargs)
        self._update_url(o.geturl())

    def geturl(self):
        """return the dsn back into url form"""
        return urlparse.urlunsplit((
            self.scheme,
            self.netloc,
            self.path,
            self.query,
            self.fragment,
        ))

    def __str__(self):
        return self.geturl()

    def _update_url(self, urlstring):
        """update the internal information with that of urlstring"""
        urlparse_attributes = {
            "scheme": "",
            "netloc": "",
            "path": "",
            "query": "",
            "fragment": "",
            "username": None,
            "password": None,
            "hostname": None,
            "port": None,
        }


        o = None
        if urlstring:
            if isinstance(urlstring, type(self)):
                o = urlparse.urlsplit(urlstring.geturl())
            else:
                o = urlparse.urlsplit(urlstring)

        for k, v in urlparse_attributes.items():
            if o:
                setattr(self, k, getattr(o, k, v))
            else:
                setattr(self, k, v)

    def _parse_query(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        d = {}
        for k, kv in urlparse.parse_qs(query, True, strict_parsing=True).iteritems():
            #k = k.rstrip("[]") # strip out php type array designated variables
            if len(kv) > 1:
                d[k] = kv
            else:
                d[k] = kv[0]

        return d

    def _unparse_query(self, query_kwargs):
        return urllib.urlencode(query_kwargs, doseq=True)

    def _create(self, *args, **kwargs):
        return type(self)(*args, **kwargs)


class Http(object):
    def __init__(self):
        self.headers = Headers()

    def has_header(self, header_name):
        """return true if the header is set"""
        return header_name in self.headers

    def set_headers(self, headers):
        """replace all headers with passed in headers"""
        self.headers = Headers(headers)

    def add_headers(self, headers):
        self.headers.update(headers)

    def set_header(self, header_name, val):
        self.headers[header_name] = val

    def get_header(self, header_name, default_val=None):
        """try as hard as possible to get a a response header of header_name,
        rreturn default_val if it can't be found"""
        return self.headers.get(header_name, default_val)

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        u = Url(query=query)
        return u.query_kwargs

    def _build_body_str(self, b):
        # we are returning the body, let's try and be smart about it and match content type
        ct = self.get_header('content-type')
        if ct:
            ct = ct.lower()
            if ct.rfind(u"json") >= 0:
                if b:
                    b = json.dumps(b)
                else:
                    b = None

            elif ct.rfind(u"x-www-form-urlencoded") >= 0:
                b = urllib.urlencode(b, doseq=True)

        return b


class Request(Http):
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

    environ = None
    """holds all the values that aren't considered headers but usually get passed with the request"""

    raw_request = None
    """the original raw request that was filtered through one of the interfaces"""

    method = None
    """the http method (GET, POST)"""

    body_input = None
    """the request body input, if this is a POST request"""

    @_property
    def charset(self):
        """the character encoding of the request, usually only set in POST type requests"""
        charset = None
        ct = self.get_header('content-type')
        if ct:
            ah = AcceptHeader(ct)
            if ah.media_types:
                charset = ah.media_types[0][2].get("charset", None)

        return charset

    @property
    def access_token(self):
        """return an Oauth 2.0 Bearer access token if it can be found"""
        access_token = self.get_auth_bearer()
        if not access_token:
            if 'access_token' in self.query_kwargs:
                access_token = self.query_kwargs['access_token']

            elif 'access_token' in self.body_kwargs:
                access_token = self.body_kwargs['access_token']

        return access_token

    @_property(read_only=True)
    def ips(self):
        """return all the possible ips of this request, this will include public and private"""
        r = []
        headers = ['x-forwarded-for', 'client-ip', 'x-real-ip', 'x-forwarded', 
               'x-cluster-client-ip', 'forwarded-for', 'forwarded', 'via',
               'remote-addr']

        for h in headers:
            vs = self.get_header(h, '')
            if not vs: continue
            for v in vs.split(','):
                r.append(v.strip())

        return r

    @_property(read_only=True)
    def ip(self):
        """return the public ip address"""
        r = ''

        # this was compiled from here:
        # https://github.com/un33k/django-ipware
        # http://www.ietf.org/rfc/rfc3330.txt (IPv4)
        # http://www.ietf.org/rfc/rfc5156.txt (IPv6)
        regex = re.compile(ur'^(?:{})'.format(ur'|'.join([
            ur'[0-2]\.', # externally non-routable
            ur'10\.', # class A
            ur'169\.254', # link local block
            ur'172\.(?:1[6-9]|2[0-9]|3[0-1])', # class B
            ur'192\.0\.2', # documentation/examples
            ur'192\.168', # class C
            ur'255\.{3}', # broadcast address
            ur'2001\:db8', # documentation/examples
            ur'fc00\:', # private
            ur'fe80\:', # link local unicast
            ur'ff00\:', # multicast
            ur'127\.', # localhost
            ur'\:\:1' # localhost
        ])))

        ips = self.ips
        for ip in ips:
            if not regex.match(ip):
                r = ip
                break

        return r

    @_property
    def host(self):
        """return the request host"""
        return self.get_header("host")

    @_property
    def scheme(self):
        """return the request scheme (eg, http, https)"""
        scheme = self.environ.get('wsgi.url_scheme', "http")
        return scheme

    @_property
    def port(self):
        """return the server port"""
        return int(self.environ.get('SERVER_PORT', 0))

    @property
    def url(self):
        """return the full request url as an Url() instance"""
        scheme = self.scheme
        host = self.host
        path = self.path
        query = self.query
        port = self.port
        if port in [80, 443]:
            port = None

        u = Url(scheme=scheme, hostname=host, path=path, query=query, port=port)
        return u

    @_property
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        self._path = ''
        path_args = self.path_args
        path = u"/{}".format(u"/".join(path_args))
        return path

    @_property
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        self._path_args = []
        path = self.path
        path_args = filter(None, path.split(u'/'))
        return path_args

    @_property
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)"""
        self._query = query = u""

        query_kwargs = self.query_kwargs
        if query_kwargs: query = urllib.urlencode(query_kwargs, doseq=True)
        return query

    @_property
    def query_kwargs(self):
        """{foo: bar, baz: che}"""
        self._query_kwargs = query_kwargs = {}
        query = self.query
        if query: query_kwargs = self._parse_query_str(query)
        return query_kwargs

    @_property
    def body(self):
        """return the raw version of the body"""
        body = None
        if self.body_input:
            body = self.body_input.read(int(self.get_header('content-length', 0)))

        return body

    @body.setter
    def body(self, body):
        if hasattr(self, "_body_kwargs"):
            del(self._body_kwargs)

        self.body_input = None
        self._body = body

    @_property
    def body_kwargs(self):
        """
        the request body, if this is a POST request

        this tries to do the right thing with the body, so if you have set the body and
        the content type is json, then it will return the body json decoded, if you need
        the original string body, use body

        example --

            self.body = '{"foo":{"name":"bar"}}'
            b = self.body_kwargs # dict with: {"foo": { "name": "bar"}}
            print self.body # string with: u'{"foo":{"name":"bar"}}'
        """
        body_kwargs = {}
        ct = self.get_header("content-type")
        if ct:
            ct = ct.lower()
            if ct.rfind("json") >= 0:
                body = self.body
                if body:
                    body_kwargs = json.loads(body)

            else:
                if self.body_input:
                    body = Body(
                        fp=self.body_input,
                        headers=self.headers,
                        environ=self.environ
                        #environ=self.raw_request
                    )

                    body_kwargs = dict(body)

                else:
                    body = self.body
                    if body:
                        body_kwargs = self._parse_query_str(body)

        return body_kwargs

    @body_kwargs.setter
    def body_kwargs(self, body_kwargs):
        self.body_input = None
        self._body_kwargs = body_kwargs
        self._body = self._build_body_str(body_kwargs)

    def __init__(self):
        self.environ = {}
        super(Request, self).__init__()

    def is_method(self, method):
        """return True if the request method matches the passed in method"""
        return self.method.upper() == method.upper()

    def has_body(self):
        return self.method.upper() in set(['POST', 'PUT'])

    def get_auth_bearer(self):
        """return the bearer token in the authorization header if it exists"""
        access_token = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(ur"^Bearer\s+(\S+)$", auth_header, re.I)
            if m: access_token = m.group(1)

        return access_token

    def get_auth_basic(self):
        """return the username and password of a basic auth header if it exists"""
        username = ''
        password = ''
        auth_header = self.get_header('authorization')
        if auth_header:
            m = re.search(ur"^Basic\s+(\S+)$", auth_header, re.I)
            if m:
                auth_str = base64.b64decode(m.group(1))
                username, password = auth_str.split(':', 1)

        return username, password

    def get_auth_client(self):
        """try and get client id and secret first from basic auth header, then from
        GET or POST parameters

        return -- tuple -- client_id, client_secret
        """
        client_id, client_secret = self.request.get_auth_basic()
        if not client_id and not client_secret:
            client_id = self.query_kwargs.get('client_id', '')
            client_secret = self.query_kwargs.get('client_secret', '')
            if not client_id and not client_secret:
                client_id = self.body_kwargs.get('client_id', '')
                client_secret = self.body_kwargs.get('client_secret', '')

        return client_id, client_secret


class Response(Http):
    """
    an instance of this class is used to create the text response that will be sent 
    back to the client
    """
    @property
    def code(self):
        """the http status code to return to the client, by default, 200 if a body is present otherwise 204"""
        code = getattr(self, '_code', None)
        if not code:
            if self.has_body():
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
            status_tuple = BaseHTTPRequestHandler.responses.get(self.code)
            msg = "UNKNOWN"
            if status_tuple: msg = status_tuple[0]
            self._status = msg

        return self._status

    @status.setter
    def status(self, v):
        self._status = v

    @property
    def body(self):
        """return the body, formatted to the appropriate content type"""
        b = None
        if hasattr(self, '_body'):
            b = self._body

        return self.normalize_body(b)

    @body.setter
    def body(self, v):
        self._body = v

    def has_body(self):
        ret = False
        if hasattr(self, '_body'):
            r = getattr(self, '_body', None)
            if r is not None: ret = True

        else:
            ret = hasattr(self, '_gbody')

        return ret

    def normalize_body(self, b):
        """return the body as a string, formatted to the appropriate content type"""
        if b is None: return ''

        is_error = isinstance(b, Exception)
        ct = self.get_header('Content-Type')
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
                # no idea what to do here because we don't know how to handle the type
                b = str(b)

        else:
            # just return a string representation of body if no content type
            b = str(b)

        return b

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

        self.add_headers(cors_headers)

    def is_success(self):
        """return True if this response is considered a "successful" response"""
        code = self.code
        return code < 400


