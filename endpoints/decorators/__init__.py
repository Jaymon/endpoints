from __future__ import absolute_import
import types
import re
import cgi
from functools import wraps
import datetime
import logging

from decorators import FuncDecorator

from ..exception import CallError, AccessDenied
from . import auth
from .base import TargetDecorator


logger = logging.getLogger(__name__)


class ratelimit(TargetDecorator):
    """Rate limit a certain endpoint

    example --

    from endpoints import Controller
    from endpoints.decorators import ratelimit

    class Default(Controller):
        @ratelimit(10, 3600) # you can make 10 requests per hour
        def GET(self):
            return "hello world"
    """
    def target(self, request, key, limit, ttl):
        """this is what is run to check if requests should be throttled

        you should override this method if you want to customize the implementation

        request -- Request -- the request instance
        key -- string -- the unique key for the endpoint
        limit -- int -- max requests that should be received in ttl
        ttl -- int -- how many seconds they should be throttled for (3600 = 1 hour)
        """
        now = datetime.datetime.utcnow()
        count = 1
        calls = getattr(self, "_calls", {})
        if not calls:
            calls = {}

        if key in calls:
            count = calls[key]["count"] + 1
            if count > limit:
                td = now - calls[key]["date"]
                if td.total_seconds() < ttl:
                    raise ValueError(
                        "Please wait {} seconds to make another request".format(ttl - td.seconds)
                    )

                else:
                    count = 1 # we are starting over

        calls[key] = {
            "count": count,
            "date": now,
        }

        self._calls = calls
        return True

    def normalize_target_params(self, request, controller_args, controller_kwargs):
        kwargs = {
            "request": request,
            "key": self.normalize_key(
                request,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs,
            ),
            "limit": self.limit,
            "ttl": self.ttl,
        }
        return [], kwargs

    def normalize_key(self, request, *args, **kwargs):
        """if you don't want to override target but do want to customize the key,
        override this method, this is mainly for convenience of child classes"""
        return "{}.{}".format(request.ip, request.path)

    def handle_error(self, e):
        """all exceptions should generate 429 responses"""
        raise CallError(429, e.message)

    def decorate(self, func, limit, ttl, *anoop, **kwnoop):
        """see target for an explanation of limit and ttl"""
        self.limit = int(limit)
        self.ttl = int(ttl)
        return super(ratelimit, self).decorate(func, target=None, *anoop, **kwnoop)


class httpcache(FuncDecorator):
    """
    sets the cache headers so the response can be cached by the client

    link -- https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching

    ttl -- integer -- how many seconds to have the client cache the request
    """
    def decorate(self, func, ttl):
        def decorated(self, *args, **kwargs):
            self.response.add_headers({
                "Cache-Control": "max-age={}".format(ttl),
            })
            return func(self, *args, **kwargs)
            # TODO -- figure out how to set ETag
            #if not self.response.has_header('ETag')

        return decorated


class nohttpcache(FuncDecorator):
    """
    sets all the no cache headers so the response won't be cached by the client
    """
    def decorate(self, func):
        def decorated(self, *args, **kwargs):
            self.response.add_headers({
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache", 
                "Expires": "0"
            })
            return func(self, *args, **kwargs)

        return decorated


