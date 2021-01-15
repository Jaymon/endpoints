# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import types
import re
import cgi
from functools import wraps
import logging

from decorators import FuncDecorator, property

from ..compat import *
from ..exception import CallError


logger = logging.getLogger(__name__)


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

    https://devcenter.heroku.com/articles/increasing-application-performance-with-http-cache-headers#cache-prevention
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


class param(FuncDecorator):
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
            raise CallError(400, "Positional arg {} failed with {}".format(index, String(e)))

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
            raise CallError(400, "{} failed with {}".format(name, String(e)))

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
                val = list(val.split(','))

            else:
                val = list(val)

        elif paction in set(['append', 'append_list']):
            if not isinstance(val, list):
                val = [val]

            if paction == 'append_list':
                vs = []
                for v in val:
                    if isinstance(v, basestring):
                        vs.extend(String(v).split(','))
                    else:
                        vs.append(v)

                val = vs

        else:
            if paction not in set(['store', 'store_false', 'store_true']):
                raise RuntimeError('unknown param action {}'.format(paction))

        if regex:
            failed = False
            if isinstance(regex, basestring):
                if not re.search(regex, val): failed = True
            else:
                if not regex.search(val): failed = True

            if failed:
                raise ValueError("param failed regex check")

        if ptype:
            if isinstance(val, list) and ptype != list:
                val = list(map(ptype, val))

            else:
                if isinstance(ptype, type):
                    if issubclass(ptype, bool):
                        if val in set(['true', 'True', '1']):
                            val = True
                        elif val in set(['false', 'False', '0']):
                            val = False
                        else:
                            val = ptype(val)

                    elif issubclass(ptype, basestring):
                        charset = request.encoding
                        val = String(val, charset)

                    elif issubclass(ptype, (bytes, bytearray)):
                        charset = request.encoding
                        val = ptype(ByteString(val, charset))

                    #elif issubclass(ptype, str):
                    #    charset = request.encoding
                    #    if is_py2:
                    #        val = ptype(ByteString(val, charset))
                    #    else:
                    #        val = ptype(String(val, charset))*/

                    else:
                        val = ptype(val)

                else:
                    val = ptype(val)

        if pchoices:
            if isinstance(val, list) and ptype != list:
                for v in val:
                    if v not in pchoices:
                        raise ValueError("param value {} not in choices {}".format(v, pchoices))

            else:
                if val not in pchoices:
                    raise ValueError("param value {} not in choices {}".format(val, pchoices))

        # at some point this if statement is just going to be too ridiculous
        # FieldStorage check is because of this bug https://bugs.python.org/issue19097
        if not isinstance(val, cgi.FieldStorage):
            if not allow_empty and val is not False and not val:
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

        return val

    def decorate(slf, func, *names, **flags):
        slf.normalize_type(names)
        slf.normalize_flags(flags)

        def decorated(self, *args, **kwargs):
            self, args, kwargs = slf.normalize_param(self, args, kwargs)
            return func(self, *args, **kwargs)
        return decorated


class param_query(param):
    """same as param, but only checks GET params"""
    def find_kwarg(self, request, names, required, default, kwargs):
        try:
            return super(param_query, self).find_kwarg(
                request,
                names,
                required,
                default,
                request.query_kwargs
            )

        except ValueError:
            raise ValueError("required param {} was not present in GET params".format(self.name))


class param_body(param):
    """same as param but only checks POST params"""
    def find_kwarg(self, request, names, required, default, kwargs):
        try:
            return super(param_body, self).find_kwarg(
                request,
                names,
                required,
                default,
                request.body_kwargs
            )

        except ValueError:
            raise ValueError("required param {} was not present in POST params".format(self.name))


class code_error(FuncDecorator):
    """
    When placed on HTTPMETHOD methods (eg, GET) this will allow you to easily map
    raised exceptions to http status codes

    :example:
        class Foo(Controller):
            @code_error(406, AttributeError, IndexError)
            def GET(self): raise AttributeError()

    :param code: integer, an http status code
        https://en.wikipedia.org/wiki/List_of_HTTP_status_codes
    :param **exc_classes: tuple, one or more exception classes that will be checked
        against the raised error
    """
    def decorate(self, func, code, *exc_classes):
        def decorated(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)

            except exc_classes as e:
                raise CallError(code, e)

        return decorated


