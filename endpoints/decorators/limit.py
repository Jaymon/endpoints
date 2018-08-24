# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import datetime

from ..exception import CallError, AccessDenied
from ..utils import String
from .base import TargetDecorator, BackendDecorator


logger = logging.getLogger(__name__)


class Backend(object):
    """This is the default backend the limit decorators use, it just uses an in
    memory class dictionary to hold values, while this does work, it is more for
    demonstration purposes and light loads as the _calls dictionary is never cleaned
    out and so it could in theory just grow forever until it uses all the memory
    and the server crashes

    you can of course create your own Backend and just set it on the base limit
    decorator to use that backend for all your limiting

    :example:
        from endpoints.decorators.limit import RateLimitDecorator

        class MyBackend(object):
            def target(self, request, key, limit, ttl):
                # access redis or something here, return boolean

        RateLimitDecorator.backend_class = MyBackend
        # now all rate limiting will use MyBackend
    """

    _calls = {}
    """class dictionary that will hold all limiting keys"""

    def target(self, request, key, limit, ttl):
        now = datetime.datetime.utcnow()
        count = 1

        calls = type(self)._calls

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

        return True


class RateLimitDecorator(BackendDecorator):
    """Base decorator providing common functionality to rate limit a given controller
    method
    """
    backend_class = Backend

    def normalize_key(self, request, *args, **kwargs):
        """Decide what key this request should have

        :example:
            # return ip.path
            return "{}.{}".format(request.ip, request.path)

        :param request: Request, the request instance
        :returns: int, the desired ttl for the request
        """
        raise NotImplementedError()

    def normalize_limit(self, request, *args, **kwargs):
        """Called with each request, if you would like to customize limit depending
        on the request, this is the method to override

        :param request: Request, the request instance
        :returns: int, the desired limit for the request
        """
        return self.limit

    def normalize_ttl(self, request, *args, **kwargs):
        """Called with each request, if you would like to customize ttl depending
        on the request, this is the method to override

        :param request: Request, the request instance
        :returns: int, the desired ttl for the request
        """
        return self.ttl

    def normalize_target_params(self, request, controller_args, controller_kwargs):
        kwargs = {
            "request": request,
            "key": self.normalize_key(
                request,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs,
            ),
            "limit": self.normalize_limit(
                request,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs,
            ),
            "ttl": self.normalize_ttl(
                request,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs,
            ),
        }
        return [], kwargs

    def target(self, request, key, limit, ttl):
        """this will only run the request if the key has a value, if you want to
        fail if the key doesn't have a value, then normalize_key() should raise
        an exception

        :param request: Request, the request instance
        :param key: string, the unique key for the endpoint, this is generated using
            self.normalize_key, so override that method to customize the key
        :param limit: int, max requests that should be received in ttl
        :param ttl: int, how many seconds the request should be throttled (eg, 3600 = 1 hour)
        """
        ret = True
        if key:
            #backend = self.create_backend()
            #method = getattr(backend, "normalize_limit", None)
            #if method:
            #    limit = method(request, limit)
            #method = getattr(backend, "normalize_ttl", None)
            #if method:
            #    ttl = method(request, ttl)
            #ret = backend.target(request, key, limit, ttl)
            ret = super(RateLimitDecorator, self).target(request, key, limit, ttl)
        else:
            logger.warn("No ratelimit key found for {}".format(request.path))

        return ret

    def handle_error(self, e):
        """all exceptions should generate 429 responses"""
        raise CallError(429, String(e))

    def decorate(self, func, limit=0, ttl=0, *anoop, **kwnoop):
        """see target for an explanation of limit and ttl"""
        self.limit = int(limit)
        self.ttl = int(ttl)
        return super(RateLimitDecorator, self).decorate(func, target=None, *anoop, **kwnoop)


class ratelimit_ip(RateLimitDecorator):
    """Rate limit by the client's ip address"""
    def normalize_key(self, request, *args, **kwargs):
        return "{}{}".format(request.ip, request.path)


class ratelimit(ratelimit_ip):
    """Rate limit a certain endpoint

    :example:
        from endpoints import Controller
        from endpoints.decorators import ratelimit

        class Default(Controller):
            @ratelimit(10, 3600) # you can make 10 requests per hour
            def GET(self):
                return "hello world"

    .. seealso:: RateLimitDecorator
    """
    def decorate(self, func, limit, ttl, *anoop, **kwnoop):
        """make limit and ttl required"""
        return super(ratelimit, self).decorate(func, limit, ttl, *anoop, **kwnoop)


class ratelimit_token(RateLimitDecorator):
    """Limit by the requested client's access token, because certain endpoints can
    only be requested a certain amount of times for the given access token"""
    def normalize_key(self, request, *args, **kwargs):
        return "{}{}".format(request.access_token, request.path)


class ratelimit_param(RateLimitDecorator):
    """this will limit on a parameter value. So, for example, if you want to limit
    login attempts for an email address you would pass in "email" to this decorator"""
    def normalize_key(self, request, controller_args, controller_kwargs):
        try:
            ret = "{}{}".format(controller_kwargs[self.param_name], request.path)
        except KeyError:
            ret = ""
        return ret

    def decorate(self, func, param_name, *args, **kwargs):
        self.param_name = param_name
        return super(ratelimit_param, self).decorate(func, *args, **kwargs)


class ratelimit_param_ip(ratelimit_param):
    """this is a combination of the limit_param and limit_ip decorators, it will allow
    the param N times on the given unique ip"""
    def normalize_key(self, request, controller_args, controller_kwargs):
        try:
            ret = "{}.{}{}".format(controller_kwargs[self.param_name], request.ip, request.path)
        except KeyError:
            ret = ""
        return ret


class ratelimit_param_only(ratelimit_param):
    """Just uses given parameter as rate-limiter. Does not use IP or path."""
    def normalize_key(self, request, controller_args, controller_kwargs):
        try:
            ret = str(controller_kwargs[self.param_name])
        except KeyError:
            ret = ""
        return ret

