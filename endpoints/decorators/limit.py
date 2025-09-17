# -*- coding: utf-8 -*-
import logging

from datatypes import Pool, Datetime

from ..compat import *
from ..exception import CallError
from ..utils import String
from .base import ControllerDecorator


logger = logging.getLogger(__name__)


class RateLimitDecorator(ControllerDecorator):
    """Base decorator providing common functionality to rate limit a given
    controller method.

    Child decorators should override `.get_key` and/or `.is_valid` to provide
    custom functionality
    """
    def definition(self, limit=0, ttl=0, *args, **kwargs):
        """The definition of the decorator, this is called from the decorator's
        __init__ method and is responsible for validating the passed in
        arguments for the decorator

        :param limit: int, max requests that can be received in ttl
        :param ttl: int, how many seconds the request should be throttled
            (eg, 3600 = 1 hour)
        """
        self.limit = int(limit)
        self.ttl = int(ttl)

        super().definition(*args, **kwargs)

    async def get_key(self, controller, method_args, method_kwargs) -> str:
        """Decide what key this request should have to decide about rate
        limiting

        :param controller: Controller, the controller handling the request
        :param method_args: the positionals that will be passed to the
            wrapped controller method
        :param method_kwargs: the keywords that will be passed to the
            wrapped controller method
        :returns: the desired key
        """
        raise NotImplementedError()

    async def is_valid(self, controller, key, limit, ttl) -> bool:
        """This returns True if the request is valid, False if the request
        isn't valid, any errors raised are also considered failures"""
        now = Datetime()
        count = 1

        calls = getattr(type(self), "_calls", None)
        if calls is None:
            calls = Pool(5000)
            type(self)._calls = calls

        if key in calls:
            count = calls[key]["count"] + 1
            if count > limit:
                td = now - calls[key]["date"]
                if td.total_seconds() < ttl:
                    raise ValueError(
                        "Please wait {} seconds to make a request".format(
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

    async def get_decorator_params(
        self,
        controller,
        method_args,
        method_kwargs
    ) -> tuple[Iterable, Mapping]:
        """These arguments will be passed to the .handle() method"""
        key = await self.get_key(
            controller,
            method_args,
            method_kwargs
        )

        return [], {
            "controller": controller,
            "key": key,
            "limit": self.limit,
            "ttl": self.ttl,
        }

    async def handle(self, controller, key, limit, ttl):
        """this will only run the request if the key has a value, if you want
        to fail if the key doesn't have a value, then `.get_key` should
        raise an exception

        :param key: string, the unique key for the endpoint, this is generated
            using `.get_key`, so override that method to customize the
            key
        :param limit: int, max requests can be received in ttl
        :param ttl: int, how many seconds the request should be throttled
            (eg, 3600 = 1 hour)
        """
        ret = True
        if key:
            ret = await self.is_valid(controller, key, limit, ttl)

        else:
            logger.warning(
                "No ratelimit key found for {}".format(
                    controller.request.path
                )
            )

        return ret

    async def handle_decorator_error(self, controller, e):
        """all exceptions should generate 429 responses"""
        if isinstance(e, CallError):
            await super().handle_error(controller, e)

        else:
            raise CallError(429, String(e)) from e


