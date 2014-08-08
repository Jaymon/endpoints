import urlparse
import urllib
import json
import types
import re
import base64
from BaseHTTPServer import BaseHTTPRequestHandler

from .decorators import _property


class Http(object):
    headers = None
    """all the http request headers in header: val format"""

    def __init__(self):
        self.headers = {}

    def get_header(self, header_name, default_val=None):
        """try as hard as possible to get a a response header of header_name, return default_val if it can't be found"""
        header_names = [header_name, header_name.replace('-', '_')]
        ret = default_val
        headers = self.headers
        for hn in header_names:
            if hn in headers:
                ret = headers[hn]
                break
            elif hn.upper() in headers:
                ret = headers[hn.upper()]
                break
            elif hn.lower() in headers:
                ret = headers[hn.lower()]
                break
            elif hn.title() in headers:
                ret = headers[hn.title()]
                break
            elif hn.capitalize() in headers:
                ret = headers[hn.capitalize()]
                break

        return ret

    def _parse_body_str(self, b):
        # we are returning the string, let's try and be smart about it and match content type
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

    def _parse_json_str(self, query):
        return json.loads(query)

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        d = {}
        for k, kv in urlparse.parse_qs(query, True, strict_parsing=True).iteritems():
            if len(kv) > 1:
                d[k] = kv
            else:
                d[k] = kv[0]

        return d

    def _build_json_str(self, query):
        return json.dumps(query)

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
                b = self._build_query_str(b)

        return b

    def _build_query_str(self, query_kwargs):
        return urllib.urlencode(query_kwargs, doseq=True)


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
        self._body = body = None
        body_kwargs = self.body_kwargs
        if body_kwargs: body = self._build_body_str(body_kwargs)
        return body

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
        self._body_kwargs = {}
        b = self.body
        if b is None:
            b = {}

        else:
            # we are returning the body, let's try and be smart about it and match content type
            b = self._parse_body_str(b)

        return b

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
    def gbody(self):
        """yield the body, formatted to the appropriate content type"""
        gb = getattr(self, '_gbody', None)
        if gb is None:
            b = getattr(self, '_body', None)
            if b:
                self.body = b
                yield self.body

            else:
                self.body = None
                yield self.body

        else:
            for b in gb:
                self.body = b
                yield self.body

    @gbody.setter
    def gbody(self, v):
        if isinstance(v, types.GeneratorType):
            self._gbody = v
        else:
            self._gbody = (b for b in [v])

    @property
    def body(self):
        """return the body, formatted to the appropriate content type"""
        b = None
        if hasattr(self, '_body'):
            b = self._body

        else:
            gb = getattr(self, '_gbody', None)
            if gb:
                for b in gb: self._body = b

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

        self.headers.update(cors_headers)


