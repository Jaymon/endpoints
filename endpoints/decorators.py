import types

from .exception import CallError


class param(object):
    """
    decorator to allow setting certain expected query/body values and options

    this tries to be as similar to python's built-in argparse as possible

    This checks both POST and GET query args, if you would like to only check POST,
    use post_param, if you only want to check GET, then use get_param

    example --

    @decorators.param('name', type=int, nargs='+', action='store_list')

    name -- string -- the name of the query_param
    **flags -- dict
        type -- type -- a python type like int or float
        action -- string --
            store -- default
            store_false -- set if you want default to be true, and false if param is
                passed in
            store_true -- opposite of store_false
            store_list -- set to have a value like 1,2,3 be blown up to ['1', '2', '3']
            append -- if multiple param values should be turned into an array
                eg, foo=1&foo=2 would become foo=[1, 2]
            append_list -- it's store_list + append, so foo=1&foo=2,3 would be foo=[1, 2, 3]
        default -- mixed -- the value that should be set if query param isn't there
        required -- boolean -- True if param is required, default is true
        choices -- set() -- a set of values to be in tested against (eg, val in choices)

    raises -- 
        CallError -- with 400 status code on any param validation failures
    """
    def __init__(self, name, **flags):
        self.name = name
        self.flags = flags

    def find_param(self, pname, prequired, pdefault, request, args, kwargs):
        val = None
        val_post = False
        if request.has_body():
            try:
                d = request.body
                if not d: d = {}
                val = self.get_param(pname, prequired, pdefault, d)
                val_post = True

            except CallError:
                val = self.get_param(pname, prequired, pdefault, kwargs)

        else:
            val = self.get_param(pname, prequired, pdefault, kwargs)

        return val, val_post

    def get_param(self, name, required, default, params):
        val = None
        if required:
            try:
                val = params[name]

            except KeyError, e:
                raise CallError(400, "required param {} was not present".format(name))

        else:
            val = params.get(name, default)

        return val

    def normalize_param(self, slf, *args, **kwargs):
        name = self.name
        flags = self.flags
        ptype = flags.get('type', None)
        paction = flags.get('action', 'store')
        if paction == 'store_false':
            flags['default'] = True 
            ptype = bool

        elif paction == 'store_true':
            flags['default'] = False
            ptype = bool

        pdefault = flags.get('default', None)
        prequired = False if 'default' in flags else flags.get('required', True)
        pchoices = flags.get('choices', None)

        request = slf.request
        val, val_post = self.find_param(name, prequired, pdefault, request, args, kwargs)

        if paction in set(['store', 'store_list', 'store_false', 'store_true']):
            if isinstance(val, list):
                raise CallError(400, "too many values for param {}".format(name))

            if paction == 'store_list':
                if isinstance(val, types.StringTypes):
                    val = val.split(',')

                else:
                    val = list(val)

        elif paction in set(['append', 'append_list']):
            if not isinstance(val, list):
                val = [val]

            if paction == 'append_list':
                vs = []
                for v in val:
                    if isinstance(v, types.StringTypes):
                        vs.extend(v.split(','))
                    else:
                        vs.append(v)

                val = vs

        else:
            raise ValueError('unknown param action {}'.format(paction))


        if ptype:
            if isinstance(val, list):
                val = map(ptype, val)

            else:
                val = ptype(val)

        if pchoices:
            if val not in pchoices:
                raise CallError(400, "param {} with value {} not in choices {}".format(name, val, pchoices))

        if val_post:
            b = request.body
            if not b: b = {}
            b[name] = val
            request.body = b

        else:
            kwargs[name] = val

        return slf, args, kwargs

    def __call__(slf, func):
        def wrapper(self, *args, **kwargs):
            self, args, kwargs = slf.normalize_param(self, *args, **kwargs)
            return func(self, *args, **kwargs)

        return wrapper


class get_param(param):
    """same as param, but only checks GET params"""
    def find_param(self, name, prequired, pdefault, request, args, kwargs):
        val_post = False
        val = self.get_param(name, prequired, pdefault, kwargs)
        return val, val_post


class post_param(param):
    """same as param but only checks POST params"""
    def find_param(self, name, prequired, pdefault, request, args, kwargs):
        b = request.body
        if not b: b = {}
        val_post = True
        val = self.get_param(name, prequired, pdefault, b)
        return val, val_post


class require_params(object):
    """
    if you want to make sure that certain params are present in the request

    If the request is a GET request, then the params checked are in the query string,
    if the method is POST, PUT, then the params checked are in the body

    example --
    # make request fail if foo and bar aren't in the request body
    @require_params("foo", "bar")
    def POST(self, *args, **kwargs):
        pass

    **param_options -- dict
        allow_empty -- boolean -- True if passed in param names can have values
            that evaluate to False (like 0 or "")
    """
    def __init__(self, *req_param_names, **param_options):
        self.req_param_names = req_param_names
        self.param_options = param_options

    def __call__(slf, f):
        param_options = slf.param_options
        req_param_names = slf.req_param_names
        not_empty = not param_options.pop('allow_empty', False)

        def decorated(self, *args, **kwargs):
            if self.request.has_body():
                d = self.request.body
                if not d: d = {}

            else:
                d = self.request.query_kwargs

            for req_param_name in req_param_names:
                if req_param_name not in d:
                    raise CallError(400, "required param {} was not present".format(req_param_name))

                if not_empty and not d[req_param_name]:
                    raise CallError(400, "required param {} was empty".format(req_param_name))

            return f(self, *args, **kwargs)

        return decorated

