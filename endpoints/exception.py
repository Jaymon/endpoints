
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
    """Any time you need to return a 401 you should return this"""

    # used for http auth
    REALM_BASIC = "Basic"

    # used for OAuth
    REALM_DIGEST = "Digest"

    def __init__(self, realm, msg='', **kwargs):
        '''
        create the error

        realm -- string -- usually either 'Basic' or 'Digest'
        msg -- string -- the message you want to accompany your status code
        '''
        self.realm = realm.title()

        # set the realm header
        headers = kwargs.pop('headers', {})
        headers.setdefault('WWW-Authenticate', self.realm)
        kwargs['headers'] = headers

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

