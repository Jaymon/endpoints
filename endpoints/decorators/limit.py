# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import datetime

from datatypes import Pool

from ..compat import *
from ..exception import CallError, AccessDenied
from ..utils import String
from .base import BackendDecorator


logger = logging.getLogger(__name__)


class RateLimitBackend(object):
    """You can extend this backend and override the .handle() method to customize
    rate limiting in your application

    you can of course create your own Backend and just set it on the base limit
    decorator to use that backend for all your limiting

    :example:
        from endpoints.decorators.limit import RateLimitDecorator, RateLimitBackend

        class MyBackend(RateLimitBackend):
            def handle(self, request, key, limit, ttl):
                # access database or something here, return boolean

        RateLimitDecorator.backend_class = MyBackend
        # now all rate limiting will use MyBackend
    """
    DEFAULT_LIMIT = 0
    DEFAULT_TTL = 0

    def handle(self, request, key, limit, ttl):
        raise NotImplementedError()


class Backend(RateLimitBackend):
    """This is the default backend the limit decorators use, it just uses an in
    memory class dictionary to hold values, while this does work, it is more for
    demonstration purposes since it tracks keys in memory and per process"""

    _calls = Pool(5000)
    """class dictionary that will hold all limiting keys"""

    def handle(self, request, key, limit, ttl):
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

    def handle_args(self, controller, controller_args, controller_kwargs):
        """These arguments will be passed to the .handle() method"""
        request = controller.request

        key = self.normalize_key(
            request,
            controller_args=controller_args,
            controller_kwargs=controller_kwargs,
        )

        limit = self.normalize_limit(
            request,
            controller_args=controller_args,
            controller_kwargs=controller_kwargs,
        )

        ttl = self.normalize_ttl(
            request,
            controller_args=controller_args,
            controller_kwargs=controller_kwargs,
        )

        return request, key, limit, ttl

    def handle(self, request, key, limit, ttl):
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
            ret = super(RateLimitDecorator, self).handle(request, key, limit, ttl)
        else:
            logger.warn("No ratelimit key found for {}".format(request.path))

        return ret

    def handle_error(self, controller, e):
        """all exceptions should generate 429 responses"""
        raise CallError(429, String(e))

    def definition(self, limit=0, ttl=0, path_in_key=True, *args, **kwargs):
        """The definition of the decorator, this is called from the decorator's __init__
        method and is responsible for validating the passed in arguments for the decorator

        :param limit: int, max requests that should be received in ttl
        :param ttl: int, how many seconds the request should be throttled (eg, 3600 = 1 hour)
        :param path_in_key: bool, True if you would like to include the request path
            in the key, if False then the path will not be included so the paths
            will be more global
        """
        super(RateLimitDecorator, self).definition(*args, **kwargs)

        self.limit = int(limit) or getattr(self.backend, "DEFAULT_LIMIT", 0) 
        self.ttl = int(ttl) or getattr(self.backend, "DEFAULT_TTL", 0)
        self.path_in_key = path_in_key


class ratelimit_ip(RateLimitDecorator):
    """Rate limit by the client's ip address"""
    def normalize_key(self, request, *args, **kwargs):
        if self.path_in_key:
            ret = "{}{}".format(request.ip, request.path)
        else:
            ret = request.ip
        return ret


class ratelimit_access_token(RateLimitDecorator):
    """Limit by the requested client's access token, because certain endpoints can
    only be requested a certain amount of times for the given access token"""
    def normalize_key(self, request, *args, **kwargs):
        if self.path_in_key:
            ret = "{}{}".format(request.access_token, request.path)
        else:
            ret = request.access_token
        return ret


class ratelimit_param(RateLimitDecorator):
    """this will limit on a parameter value. So, for example, if you want to limit
    login attempts for an email address you would pass in "email" to this decorator"""
    def normalize_key(self, request, controller_args, controller_kwargs):
        try:
            if self.path_in_key:
                ret = "{}{}".format(controller_kwargs[self.param_name], request.path)
            else:
                ret = String(controller_kwargs[self.param_name])
        except KeyError:
            ret = ""
        return ret

    def definition(self, param_name, *args, **kwargs):
        self.param_name = param_name
        return super(ratelimit_param, self).definition(*args, **kwargs)


class ratelimit_param_ip(ratelimit_param):
    """this is a combination of the limit_param and limit_ip decorators, it will allow
    the param N times on the given unique ip"""
    def normalize_key(self, request, controller_args, controller_kwargs):
        try:
            if self.path_in_key:
                ret = "{}.{}{}".format(controller_kwargs[self.param_name], request.ip, request.path)
            else:
                ret = "{}.{}".format(controller_kwargs[self.param_name], request.ip)
        except KeyError:
            ret = ""
        return ret


