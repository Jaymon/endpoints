# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import json
import types
import re
from functools import partial
import itertools
import logging
import inspect
import copy
from socket import gethostname
import cgi
import io

from datatypes import Url as BaseUrl, Host, Headers as BaseHeaders, Environ

from .compat import *
from .decorators.utils import property # must be .utils because circular dep
from .utils import (
    AcceptHeader,
    MimeType,
    Base64,
    Deepcopy,
    FileWrapper,
)


logger = logging.getLogger(__name__)


class Headers(BaseHeaders):
    def is_plain(self):
        """return True if body's content-type is text/plain"""
        ct = self.get("Content-Type", "")
        return "plain" in ct

    def is_json(self):
        """return True if body's content-type is application/json"""
        ct = self.get("Content-Type", "")
        return "json" in ct

    def is_urlencoded(self):
        """return True if body's content-type is application/x-www-form-urlencoded"""
        ct = self.get("Content-Type", "")
        return ("form-urlencoded" in ct) or ("form-data" in ct)

    def is_multipart(self):
        """return True if body's content-type is multipart/form-data"""
        ct = self.get("Content-Type", "")
        return "multipart" in ct


class Body(cgi.FieldStorage, object):
    """Wraps the default FieldStorage to handle json and also recovers when the
    input fails to parse correctly

    https://github.com/python/cpython/blob/2.7/Lib/cgi.py
    https://github.com/python/cpython/blob/3.8/Lib/cgi.py
    """
    FieldStorageClass = cgi.FieldStorage

    @property(cached="_args")
    def args(self):
        return getattr(self, "json_args", [])

    @property(cached="_kwargs")
    def kwargs(self):
        body_kwargs = {}
        body_kwargs.update(getattr(self, "json_kwargs", {}))

        # we only have a list when we had a multiport or data-form submission
        if getattr(self, "list"):
            for field_name in self.keys():
                body_field = self[field_name]
                if body_field.filename:
                    body_kwargs[field_name] = FileWrapper(
                        body_field.file,
                        name=body_field.filename,
                        filename=body_field.filename,
                        type=body_field.type,
                        raw=body_field,
                    )

                else:
                    body_kwargs[field_name] = body_field.value


        return body_kwargs

    def __init__(self, fp, request, **kwargs):
        if request.headers.get('transfer-encoding', "").lower().startswith("chunked"):
            raise IOError("Chunked bodies are not supported")

        self.request = request

        # py3 compatibility
        self.encoding = request.encoding
        self.errors = "replace"
        self.max_num_fields = None

        self.name = self.filename = self.value = None
        self.length = int(request.headers.get("CONTENT_LENGTH", -1))
        self.fp = fp
        self.list = None

        if self.length > 0:
            if request.is_json():
                self.read_json()

            else:
                kwargs.setdefault("keep_blank_values", True)

                # so FieldStorage parses the body in the constructor and if it fails
                # then the body instance won't be created, so this is set to True and
                # the error is handled in read_urlencoded
                kwargs["strict_parsing"] = True

                super(Body, self).__init__(
                    fp=fp,
                    headers=request.headers,
                    environ=request.environ,
                    **kwargs
                )

    def is_plain(self):
        """return True if body's content-type is text/plain"""
        return self.request.headers.is_plain()

    def is_json(self):
        """return True if body's content-type is application/json"""
        return self.request.headers.is_json()

    def is_urlencoded(self):
        """return True if body's content-type is application/x-www-form-urlencoded"""
        return self.request.headers.is_urlencoded()

    def is_multipart(self):
        """return True if body's content-type is multipart/form-data"""
        return self.request.headers.is_multipart()

    def read_json(self):
        body = self.fp.read(self.length)
        self.file = io.BytesIO(body)

        body_args = []
        body_kwargs = {}
        b = json.loads(body)
        if isinstance(b, list):
            body_args = b

        elif isinstance(b, dict):
            body_kwargs = b

        else:
            body_args = [b]

        self.json_args = body_args
        self.json_kwargs = body_kwargs

    def read_urlencoded(self):
        """Internal: read data in query string format."""
        body = self.fp.read(self.length)
        self.file = io.BytesIO(body)

        qs = String(body, self.encoding, self.errors)

        if self.qs_on_post:
            qs += '&' + self.qs_on_post

        try:
            if is_py2:
                query = parse.parse_qsl(
                    qs,
                    self.keep_blank_values,
                    self.strict_parsing,
                )

            else:
                query = parse.parse_qsl(
                    qs,
                    self.keep_blank_values,
                    self.strict_parsing,
                    encoding=self.encoding,
                    errors=self.errors,
                    max_num_fields=self.max_num_fields
                )

        except ValueError:
            # if the right headers were sent then this should error
            if self.is_urlencoded() or self.is_multipart():
                raise

        else:
            self.list = [cgi.MiniFieldStorage(key, value) for key, value in query]
            self.skip_lines()

    def make_file(self, *args, **kwargs):
        return io.BytesIO()

    def seek(self, *args, **kwargs):
        return self.file.seek(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.file.read(*args, **kwargs)

    def tell(self, *args, **kwargs):
        return self.file.tell(*args, **kwargs)


class Url(BaseUrl):
    """a url object on steroids, this is here to make it easy to manipulate urls
    we try to map the supported fields to their urlparse equivalents, with some additions

    https://tools.ietf.org/html/rfc3986.html

    given a url http://user:pass@foo.com:1000/bar/che?baz=boom#anchor
    with a controller: Bar

    .scheme = http
    .netloc = user:pass@foo.com:1000
    .hostloc = foo.com:1000
    .hostname = foo.com
    .host() = http://foo.com
    .port = 1000
    .base = http://user:pass@foo.com:1000/bar/che
    .fragment = anchor
    .anchor = fragment
    .uri = /bar/che?baz=boom#anchor
    .host(...) = http://foo.com/...
    .base(...) = http://foo.com/bar/che/...
    .controller(...) = http://foo.com/bar/...
    """
    class_path = ""

    module_path = ""

    def module(self, *paths, **query_kwargs):
        """create a new Url instance using the module path as a base

        :param *paths: list, the paths to append to the module path
        :param **query_kwargs: dict, any query string params to add
        :returns: new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)
        if self.module_path:
            if "path" in kwargs:
                paths = self.normalize_paths(self.module_path, kwargs["path"])
                kwargs["path"] = "/".join(paths)
            else:
                kwargs["path"] = self.module_path
        return self.create(self.root, **kwargs)

    def controller(self, *paths, **query_kwargs):
        """create a new url object using the controller path as a base

        if you have a controller `foo.BarController` then this would create a new
        Url instance with `host/foo/bar` as the base path, so any *paths will be
        appended to `/foo/bar`

        :example:
            # controller foo.Bar(Controller)

            print url # http://host.com/foo/bar/some_random_path

            print url.controller() # http://host.com/foo/bar
            print url.controller("che", boom="bam") # http://host/foo/bar/che?boom=bam

        :param *paths: list, the paths to append to the controller path
        :param **query_kwargs: dict, any query string params to add
        :returns: new Url instance
        """
        kwargs = self._normalize_params(*paths, **query_kwargs)
        if self.class_path:
            if "path" in kwargs:
                paths = self.normalize_paths(self.class_path, kwargs["path"])
                kwargs["path"] = "/".join(paths)
            else:
                kwargs["path"] = self.class_path
        return self.create(self.root, **kwargs)


class Http(object):
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

    def get_header(self, header_name, default_val=None):
        """try as hard as possible to get a a response header of header_name,
        rreturn default_val if it can't be found"""
        return self.headers.get(header_name, default_val)

    def find_header(self, header_names, default_val=None):
        """given a list of headers return the first one you can, default_val if you
        don't find any

        :param header_names: list, a list of headers, first one found is returned
        :param default_val: mixed, returned if no matching header is found
        :returns: mixed, the value of the header or default_val
        """
        ret = default_val
        for header_name in header_names:
            if self.has_header(header_name):
                ret = self.get_header(header_name, default_val)
                break
        return ret

    def _parse_query_str(self, query):
        """return name=val&name2=val2 strings into {name: val} dict"""
        u = Url(query=query)
        return u.query_kwargs

    def _build_body_str(self, b):
        # we are returning the body, let's try and be smart about it and match content type
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
        return copy.deepcopy(self)

    def __deepcopy__(self, memodict=None):
        memodict = memodict or {}

        memodict.setdefault("controller_info", getattr(self, "controller_info", {}))
        memodict.setdefault("body", getattr(self, "body", None))

        return Deepcopy(ignore_private=True).copy(self, memodict)

    def is_json(self):
        return self.headers.is_json()


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

    controller_info = None
    """will hold the controller information for the request, populated from the Call"""

    body_class = Body
    """see create_body()"""

    @property
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

    @property(cached="_encoding")
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

    @property(read_only="_ips")
    def ips(self):
        """return all the possible ips of this request, this will include public and private ips"""
        r = []
        names = ['X_FORWARDED_FOR', 'CLIENT_IP', 'X_REAL_IP', 'X_FORWARDED', 
               'X_CLUSTER_CLIENT_IP', 'FORWARDED_FOR', 'FORWARDED', 'VIA',
               'REMOTE_ADDR']

        for name in names:
            vs = self.get_header(name, '')
            if vs:
                r.extend(map(lambda v: v.strip(), vs.split(',')))

            vs = self.environ.get(name, '')
            if vs:
                r.extend(map(lambda v: v.strip(), vs.split(',')))

        return r

    @property(read_only="_ip")
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

    @property(cached="_host")
    def host(self):
        """return the request host"""
        return self.get_header("host")

    @property(cached="_scheme")
    def scheme(self):
        """return the request scheme (eg, http, https)"""
        scheme = self.environ.get('wsgi.url_scheme', "http")
        return scheme

    @property(cached="_port")
    def port(self):
        """return the server port"""
        return int(self.environ.get('SERVER_PORT', 0))

    @property
    def host_url(self):
        """return the request host as a Url instance"""
        return self.url.host_url()

    @property
    def url(self):
        """return the full request url as an Url() instance"""
        scheme = self.scheme
        host = self.host
        path = self.path
        query = self.query
        port = self.port

        # normalize the port
        host_domain, host_port = Url.split_hostname_from_port(host)
        if host_port:
            port = host_port

        class_path = ""
        module_path = ""
        if self.controller_info:
            class_path = self.controller_info.get("class_path", "")
            module_path = self.controller_info.get("module_path", "")

        u = Url(
            scheme=scheme,
            hostname=host,
            path=path,
            query=query,
            port=port,
            class_path=class_path,
            module_path=module_path
        )
        return u

    @property(cached="_path")
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        self._path = ''
        path_args = self.path_args
        path = "/{}".format("/".join(path_args))
        return path

    @property(cached="_path_args")
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        self._path_args = []
        path = self.path
        path_args = list(filter(None, path.split('/')))
        return path_args

    @property(cached="_query")
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)"""
        self._query = query = ""

        query_kwargs = self.query_kwargs
        if query_kwargs: query = urlencode(query_kwargs, doseq=True)
        return query

    @property(cached="_query_kwargs")
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
        self.environ = Environ()
        self.body = None
        self.body_args = []
        self.body_kwargs = {}
        super(Request, self).__init__()

    def create_body(self, body):
        return self.body_class(body, self)

    def version(self, content_type="*/*"):
        """
        versioning is based off of this post 
        http://urthen.github.io/2013/05/09/ways-to-version-your-api/
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
        """return the username and password of a basic auth header if it exists"""
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
        will check for values like "client_id" and "client_secret" being passed up
        in the body because javascript doesn't want to set headers in websocket
        connections

        :param scheme: string, the scheme you want to check, usually "basic" or "bearer"
        :return: boolean
        """
        scheme = scheme.lower()
        if scheme in set(["bearer", "token", "access"]):
            access_token = self.access_token
            return True if access_token else False

        elif scheme in set(["basic", "client"]):
            client_id, client_secret = self.client_tokens
            return True if (client_id and client_secret) else False


class Response(Http):
    """The Response object, every request instance that comes in will get a
    corresponding Response instance that answers the Request.

    an instance of this class is used to create the text response that will be sent 
    back to the client

    Request has a ._body and .body, the ._body property is the raw value that is
    returned from the Controller method that handled the request, the .body property
    is a string that is ready to be sent back to the client, so it is _body converted
    to a string. The reason _body isn't name body_kwargs is because _body can be
    almost anything (not just a dict)
    """

    encoding = ""

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
        self._status = None

    @property
    def status_code(self): return self.code

    @status_code.setter
    def status_code(self, v): self.code = v

    @property
    def status(self):
        """The full http status (the first line of the headers in a server response)"""
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
        return getattr(self, "_body", None)

    @body.setter
    def body(self, v):
        self._body = v
        if self.is_file():
            filepath = getattr(v, "name", "")
            if filepath:
                mt = MimeType.find_type(filepath)
                filesize = os.path.getsize(filepath)
                self.set_header("Content-Type", mt)
                self.set_header("Content-Length", filesize)
                logger.debug(
                    "Response body set to file: \"{}\" with mimetype: \"{}\" and size: {}".format(
                        filepath,
                        mt,
                        filesize
                    )
                )

            else:
                logger.warn("Response body is a filestream that has no .filepath property")

    def has_body(self):
        """return True if there is an actual response body"""
        return getattr(self, "_body", None) is not None

    def is_file(self):
        """return True if the response body is a file pointer"""
        # http://stackoverflow.com/questions/1661262/check-if-object-is-file-like-in-python
        return hasattr(self._body, "read") if self.has_body() else False

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
    is_successful = is_success


