import types

from .exception import CallError

#@decorators.param('user_id', type=int, nargs='+', action=query_list)

def get_param(name, **flags):
    """
    decorator to allow setting certain expected query values and options

    this tries to be as similar to python's built-in argparse as possible

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
    ptype = flags.get('type', None)
    paction = flags.get('action', 'store')
    if paction == 'store_false':
        flags['default'] = True 
        ptype = bool
    elif paction == 'store_true':
        flags['default'] = False
        ptype = bool

    #pnargs = flags.get('nargs', 1)

    pdefault = flags.get('default', None)
    prequired = False if 'default' in flags else flags.get('required', True)
    pchoices = flags.get('choices', None)

    def real_decorator(func):

        def wrapper(self, *args, **kwargs):

            val = None
            if prequired:
                try:
                    val = kwargs[name]
                except KeyError, e:
                    raise CallError(400, "required param {} was not present".format(name))

            else:
                val = kwargs.get(name, pdefault)

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

            kwargs[name] = val

            return func(self, *args, **kwargs)

        return wrapper

    return real_decorator 

