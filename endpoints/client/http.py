from __future__ import absolute_import
import urllib
import subprocess
import json
import os
import re

import requests
#from requests.auth import HTTPBasicAuth
from requests.auth import _basic_auth_str

from ..http import Headers, Url


class HTTPClient(object):
    """A generic test client that can make endpoint requests"""
    timeout = 10

    def __init__(self, host, *args, **kwargs):
        self.host = Url(host)

        # these are the common headers that usually don't change all that much
        self.headers = Headers({
            "x-forwarded-for": "127.0.0.1",
            "user-agent": "Endpoints client",
        })

        if kwargs.get("json", False):
            self.headers.update({
                "content-type": "application/json",
            })

    def get(self, uri, query=None, **kwargs):
        """make a GET request"""
        return self.fetch('get', uri, query, **kwargs)

    def post(self, uri, body=None, **kwargs):
        """make a POST request"""
        return self.fetch('post', uri, kwargs.pop("query", {}), body, **kwargs)

    def post_file(self, uri, body, files, **kwargs):
        """POST a file"""
        # requests doesn't actually need us to open the files but we do anyway because
        # if we don't then the filename isn't preserved, so we assume each string
        # value is a filepath
        for key in files.keys():
            if isinstance(files[key], basestring):
                files[key] = open(files[key], 'rb')
        kwargs["files"] = files

        # we ignore content type for posting files since it requires very specific things
        ct = self.headers.pop("content-type", None)
        ret = self.fetch('post', uri, {}, body, **kwargs)
        if ct:
            self.headers["content-type"] = ct
        return ret

    def post_chunked(self, uri, body, **kwargs):
        """POST a file to the uri using a Chunked transfer, this works exactly like
        the post() method, but this will only return the body because we use curl
        to do the chunked request"""
        filepath = kwargs.pop("filepath", None)
        url = self.get_url(uri)
        body = body or {}

        # http://superuser.com/a/149335/164279
        # http://comments.gmane.org/gmane.comp.web.curl.general/10711
        cmd = " ".join([
            "curl",
            '--header "Transfer-Encoding: Chunked"',
            '-F "file=@{}"'.format(filepath),
            '-F "{}"'.format(urllib.urlencode(body, doseq=True)),
            url
        ])
        with open(os.devnull, 'w') as stdnull:
            output = subprocess.check_output(cmd, shell=True, stderr=stdnull)

        return output

        # https://github.com/kennethreitz/requests/blob/master/requests/models.py#L260
        # I couldn't get Requests to successfully do a chunked request, but I could
        # get curl to do it, so that's what we're going to use
#         files = {'file': open(fileuri, 'rb')}
#         req = requests.Request('POST', url, data=body, files=files)
#         r = req.prepare()
#         r.headers.pop('Content-Length', None)
#         r.headers['Transfer-Encoding'] = 'Chunked'
# 
#         s = requests.Session()
#         s.stream = True
#         res = s.send(r)
#         return self.get_response(res)

        # another way to try chunked in pure python
        # http://stackoverflow.com/questions/9237961/how-to-force-http-client-to-send-chunked-encoding-http-body-in-python
        # http://stackoverflow.com/questions/17661962/how-to-post-chunked-encoded-data-in-python

        # and one more way to test it using raw sockets
        # http://lists.unbit.it/pipermail/uwsgi/2013-June/006170.html

    def delete(self, uri, query=None, **kwargs):
        """make a DELETE request"""
        return self.fetch('delete', uri, query, **kwargs)

    def fetch(self, method, uri, query=None, body=None, **kwargs):
        """
        wrapper method that all the top level methods (get, post, etc.) use to actually
        make the request
        """
        if not query: query = {}
        fetch_url = self.get_url(uri, query)

        args = [fetch_url]

        kwargs.setdefault("timeout", self.timeout)

        headers = self.headers
        if "headers" in kwargs:
            headers = headers.copy()
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        if body:
            kwargs['data'] = self.get_fetch_body(body)

        #pout.v(method, args, kwargs)
        res = requests.request(method, *args, **kwargs)
        res = self.get_fetch_response(res)
        self.response = res
        return res

    def get_query(self, query_str, query):
        if query:
            more_query_str = urllib.urlencode(query, doseq=True)
            if query_str:
                query_str += u'&{}'.format(more_query_str)
            else:
                query_str = more_query_str

        return query_str

    def get_url(self, uri, query=None):
        if re.match("^\S+://\S", uri): return uri

        base_url = self.host.host
        query_str = ''
        if '?' in uri:
            i = uri.index('?')
            query_str = uri[i+1:]
            uri = uri[0:i]

        uri = uri.lstrip('/')
        query_str = self.get_query(query_str, query)
        if query_str:
            uri = '{}?{}'.format(uri, query_str)

        ret_url = '{}/{}'.format(base_url, uri)
        return ret_url

    def get_fetch_body(self, body):
        return body

    def get_fetch_response(self, res):
        """the goal of this method is to make the requests object more endpoints like

        res -- requests Response -- the native requests response instance, we manipulate
            it a bit to make it look a bit more like the internal endpoints.Response object
        """
        res.code = res.status_code
        res.headers = Headers(res.headers)
        res._body = None
        res.body = ''
        body = res.content
        if body:
            if self.is_json(res.headers):
                res._body = res.json()
            else:
                res._body = body

            res.body = body

        return res

    def is_json(self, headers):
        """return true if content_type is a json content type"""
        ret = False
        ct = headers.get("content-type", "").lower()
        if ct:
            ret = ct.lower().rfind("json") >= 0
        return ret

    def basic_auth(self, username, password):
        '''
        add basic auth to this client

        link -- http://stackoverflow.com/questions/6068674/

        username -- string
        password -- string
        '''
        self.headers['authorization'] = _basic_auth_str(username, password)
#         credentials = HTTPBasicAuth(username, password)
#         #credentials = base64.b64encode('{}:{}'.format(username, password)).strip()
#         auth_string = 'Basic {}'.format(credentials())
#         self.headers['authorization'] = auth_string

    def token_auth(self, access_token):
        """add bearer TOKEN auth to this client"""
        self.headers['authorization'] = 'Bearer {}'.format(access_token)

    def remove_auth(self):
        self.headers.pop('authorization', None)

    def set_version(self, version):
        self.headers["accept"] = "{};version={}".format(
            self.headers["content-type"],
            version
        )

