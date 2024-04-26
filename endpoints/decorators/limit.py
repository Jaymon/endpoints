# -*- coding: utf-8 -*-
import logging

from datatypes import Pool, Datetime

from ..compat import *
from ..exception import CallError
from ..utils import String
from .base import BackendDecorator


logger = logging.getLogger(__name__)


class RateLimitBackend(object):
    """You can extend this backend and override the .handle() method to
    customize rate limiting in your application

    you can of course create your own Backend and just set it on the base limit
    decorator to use that backend for all your limiting

    :example:
        from endpoints.decorators.limit import (
            RateLimitDecorator,
            RateLimitBackend,
        )

        class MyBackend(RateLimitBackend):
            def handle(self, controller, key, limit, ttl):
                # access database or something here, return boolean

        RateLimitDecorator.backend_class = MyBackend
        # now all rate limiting will use MyBackend
    """
    async def handle(self, controller, key, limit, ttl):
        raise NotImplementedError()


class Backend(RateLimitBackend):
    """This is the default backend the limit decorators use, it just uses an in
    memory class dictionary to hold values, while this does work, it is more
    for demonstration purposes since it tracks keys in memory and per
    process"""

    _calls = Pool(5000)
    """class dictionary that will hold all limiting keys"""

    async def handle(self, controller, key, limit, ttl):
        now = Datetime()
        count = 1

        calls = type(self)._calls

        if key in calls:
            count = calls[key]["count"] + 1
            if count > limit:
                td = now - calls[key]["date"]
                if td.total_seconds() < ttl:
                    raise ValueError(
                        "Please wait {} seconds to make another request".format(
                            ttl - td.seconds
                        )
                    )

                else:
                    count = 1 # we are starting over

        calls[key] = {
            "count": count,
            "date": now,
        }

        return True


class RateLimitDecorator(BackendDecorator):
    """Base decorator providing common functionality to rate limit a given
    controller method
    """
    backend_class = Backend

    def definition(self, limit=0, ttl=0, path_in_key=True, *args, **kwargs):
        """The definition of the decorator, this is called from the decorator's
        __init__ method and is responsible for validating the passed in
        arguments for the decorator

        :param limit: int, max requests that can be received in ttl
        :param ttl: int, how many seconds the request should be throttled
            (eg, 3600 = 1 hour)
        :param path_in_key: bool, True if you would like to include the request
            path in the key, if False then the path will not be included so the
            paths will be more global
        """
        self.limit = int(limit)
        self.ttl = int(ttl)
        self.path_in_key = path_in_key

        super().definition(*args, **kwargs)

    async def normalize_key(self, controller, **kwargs):
        """Decide what key this request should have

        :example:
            # return ip.path
            return "{}.{}".format(request.ip, request.path)

        :param controller: Controller, the controller handling the request
        :returns: int, the desired ttl for the request
        """
        raise NotImplementedError()

    async def handle_kwargs(self, controller, **kwargs):
        """These arguments will be passed to the .handle() method"""
        key = await self.normalize_key(
            controller,
            **kwargs
        )

        return {
            "controller": controller,
            "key": key,
            "limit": self.limit,
            "ttl": self.ttl,
        }

    async def handle(self, controller, key, limit, ttl):
        """this will only run the request if the key has a value, if you want
        to fail if the key doesn't have a value, then normalize_key() should
        raise an exception

        :param request: Request, the request instance
        :param key: string, the unique key for the endpoint, this is generated
            using self.normalize_key, so override that method to customize the
            key
        :param limit: int, max requests can be received in ttl
        :param ttl: int, how many seconds the request should be throttled
            (eg, 3600 = 1 hour)
        """
        ret = True
        if key:
            ret = await super().handle(controller, key, limit, ttl)

        else:
            logger.warning(
                "No ratelimit key found for {}".format(
                    controller.request.path
                )
            )

        return ret

    async def handle_handle_error(self, controller, e):
        """all exceptions should generate 429 responses"""
        if isinstance(e, CallError):
            await super().handle_error(controller, e)

        else:
            raise CallError(429, String(e)) from e


class ratelimit_ip(RateLimitDecorator):
    """Rate limit by the client's ip address"""
    async def normalize_key(self, controller, **kwargs):
        request = controller.request
        if self.path_in_key:
            ret = "{}{}".format(request.ip, request.path)
        else:
            ret = request.ip
        return ret


class ratelimit_access_token(RateLimitDecorator):
    """Limit by the requested client's access token, because certain endpoints
    can only be requested a certain amount of times for the given access token
    """
    async def normalize_key(self, controller, **kwargs):
        access_token = controller.get_access_token(
            *kwargs["controller_args"],
            **kwargs["controller_kwargs"]
        )

        if self.path_in_key:
            ret = "{}{}".format(access_token, controller.request.path)

        else:
            ret = access_token

        return ret


class ratelimit_param(RateLimitDecorator):
    """this will limit on a parameter value. So, for example, if you want to
    limit login attempts for an email address you would pass in "email" to this
    decorator
    """
    async def normalize_key(self, controller, **kwargs):
        try:
            if self.path_in_key:
                ret = "{}{}".format(
                    kwargs["controller_kwargs"][self.param_name],
                    controller.request.path
                )

            else:
                ret = String(kwargs["controller_kwargs"][self.param_name])

        except KeyError:
            ret = ""

        return ret

    def definition(self, param_name, *args, **kwargs):
        self.param_name = param_name
        return super().definition(*args, **kwargs)


class ratelimit_param_ip(ratelimit_param):
    """this is a combination of the limit_param and limit_ip decorators, it
    will allow the param N times on the given unique ip
    """
    async def normalize_key(self, controller, **kwargs):
        request = controller.request
        try:
            if self.path_in_key:
                ret = "{}.{}{}".format(
                    kwargs["controller_kwargs"][self.param_name],
                    request.ip,
                    request.path
                )

            else:
                ret = "{}.{}".format(
                    kwargs["controller_kwargs"][self.param_name],
                    request.ip
                )

        except KeyError:
            ret = ""

        return ret