class _property(object):
    """A memoized @property that is only evaluated once, and then stored at _property
    and retrieved from there unless deleted, in which case this would be called
    again and stored in _property again.

    See http://www.reddit.com/r/Python/comments/ejp25/cached_property_decorator_that_is_memory_friendly/
    see https://docs.python.org/2/howto/descriptor.html
    see http://stackoverflow.com/questions/17330160/python-how-does-the-property-decorator-work
    see https://docs.python.org/2/howto/descriptor.html

    options you can use to further customize the property

    read_only -- boolean (default False) -- set to de-activate set and del methods
    allow_empty -- boolean (default True) -- False to not cache empty values (eg, None, "")
    setter -- boolean -- set this to true if you want the decorated method to act as the setter
        instead of the getter, this will cause a default getter to be created that just returns
        _name (you should set self._name in your setter)
    deleter -- boolean -- same as setter, set to True to have the method act as the deleter
    """
    def __init__(self, *args, **kwargs):
        self.allow_empty = kwargs.get('allow_empty', True)
        self.has_setter = kwargs.get('setter', False)
        self.has_deleter = kwargs.get('deleter', False)

        has_no_write = not self.has_setter and not self.has_deleter
        self.has_getter = kwargs.get('getter', has_no_write)

        # mutually exclusive to having defined a setter or deleter
        self.read_only = kwargs.get('read_only', False) and has_no_write

        if args:
            if isinstance(args[0], bool):
                self.read_only = args[0]

            else:
                # support _property(fget, fset, fdel, desc) also
                total_args = len(args)
                self.set_method(args[0])
                if total_args > 1:
                    self.setter(args[1])
                if total_args > 2:
                    self.deleter(args[2])
                if total_args > 3:
                    self.__doc__ = args[3]

        # support _property(fget=getter, fset=setter, fdel=deleter, doc="")
        if "fget" in kwargs:
            self.set_method(kwargs["fget"])
        if "fset" in kwargs:
            self.setter(kwargs["fset"])
        if "fdel" in kwargs:
            self.deleter(kwargs["fdel"])
        if "doc" in kwargs:
            self.__doc__ = kwargs["doc"]

    def set_method(self, method):
        self.fget = method if self.has_getter else self.default_get
        self.fset = method if self.has_setter else self.default_set
        self.fdel = method if self.has_deleter else self.default_del
        self.__doc__ = method.__doc__
        self.__name__ = method.__name__
        self.name = '_{}'.format(self.__name__)

    def __call__(self, *args, **kwargs):
        if args:
            self.set_method(args[0])

        return self

    def __get__(self, instance, cls):
        # return the cached value if it exists
        val = None
        name = self.name
        if name in instance.__dict__:
            val = instance.__dict__[name]

        else:
            try:
                val = self.fget(instance)
                if val or self.allow_empty:
                    # We don't do fset here because that causes unexpected bahavior
                    # if you ever override the setter, causing the setter to be fired
                    # every time the getter is called, which confused me for about
                    # an hour before I figured out what was happening
                    self.default_set(instance, val)

            except Exception:
                # make sure no value gets set no matter what
                instance.__dict__.pop(name, None)
                raise

        return val

    def default_get(self, instance):
        try:
            return instance.__dict__[self.name]
        except KeyError:
            raise AttributeError("can't get attribute {}".format(self.__name__))

    def default_set(self, instance, val):
        instance.__dict__[self.name] = val

    def __set__(self, instance, val):
        if self.read_only:
            raise AttributeError("can't set attribute {}".format(self.__name__))

        if val or self.allow_empty:
            self.fset(instance, val)

    def default_del(self, instance):
        instance.__dict__.pop(self.name, None)

    def __delete__(self, instance, *args):
        if self.read_only:
            raise AttributeError("can't delete attribute {}".format(self.__name__))

        self.fdel(instance)

    def getter(self, fget):
        self.fget = fget
        self.has_getter = True
        return self

    def setter(self, fset):
        self.fset = fset
        self.has_setter = True
        return self

    def deleter(self, fdel):
        self.fdel = fdel
        self.has_deleter = True
        return self


class _propertyset(_property):
    def set_method(self, method):
        super(_propertyset, self).set_method(method)

        # switch get and set since this method is 
        self.fget = self.default_get
        self.fset = method

    def set_method(self, method):
        self.fget = method
        self.fset = self.default_set
        self.fdel = self.default_del
        self.__doc__ = method.__doc__
        self.__name__ = method.__name__
        self.name = '_{}'.format(self.__name__)



