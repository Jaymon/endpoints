# -*- coding: utf-8 -*-
import logging
import inspect
from typing import Callable

from datatypes.decorators import FuncDecorator

from ..compat import *
from ..exception import CallError


logger = logging.getLogger(__name__)


class ControllerDecorator(FuncDecorator):
    """Base decorator providing common functionality to run .handle() when a
    decorated function is called, this class is meant to be extended by a child

    This also is Controller specific, it's meant to be used in decorators that
    decorate Controller methods

    A controller decorator has a specific lifecycle:

        1. `.definition`
        2. `.get_params`
            a. `.get_decorator_params`
                1. `.handle_decorator_error` (optional)
            b. `.get_method_params`
                1. `.handle_method_error` (optional)
        3. `.handle_decorator`
            a. `.handle`
            b. `.handle_decorator_error` (optional)
        4. `.handle_method`
            a. calls controller method
            b. `.get_response_body`
            c. `.handle_decorator_error` (optional)
    """
    def decorate(self, method: Callable, *args, **kwargs) -> Callable:
        """decorate the passed in Callable calling target when func is called

        You should never override this method unless you know what you are
        doing

        :param method: callable, the controller method being decorated
        :param *args: these are the positional arguments passed into the
            decorator's __init__ method
        :param **kwargs: these are the named arguments passed into the
            decorator's __init__ method
        :returns: the decorated function that calls `method`
        """
        self.definition(*args, **kwargs)

        async def decorated(controller, *method_args, **method_kwargs):
            decorator_params, method_params = await self.get_params(
                controller,
                method_args,
                method_kwargs,
            )

            await self.handle_decorator(
                controller,
                decorator_params[0],
                decorator_params[1],
            )

            return await self.handle_method(
                method,
                controller,
                method_params[0],
                method_params[1],
            )

        return decorated

    def definition(self, *args, **kwargs):
        """whatever is passed into the decorator creation will be passed to
        this method, so you can set instance variables and stuff

        This can be overridden by child classes but this cannot be made async
        and it should avoid doing any IO because of that

        :example:
            a decorator like:

                @foo("bar", "che", baz=1)
                def function_name(*args, **kwargs): pass

            would be passed to this method as:

                definition(*("bar", "che"), **{"baz": 1})

        :param *args: these are the positional arguments passed into the
            decorator __init__ method
        :param **kwargs: these are the named arguments passed into the
            decorator __init__ method
        """
        self.definition_args = args
        self.definition_kwargs = kwargs

    async def get_params(
        self,
        controller,
        method_args,
        method_kwargs,
    ) -> tuple[tuple[Iterable, Mapping], tuple[Iterable, Mapping]]:
        """Get the params that will be passed to `.handle` and the params
        that will be passed to the wrapped method

        :returns: a tuple of tuples, the first tuple are the args and kwargs
            for the `.handle` method, the second tuple are the args and kwargs
            for the wrapped `method`
        """
        try:
            decorator_params = await self.get_decorator_params(
                controller,
                method_args,
                method_kwargs,
            )

        except Exception as e:
            await self.handle_decorator_error(controller, e)

        try:
            method_params = await self.get_method_params(
                controller,
                method_args,
                method_kwargs,
            )

        except Exception as e:
            await self.handle_method_error(controller, e)

        return decorator_params, method_params

    async def get_decorator_params(
        self,
        controller,
        method_args,
        method_kwargs,
    ) -> tuple[Iterable, Mapping]:
        """Returns the args and kwargs that will be passed into the `.handle`
        method

        if this raises an error it will be passed to `.handle_decorator_error`

        :param controller: Controller, the controller instance
        :param method_args: the positional arguments that will
            be passed to `.handle`
        :param method_kwargs: the keyword arguments that will be
            passed to `.handle`
        :returns: this will be passed to `.handle` as `*args` and `**kwargs`
        """
        return [controller, *method_args], method_kwargs

    async def get_method_params(
        self,
        controller,
        method_args,
        method_kwargs,
    ) -> tuple[Iterable, Mapping]:
        """This is called before the wrapped controller method is called, this
        is for decorators that want to normalize the controller method params
        in some way

        This is roughly analogous to `Controller.get_method_params

        if this raises an error it will be passed to `.handle_method_error`

        :param controller: Controller, the controller instance whose method is
            going to be called
        :param method_args: the positional controller method
            arguments that were passed in
        :param method_kwargs: the keyword controller method
            arguments that were passed in
        :returns: index 0 will be passed to the controller
            method as `*args`, index 1 will be passed as `**kwargs`
        """
        return method_args, method_kwargs

    async def handle_decorator(
        self,
        controller,
        decorator_args,
        decorator_kwargs
    ):
        """Internal method for calling `.handle` and handling any error
        with `.handle_decorator_error`"""
        try:
            ret = self.handle(*decorator_args, **decorator_kwargs)
            while inspect.iscoroutine(ret):
                ret = await ret

            if ret is not None and not ret:
                raise ValueError(
                    "{} check failed".format(self.__class__.__name__)
                )

        except Exception as e:
            await self.handle_decorator_error(controller, e)

    async def handle(self, *args, **kwargs) -> bool|None:
        """The meat of the decorator, this is usually where child functionality
        will go, this is meant to be extended in decorators that want to check
        something and interrupt the request if some condition fails

        if this raises an error it will be passed to `.handle_decorator_error`

        :param *args: the Iterable returned from `.get_decorator_params`
        :param **kwargs: the Mapping returned from `.get_decorator_params`
        :returns: bool, if this method returns False then it will cause a
            ValueError to be raised signalling the input failed this decorator,
            if this returns None then it's return value is ignored
        """
        return True

    async def handle_method(
        self,
        method: Callable,
        controller,
        method_args: Iterable,
        method_kwargs: Mapping,
    ):
        """Internal method that handles actually runnning the controller
        function and returns whatever the function returned

        :param method: the controller method
        :param controller: Controller, the controller instance
        :param method_args: the positional arguments that will
            be passed to `method` as returned by `.get_method_params`
        :param method_kwargs: the keyword arguments that will be
            passed to `method` as returned by `.get_method_params`
        :returns: Any, whatever the func returns
        """
        try:
            body = method(controller, *method_args, **method_kwargs)
            while inspect.iscoroutine(body):
                body = await body

            body = await self.get_response_body(controller, body)

        except Exception as e:
            await self.handle_method_error(controller, e)

        return body

    async def get_response_body(self, controller, body):
        """This is called right after the controller method is called, this is
        for decorators that want to normalize the controller method return
        value in some way

        This is roughly analogous to `Controller.get_response_body`

        if this raises an error it will be passed to `.handle_method_error`

        :param controller: Controller, the controller instance whose method was
            just called
        :param body: Any, whatever the controller method returned
        :returns: Any, if None is returned then no changes to the controller's 
            response will be made
        """
        return body

    async def handle_decorator_error(self, controller, e):
        """Handles any error raised by `.handle` or `.get_decorator_params`"""
        raise e

    async def handle_method_error(self, controller, e):
        """Handles any error raised by `.handle_method`,
        `.get_method_params`, or `.get_response_body`"""
        raise e

