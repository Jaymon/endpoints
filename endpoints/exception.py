
class Redirect(Exception):
    """controllers can raise this to redirect to the new location"""
    def __init__(self, location, code=302):
        self.code = code
        super(Redirect, self).__init__(location)


class CallError(RuntimeError):
    """
    http errors can raise this with an HTTP status code and message
    """
    def __init__(self, code, msg):
        '''
        create the error

        code -- integer -- http status code
        msg -- string -- the message you want to accompany your status code
        '''
        self.code = code
        super(CallError, self).__init__(msg)

