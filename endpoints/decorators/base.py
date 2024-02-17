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

    A controller decorator has a specific lifecycle:

        1. .definition() is called with any arguments that were passed in when
            the decorator is first created, by default, the instance properties
            .decorator_args and .decorator_kwargs will be set
        2. .handle_kwargs() is called when a Controller method that is wrapped
            by the decorator is called. This method should return any arguments
            that will be passed to .handle() as **kwargs. You would override
            this method if you wanted your child decorator to have a custom
            .handle() definition
        3. .handle() is called with the return value of .handle_kwargs(). If
            this method returns False then .handle_error() will be called. If
            this method returns True or None then the wrapped controller method
            will be called
        4. .handle_request() is called with the controller instance and the 
            args (as a list) and kwargs (as a dict). It should return a
            tuple[list, dict] where index 0 represents that *args that will be
            passed to wrapped method and index 1 represents the **kwargs that
            will be passed to the wrapped method
        5. .handle_response() is called with the controller instance and the
            response from whatever controller method was called
    """
    def get_wrapped_method(self, func):
        wrapped = getattr(func, "__wrapped__", None)
        if wrapped:
            func = self.get_wrapped_method(wrapped)

        return func

    def is_wrapped_method(self, func):
        wrapped = getattr(func, "__wrapped__", None)
        return True if wrapped else False

    def decorate(self, func, *args, **kwargs):
        """decorate the passed in func calling target when func is called

        You should never override this method unless you know what you are doing

        :param func: callable, the controller method being decorated
        :param *args: these are the positional arguments passed into the
            decorator __init__ method
        :param **kwargs: these are the named arguments passed into the decorator
            __init__ method
        :returns: the decorated func
        """
        self.definition(*args, **kwargs)

        async def decorated(controller, *controller_args, **controller_kwargs):

            # handle the decorator's .handle_kwargs() and .handle() calls, this
            # isn't wrapped in try/catch because .handle_call takes care of that
            await self.handle_call(
                controller,
                controller_args,
                controller_kwargs
            )

            # prepare the controller request, this is wrapped in try/catch
            # because .handle_request is meant to be extended by child classes
            try:
                crequest = await self.handle_request(
                    controller,
                    controller_args,
                    controller_kwargs
                )

                if crequest is not None:
                    controller_args = crequest[0]
                    controller_kwargs = crequest[1]

            except Exception as e:
                return await self.handle_error(controller, e)

            # actually call the controller, this calls the controller method
            # and handles any errors, that's why it isn't wrapped in try/catch
            controller_response = await self.handle_controller(
                func,
                controller,
                controller_args,
                controller_kwargs,
            )

            # make any changes to the controller's response before returning,
            # this is wrapped in try/catch because .handle_response is meant
            # to be extended by child classes
            try:
                cresponse = await self.handle_response(
                    controller,
                    controller_response,
                )

                if cresponse is not None:
                    controller_response = cresponse

                return controller_response

            except Exception as e:
                return await self.handle_error(controller, e)

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
        """Returns the **kwargs part that will be passed into the .handle()
        method

        :param controller: Controller, the controller instance
        :param controller_args: list|tuple, the positional arguments that will
            be passed to func
        :param controller_kwargs: dict, the keyword arguments that will be
            passed to func
        :returns: dict, this will be passed to .handle() as **kwargs
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
        """Internal method that handles actually runnning the controller
        function and returns whatever the function returned

        :param func: callable, the controller method
        :param controller: Controller, the controller instance
        :param controller_args: list|tuple, the positional arguments that will
            be passed to func
        :param controller_kwargs: dict, the keyword arguments that will be
            passed to func
        :returns: Any, whatever the func returns
        """
        try:
            controller_response = func(
                controller,
                *controller_args,
                **controller_kwargs
            )
            while asyncio.iscoroutine(controller_response):
                controller_response = await controller_response

            return controller_response

        except Exception as e:
            return await self.handle_error(controller, e)

    async def handle_call(self, controller, controller_args, controller_kwargs):
        """Internal method for this class, this handles calling .handle_kwargs()
        and .handle() for this decorator

        handles normalizing the passed in values from the decorator using
        .handle_kwargs() and then passes them to .handle()
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
            return await self.handle_error(controller, e)

    async def handle(self, *args, **kwargs):
        """The meat of the decorator, this is where all the functionality should
        go in the child class, this is meant to be extended in decorators that
        want to check something and interrupt the request if some condition
        fails

        if this raises an error it will be passed to .handle_error()

        :param **kwargs: dict, whatever returned from .normalize_handle_kwargs()
        :returns: bool, if this method returns False then it will cause a
            ValueError to be raised signalling the input failed this decorator,
            if this returns None then it's return value is ignored
        """
        return True

    async def handle_request(self, controller, controller_args, controller_kwargs):
        """This is called right before the controller method is called, this is
        for decorators that want to normalize the controller method request in
        some way

        if this raises an error it will be passed to .handle_error()

        :param controller: Controller, the controller instance whose method is
            going to be called
        :param controller_args: list|tuple, the positional controller method
            arguments that were passed in
        :param controller_kwargs: dict, the keyword controller method arguments
            that were passed in
        :returns: tuple[list, dict], index 1 will be passed to the controller
            method as *args, index 2 will be passed as **kwargs, if None is
            returned then no change to the controller args and kwargs will be
            made
        """
        return controller_args, controller_kwargs

    async def handle_response(self, controller, controller_response):
        """This is called right after the controller method is called, this is
        for decorators that want to normalize the controller method return value
        in some way

        if this raises an error it will be passed to .handle_error()

        :param controller: Controller, the controller instance whose method was
            just called
        :param controller_response: Any, whatever the controller method returned
        :returns: Any, if None is returned then no changes to the controller's 
            response will be made
        """
        return controller_response


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