class param(object):
    """
    decorator to allow setting certain expected query/body values and options

    this tries to be as similar to python's built-in argparse as possible

    This checks both POST and GET query args, if you would like to only check POST,
    use post_param, if you only want to check GET, then use get_param

    example --

    @decorators.param('name', type=int, action='store_list')

    name -- string -- the name of the query_param
    **flags -- dict
        dest -- string -- the key in kwargs this param will be set into
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
        default -- mixed -- the value that should be set if query param isn't there, if this is
            callable (eg, time.time or datetime.utcnow) then it will be called every time the
            decorated method is called
        required -- boolean -- True if param is required, default is true
        choices -- set() -- a set of values to be in tested against (eg, val in choices)
        allow_empty -- boolean -- True allows values like False, 0, '' through,
            default False, this will also let through any empty value that was set
            via the default flag
        max_size -- int -- the maximum size of the param
        min_size -- int -- the minimum size of the param
        regex -- regexObject -- if you would like the param to be validated with a regular
            exception, uses the re.search() method
        help -- string -- a helpful description for this param

    raises -- 
        CallError -- with 400 status code on any param validation failures
    """
    def __init__(self, *names, **flags):
        self.normalize_type(names)
        self.normalize_flags(flags)

    def normalize_flags(self, flags):
        """normalize the flags to make sure needed values are there

        after this method is called self.flags is available

        :param flags: the flags that will be normalized
        """
        flags['type'] = flags.get('type', None)
        paction = flags.get('action', 'store')
        if paction == 'store_false':
            flags['default'] = True 
            flags['type'] = bool

        elif paction == 'store_true':
            flags['default'] = False
            flags['type'] = bool

        prequired = False if 'default' in flags else flags.get('required', True)

        flags["action"] = paction
        flags["required"] = prequired
        self.flags = flags

    def normalize_type(self, names):
        """Decide if this param is an arg or a kwarg and set appropriate internal flags"""
        self.name = names[0]
        self.is_kwarg = False
        self.is_arg = False
        self.names = []

        try:
            # http://stackoverflow.com/a/16488383/5006 uses ask forgiveness because
            # of py2/3 differences of integer check
            self.index = int(self.name)
            self.name = ""
            self.is_arg = True

        except ValueError:
            self.is_kwarg = True
            self.names = names

    def normalize_default(self, default):
        ret = default
        if isinstance(default, dict):
            ret = dict(default)

        elif isinstance(default, list):
            ret = list(default)

        else:
            if callable(default):
                ret = default()

        return ret

    def normalize_param(self, slf, args, kwargs):
        """this is where all the magic happens, this will try and find the param and
        put its value in kwargs if it has a default and stuff"""
        if self.is_kwarg:
            kwargs = self.normalize_kwarg(slf.request, kwargs)
        else:
            args = self.normalize_arg(slf.request, args)
        return slf, args, kwargs

    def normalize_arg(self, request, args):
        flags = self.flags
        index = self.index
        args = list(args)

        paction = flags['action']
        if paction not in set(['store', 'store_false', 'store_true']):
            raise RuntimeError('unsupported positional param action {}'.format(paction))

        if 'dest' in flags:
            logger.warn("dest is ignored in positional param")

        try:
            val = args.pop(index)

        except IndexError:
            if flags["required"]:
                raise CallError(400, "required positional param at index {} does not exist".format(index))

            else:
                val = self.normalize_default(flags.get('default', None))

        try:
            val = self.normalize_val(request, val)

        except ValueError as e:
            raise CallError(400, "Positional arg {} failed with {}".format(index, e.message))

        args.insert(index, val)

        return args

    def find_kwarg(self, request, names, required, default, kwargs):
        """actually try to retrieve names key from params dict

        :param request: the current request instance, handy for child classes
        :param names: the names this kwarg can be
        :param required: True if a name has to be found in kwargs
        :param default: the default value if name isn't found
        :param kwargs: the kwargs that will be used to find the value
        :returns: tuple, found_name, val where found_name is the actual name kwargs contained
        """
        val = default
        found_name = ''
        for name in names:
            if name in kwargs:
                val = kwargs[name]
                found_name = name
                break

        if not found_name and required:
            raise ValueError("required param {} does not exist".format(self.name))

        return found_name, val

    def normalize_kwarg(self, request, kwargs):
        flags = self.flags
        name = self.name

        try:
            pdefault = self.normalize_default(flags.get('default', None))
            prequired = flags['required']
            dest_name = flags.get('dest', name)

            has_val = True
            found_name, val = self.find_kwarg(request, self.names, prequired, pdefault, kwargs)
            if found_name:
                # we are going to replace found_name with dest_name
                kwargs.pop(found_name)
            else:
                # we still want to run a default value through normalization but if we
                # didn't find a value and don't have a default, don't set any value
                has_val = 'default' in flags

            if has_val:
                    kwargs[dest_name] = self.normalize_val(request, val)

        except ValueError as e:
            raise CallError(400, "{} failed with {}".format(name, e.message))

        return kwargs

    def normalize_val(self, request, val):
        """This will take the value and make sure it meets expectations

        :param request: the current request instance
        :param val: the raw value pulled from kwargs or args
        :returns: val that has met all param checks
        :raises: ValueError if val fails any checks
        """
        flags = self.flags
        paction = flags['action']
        ptype = flags['type']
        pchoices = flags.get('choices', None)
        allow_empty = flags.get('allow_empty', False)
        min_size = flags.get('min_size', None)
        max_size = flags.get('max_size', None)
        regex = flags.get('regex', None)

        if paction in set(['store_list']):
            if isinstance(val, list) and len(val) > 1:
                raise ValueError("too many values for param")

            if isinstance(val, basestring):
                val = val.split(',')

            else:
                val = list(val)

        elif paction in set(['append', 'append_list']):
            if not isinstance(val, list):
                val = [val]

            if paction == 'append_list':
                vs = []
                for v in val:
                    if isinstance(v, basestring):
                        vs.extend(v.split(','))
                    else:
                        vs.append(v)

                val = vs

        else:
            if paction not in set(['store', 'store_false', 'store_true']):
                raise RuntimeError('unknown param action {}'.format(paction))

        if ptype:
            if isinstance(val, list) and ptype != list:
                val = map(ptype, val)

            else:
                if isinstance(ptype, type):
                    if issubclass(ptype, bool):
                        if val in set(['true', 'True', '1']):
                            val = True
                        elif val in set(['false', 'False', '0']):
                            val = False
                        else:
                            val = ptype(val)

                    elif issubclass(ptype, str):
                        charset = request.charset
                        if charset and isinstance(val, unicode):
                            val = val.encode(charset)
                        else:
                            val = ptype(val)

                    else:
                        val = ptype(val)

                else:
                    val = ptype(val)

        if pchoices:
            if val not in pchoices:
                raise ValueError("param value {} not in choices {}".format(val, pchoices))

        # at some point this if statement is just going to be too ridiculous
        # FieldStorage check is because of this bug https://bugs.python.org/issue19097
        if not allow_empty and val is not False and not val and not isinstance(val, cgi.FieldStorage):
            if 'default' not in flags:
                raise ValueError("param was empty")

        if min_size is not None:
            failed = False
            if isinstance(val, (int, float)):
                if val < min_size: failed = True
            else:
                if len(val) < min_size: failed = True

            if failed:
                raise ValueError("param was smaller than {}".format(min_size))

        if max_size is not None:
            failed = False
            if isinstance(val, (int, float)):
                if val > max_size: failed = True
            else:
                if len(val) > max_size: failed = True

            if failed:
                raise ValueError("param was bigger than {}".format(max_size))

        if regex:
            failed = False
            if isinstance(regex, basestring):
                if not re.search(regex, val): failed = True
            else:
                if not regex.search(val): failed = True

            if failed:
                raise ValueError("param failed regex check")

        return val

    def __call__(slf, func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self, args, kwargs = slf.normalize_param(self, args, kwargs)
            return func(self, *args, **kwargs)
        return wrapper


class get_param(param):
    """same as param, but only checks GET params"""
    def find_kwarg(self, request, names, required, default, kwargs):
        try:
            return super(get_param, self).find_kwarg(
                request,
                names,
                required,
                default,
                request.query_kwargs
            )

        except ValueError:
            raise ValueError("required param {} was not present in GET params".format(self.name))


class post_param(param):
    """same as param but only checks POST params"""
    def find_kwarg(self, request, names, required, default, kwargs):
        try:
            return super(post_param, self).find_kwarg(
                request,
                names,
                required,
                default,
                request.body_kwargs
            )

        except ValueError:
            raise ValueError("required param {} was not present in POST params".format(self.name))


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

    def __call__(slf, func):
        param_options = slf.param_options
        req_param_names = slf.req_param_names
        not_empty = not param_options.pop('allow_empty', False)

        @wraps(func)
        def decorated(self, *args, **kwargs):
            for req_param_name in req_param_names:
                if req_param_name not in kwargs:
                    raise CallError(400, "required param {} was not present".format(req_param_name))

                if not_empty and not kwargs[req_param_name]:
                    raise CallError(400, "required param {} was empty".format(req_param_name))

            return func(self, *args, **kwargs)

        return decorated

