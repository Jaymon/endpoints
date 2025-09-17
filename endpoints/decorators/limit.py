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
    controller method
    """
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

    async def get_key(self, controller, method_args, method_kwargs) -> str:
        """Decide what key this request should have

        :example:
            # return ip.path
            return "{}.{}".format(request.ip, request.path)

        :param controller: Controller, the controller handling the request
        :returns: int, the desired ttl for the request
        """
        raise NotImplementedError()

    async def is_valid(self, controller, key, limit, ttl):
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


