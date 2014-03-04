
class Redirect(Exception):
    """controllers can raise this to redirect to the new location"""
    def __init__(self, location, code=302):
        self.code = code
        super(Redirect, self).__init__(location)


class CallError(RuntimeError):
    """
    http errors can raise this with an HTTP status code and message
    """
    def __init__(self, code, msg=''):
        '''
        create the error

        code -- integer -- http status code
        msg -- string -- the message you want to accompany your status code
        '''
        self.code = code
        super(CallError, self).__init__(msg)


class CallStop(Exception):
    """
    http requests can raise this with an HTTP status code and body if they don't want
    to continue to run code, this is just an easy way to short circuit processing
    """
    def __init__(self, code, body=None, msg=''):
        '''
        create the stop object

        code -- integer -- http status code
        body -- mixed -- the body of the response
        '''
        self.code = code
        self.body = body
        super(CallStop, self).__init__(msg)

