
class CallError(Exception):
    """
    http errors can raise this with an HTTP status code and message

    All Endpoints' exceptions extend this
    """
    def __init__(self, code=500, msg='', *args, **kwargs):
        '''
        create the error

        code -- integer -- http status code
        msg -- string -- the message you want to accompany your status code
        '''
        self.code = code
        self.headers = kwargs.pop('headers', {})
        super(CallError, self).__init__(msg, *args, **kwargs)


class Redirect(CallError):
    """controllers can raise this to redirect to the new location"""
    def __init__(self, location, code=302, **kwargs):
        # set the realm header
        headers = kwargs.pop('headers', {})
        headers.setdefault('Location', location)
        kwargs['headers'] = headers
        super(Redirect, self).__init__(code, location, **kwargs)


class AccessDenied(CallError):
    """Any time you need to return a 401 you should return this

    .. seealso:: https://tools.ietf.org/html/rfc7235
    .. seealso: http://stackoverflow.com/questions/12701085/what-is-the-realm-in-basic-authentication
    """

    # used for http auth
    SCHEME_BASIC = "Basic"

    # used for Oauth access token
    SCHEME_BEARER = "Bearer"

    # used when nothing is specified
    SCHEME_DEFAULT = "Auth"

    def __init__(self, msg='', scheme="", realm="", **kwargs):
        """create an access denied error (401)

        This error adds the needed WWW-Authenticate header using the passed in
        scheme and realm. Rfc 7235 also includes type and title params but I didn't
        think they were worth adding right now so they are ignored

        Realm is no longer required, see https://tools.ietf.org/html/rfc7235#appendix-A

        :param msg: string, the message you want to accompany your status code
        :param scheme: usually one of the SCHEME_* constants but can really be anything
        :param realm: this is the namespace for the authentication scheme
        :param **kwargs: headers if you want to add custom headers
        """
        self.scheme = scheme.title() if scheme else self.SCHEME_DEFAULT
        self.realm = realm

        # set the realm header
        kwargs.setdefault("headers", {})
        v = "{} realm=\"{}\"".format(self.scheme, self.realm) if self.realm else self.scheme
        kwargs["headers"].setdefault("WWW-Authenticate", v)

        super(AccessDenied, self).__init__(401, msg, **kwargs)


class CallStop(CallError):
    """
    http requests can raise this with an HTTP status code and body if they don't want
    to continue to run code, this is just an easy way to short circuit processing
    """
    def __init__(self, code, body=None, msg='', **kwargs):
        '''
        create the stop object

        code -- integer -- http status code
        body -- mixed -- the body of the response
        '''
        self.body = body
        super(CallStop, self).__init__(code, msg, **kwargs)

