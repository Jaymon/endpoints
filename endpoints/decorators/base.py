# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging

from decorators import FuncDecorator

from ..exception import CallError


logger = logging.getLogger(__name__)


class ControllerDecorator(FuncDecorator):
    """Base decorator providing common functionality to run .handle() when a decorated
    function is called, this class is meant to be extended by a child

    This also is Controller specific, it's meant to be used in decorators that
    decorate Controller methods

    .. seealso:: decorators.auth
    """
    def handle_params(self, controller, controller_args, controller_kwargs):
        """get params ready for calling .handle()

        this method exists because child classes might only really need certain params
        passed to the method, this allows the child classes to decided what their
        .handle method needs

        :param controller: call.Controller instance, you can get the request with
            controller.request
        :param controller_args: the arguments that will be passed to the controller
        :param controller_kwargs: the key/val arguments that will be passed to the 
            controller, these usually come from query strings and post bodies
        :returns: a tuple (list, dict) that correspond to the *args, **kwargs that
            will be passed to the target() method
        """
        return [controller, controller_args, controller_kwargs], {}

    def handle_error(self, controller, e):
        """Any error the class isn't sure how to categorize will go through this method

        overriding this method allows child classes to customize responses based
        on certain encountered errors

        :param controller: the controller instance that contains the method that
            raised e
        :param e: the raised error
        """
        logger.warning(e, exc_info=True)
        raise e

    def handle_call(self, controller, controller_args, controller_kwargs):
        """Internal method for this class

        handles normalizing the passed in values from the decorator using
        .normalize_target_params() and then passes them to the set .target()
        """
        try:
            handle_args, handle_kwargs = self.handle_params(
                controller,
                controller_args,
                controller_kwargs
            )
            ret = self.target(*target_args, **target_kwargs)
            if not ret:
                raise ValueError("{} check failed".format(self.__class__.__name__))

        except CallError:
            raise

        except Exception as e:
            self.handle_error(controller, e)

    def decorate(self, func, *args, **kwargs):
        """decorate the passed in func calling target when func is called

        In child classes this will most likely be 

        :param func: the function being decorated
        :param target: the target that will be run when func is called
        :returns: the decorated func
        """
        self.handle_definition(*args, **kwargs)

        def decorated(controller, *controller_args, **controller_kwargs):
            self.handle_call(controller, controller_args, controller_kwargs)
            return func(controller, *controller_args, **controller_kwargs)

        return decorated

    def handle_definition(self, *args, **kwargs):
        """whatever is passed into the decorator creation will be passed to this
        method, so you can set instance variables and stuff, this is meant to 
        be overridden in child classes

        :Example:
            a decorator like:
                @foo("bar", "che", baz=1)
                def function_name(*args, **kwargs): pass

            would be passed to this method as:

                handle_definition(*["bar", "che"], **{"baz": 1})


        :param *args: list, should be defined in a child class
        :param **kwargs: dict, all the passed in kwargs
        """
        self.args = args
        self.kwargs = kwargs

    def handle(self, *args, **kwargs):
        """The meat of the decorator, this is where all the functionality should
        go in the child class, this is meant to be extended

        if this raises an error it will be passed to .handle_error()

        :param *args: list, whatever returned from .handle_params()[0]
        :param **kwargs: dict, whatever returned from .handle_params()[1]
        """
        raise NotImplementedError()


class TargetDecorator(FuncDecorator):
    """Base decorator providing common functionality to run a target when decorated
    function is called, this class is meant to be extended by a child

    This also is very Controller specific, it's meant to be used in decorators that
    decorate Controller methods

    .. seealso:: decorators.auth
    """
    def normalize_target_params(self, request, controller_args, controller_kwargs):
        """get params ready for calling target

        this method exists because child classes might only really need certain params
        passed to the method, this allows the child classes to decided what their
        target methods need

        :param request: the http.Request instance for this specific request
        :param controller_args: the arguments that will be passed to the controller
        :param controller_kwargs: the key/val arguments that will be passed to the 
            controller, these usually come from query strings and post bodies
        :returns: a tuple (list, dict) that correspond to the *args, **kwargs that
            will be passed to the target() method
        """
        return [], dict(
            request=request,
            controller_args=controller_args, 
            controller_kwargs=controller_kwargs
        )

    def handle_error(self, controller, e):
        """Any error the class isn't sure how to categorize will go through this method

        overriding this method allows child classes to customize responses based
        on certain encountered errors

        :param e: the raised error
        """
        logger.warning(e, exc_info=True)
        raise e

    def handle_target(self, controller, controller_args, controller_kwargs):
        """Internal method for this class

        handles normalizing the passed in values from the decorator using
        .normalize_target_params() and then passes them to the set .target()
        """
        try:
            target_args, target_kwargs = self.normalize_target_params(
                controller=controller,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs
            )
            ret = self.target(*target_args, **target_kwargs)
            if not ret:
                raise ValueError("{} check failed".format(self.__class__.__name__))

        except CallError:
            raise

        except Exception as e:
            self.handle_error(controller, e)

    def decorate(self, func, target, *anoop, **kwnoop):
        """decorate the passed in func calling target when func is called

        In child classes this will most likely be 

        :param func: the function being decorated
        :param target: the target that will be run when func is called
        :returns: the decorated func
        """
        if target:
            self.target = target

        def decorated(decorated_self, *args, **kwargs):
            self.handle_target(
                controller=decorated_self,
                controller_args=args,
                controller_kwargs=kwargs
            )
            return func(decorated_self, *args, **kwargs)

        return decorated


class BackendDecorator(TargetDecorator):

    backend_class = None

    def create_backend(self, *args, **kwargs):
        if not self.backend_class:
            raise ValueError("You are using a BackendDecorator with no backend class")
        return self.backend_class(*args, **kwargs)

    def target(self, *args, **kwargs):
        backend = self.create_backend()
        return backend.target(*args, **kwargs)

    def decorate(self, func, *anoop, **kwnoop):
        return super(BackendDecorator, self).decorate(func, target=None)


