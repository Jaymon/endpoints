# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os
import json
import types
import re
from functools import partial
from wsgiref.headers import Headers as BaseHeaders
import itertools
import logging
import inspect
import copy
from socket import gethostname

from datatypes import Url as BaseUrl, Host

from .compat import *
from .decorators.utils import _property
from .utils import AcceptHeader, ByteString, MimeType, String, Base64, Deepcopy


logger = logging.getLogger(__name__)


class Headers(BaseHeaders, Mapping):
    """handles headers, see wsgiref.Headers link for method and use information

    Handles normalizing of header names, the problem with headers is they can
    be in many different forms and cases and stuff (eg, CONTENT_TYPE and Content-Type),
    so this handles normalizing the header names so you can request Content-Type
    or CONTENT_TYPE and get the same value.

    This has the same interface as Python's built-in wsgiref.Headers class but
    makes it even more dict-like and will return titled header names when iterated
    or anything (eg, Content-Type instead of all lowercase content-type)

    http headers spec:
        https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

    wsgiref class docs:
        https://docs.python.org/2/library/wsgiref.html#module-wsgiref.headers
        https://hg.python.org/cpython/file/2.7/Lib/wsgiref/headers.py
    actual python3 code:
        https://github.com/python/cpython/blob/master/Lib/wsgiref/headers.py
    """
    def __init__(self, headers=None, **kwargs):
        super(Headers, self).__init__([])
        self.update(headers, **kwargs)

    def _convert_string_part(self, bit):
        """each part of a header will go through this method, this allows further
        normalization of each part, so a header like FOO_BAR would call this method
        twice, once with foo and again with bar

        :param bit: string, a part of a header all lowercase
        :returns: string, the normalized bit
        """
        if bit == "websocket":
            bit = "WebSocket"
        else:
            bit = bit.title()
        return bit

    def _convert_string_name(self, k):
        """converts things like FOO_BAR to Foo-Bar which is the normal form"""
        k = String(k, "iso-8859-1")
        bits = k.lower().replace('_', '-').split('-')
        return "-".join((self._convert_string_part(bit) for bit in bits))

    def _convert_string_type(self, v):
        """Override the internal method wsgiref.headers.Headers uses to check values
        to make sure they are strings"""
        # wsgiref.headers.Headers expects a str() (py3) or unicode (py2), it
        # does not accept even a child of str, so we need to convert the String
        # instance to the actual str, as does the python wsgi methods, so even
        # though we override this method we still return raw() strings so we get
        # passed all the type(v) == "str" checks
        # sadly, this method is missing in 2.7
        # https://github.com/python/cpython/blob/2.7/Lib/wsgiref/headers.py
        return String(v).raw()

    def get_all(self, name):
        name = self._convert_string_name(name)
        return super(Headers, self).get_all(name)

    def get(self, name, default=None):
        name = self._convert_string_name(name)
        return super(Headers, self).get(name, default)

    def __delitem__(self, name):
        name = self._convert_string_name(name)
        return super(Headers, self).__delitem__(name)

    def __setitem__(self, name, val):
        name = self._convert_string_name(name)
        if is_py2:
            val = self._convert_string_type(val)
        return super(Headers, self).__setitem__(name, val)

    def setdefault(self, name, val):
        name = self._convert_string_name(name)
        if is_py2:
            val = self._convert_string_type(val)
        return super(Headers, self).setdefault(name, val)

    def add_header(self, name, val, **params):
        name = self._convert_string_name(name)
        if is_py2:
            val = self._convert_string_type(val)
        return super(Headers, self).add_header(name, val, **params)

    def keys(self):
        return [k for k, v in self._headers]

    def items(self):
        for k, v in self._headers:
            yield k, v

    def iteritems(self):
        return self.items()

    def iterkeys(self):
        for k in self.keys():
            yield k

    def __iter__(self):
        for k, v in self._headers:
            yield k

    def pop(self, name, *args, **kwargs):
        """remove and return the value at name if it is in the dict

        This uses *args and **kwargs instead of default because this will raise
        a KeyError if default is not supplied, and if it had a definition like
        (name, default=None) you wouldn't be able to know if default was provided
        or not

        :param name: string, the key we're looking for
        :param default: mixed, the value that would be returned if name is not in
            dict
        :returns: the value at name if it's there
        """
        val = self.get(name)
        if val is None:
            if args:
                val = args[0]
            elif "default" in kwargs:
                val = kwargs["default"]
            else:
                raise KeyError(name)

        else:
            del self[name]

        return val

    def update(self, headers, **kwargs):
        if not headers: headers = {}
        if isinstance(headers, Mapping):
            headers.update(kwargs)
            headers = headers.items()

        else:
            if kwargs:
                headers = itertools.chain(
                    headers,
                    kwargs.items()
                )

        for k, v in headers:
            self[k] = v

    def copy(self):
        return Deepcopy().copy(self)

    def list(self):
        """Return all the headers as a list of headers instead of a dict"""
        return [": ".join(h) for h in self.items() if h[1]]


class Environ(Headers):
    """just like Headers but allows any values (headers converts everything to unicode
    string)"""
    def _convert_string_type(self, v):
        return v


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

        if self.controller_info:
            memodict.setdefault("controller_info", self.controller_info)

        return Deepcopy(ignore_private=True).copy(self, memodict)

    def is_json(self):
        ct = self.get_header('Content-Type')
        return ct.lower().rfind("json") >= 0 if ct else False


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

    @_property
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

    @_property(read_only=True)
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

    @_property(read_only=True)
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

    @_property
    def path(self):
        """path part of a url (eg, http://host.com/path?query=string)"""
        self._path = ''
        path_args = self.path_args
        path = "/{}".format("/".join(path_args))
        return path

    @_property
    def path_args(self):
        """the path converted to list (eg /foo/bar becomes [foo, bar])"""
        self._path_args = []
        path = self.path
        path_args = list(filter(None, path.split('/')))
        return path_args

    @_property
    def query(self):
        """query_string part of a url (eg, http://host.com/path?query=string)"""
        self._query = query = ""

        query_kwargs = self.query_kwargs
        if query_kwargs: query = urlencode(query_kwargs, doseq=True)
        return query

    @_property
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


