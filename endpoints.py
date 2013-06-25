# stdlib modules
import urlparse

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

class Mongrel2Request(Request):

    def __init__(self, req):
        h = req.headers
        self.path = h[u'PATH']
        self.query = h[u'QUERY']
        self.method = h[u'METHOD'].upper()

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


























