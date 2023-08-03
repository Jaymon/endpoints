# -*- coding: utf-8 -*-
import logging
import asyncio

from datatypes.decorators import FuncDecorator

from ..compat import *
from ..exception import CallError


logger = logging.getLogger(__name__)


class ControllerDecorator(FuncDecorator):
    """Base decorator providing common functionality to run .handle() when a
    decorated function is called, this class is meant to be extended by a child

    This also is Controller specific, it's meant to be used in decorators that
    decorate Controller methods

    .. seealso:: decorators.auth
    """
    def decorate(self, func, *args, **kwargs):
        """decorate the passed in func calling target when func is called

        You should never override this method unless you know what you are doing

        :param func: callable, the function being decorated
        :param *args: these are the positional arguments passed into the
            decorator __init__ method
        :param **kwargs: these are the named arguments passed into the decorator
            __init__ method
        :returns: the decorated func
        """
        self.definition(*args, **kwargs)

        async def decorated(controller, *controller_args, **controller_kwargs):
            await self.handle_call(
                controller,
                controller_args,
                controller_kwargs
            )

            return await self.handle_controller(
                func,
                controller,
                controller_args,
                controller_kwargs,
            )

        return decorated

    def definition(self, *args, **kwargs):
        """whatever is passed into the decorator creation will be passed to this
        method, so you can set instance variables and stuff

        This can be overridden by child classes but this cannot be made async
        and it should avoid doing any IO because of that

        :Example:
            a decorator like:
                @foo("bar", "che", baz=1)
                def function_name(*args, **kwargs): pass

            would be passed to this method as:

                definition(*("bar", "che"), **{"baz": 1})


        :param *args: these are the positional arguments passed into the
            decorator __init__ method
        :param **kwargs: these are the named arguments passed into the decorator
            __init__ method
        """
        self.decorator_args = args
        self.decorator_kwargs = kwargs

    async def handle_kwargs(self, controller, controller_args, controller_kwargs):
        """Returns the **kwargs part that will be passed into the .handle() method

        this is called from .handle_params()
        """
        return {
            "controller": controller,
            "controller_args": controller_args,
            "controller_kwargs": controller_kwargs,
        }

    async def handle_error(self, controller, e):
        """Any error the class isn't sure how to categorize will go through this
        method

        overriding this method allows child classes to customize responses based
        on certain encountered errors

        :param controller: the controller instance that contains the method that
            raised e
        :param e: the raised error
        """
        if not isinstance(e, CallError):
            logger.warning(e)

        raise e

    async def handle_controller(self, func, controller, controller_args, controller_kwargs):
        ret = func(controller, *controller_args, **controller_kwargs)
        while asyncio.iscoroutine(ret):
            ret = await ret

        return ret

    async def handle_call(self, controller, controller_args, controller_kwargs):
        """Internal method for this class

        handles normalizing the passed in values from the decorator using
        .handle_params() and then passes them to .handle()
        """
        try:
            handle_kwargs = await self.handle_kwargs(
                controller=controller,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs
            )

            ret = self.handle(**handle_kwargs)
            while asyncio.iscoroutine(ret):
                ret = await ret

            if ret is not None and not ret:
                raise ValueError(
                    "{} check failed".format(self.__class__.__name__)
                )

        except Exception as e:
            await self.handle_error(controller, e)

    async def handle(self, *args, **kwargs):
        """The meat of the decorator, this is where all the functionality should
        go in the child class, this is meant to be extended

        if this raises an error it will be passed to .handle_error()

        :param **kwargs: dict, whatever returned from .normalize_handle_kwargs()
        :returns: bool, if this method returns False then it will cause a
            ValueError to be raised signalling the input failed this decorator
        """
        return True


class BackendDecorator(ControllerDecorator):

    backend_class = None

    async def get_backend(self, *args, **kwargs):
        backend = getattr(self, "backend", None)
        if backend is None:
            self.backend = backend = await self.create_backend(*args, **kwargs)

        return backend

    async def create_backend(self, *args, **kwargs):
        backend = kwargs.pop("backend", None)

        if not backend:
            backend_class = kwargs.pop("backend_class", self.backend_class)

            if not backend_class:
                raise ValueError(
                    "You are using a BackendDecorator with no backend class"
                )

            backend = backend_class(*args, **kwargs)

        return backend

    async def handle(self, *args, **kwargs):
        backend = await self.get_backend(
            *self.decorator_args,
            **self.decorator_kwargs,
        )
        return backend.handle(*args, **kwargs)

