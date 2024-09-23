# -*- coding: utf-8 -*-
import inspect

from ..exception import CallError, AccessDenied
from ..utils import String
from .base import ControllerDecorator


class AuthDecorator(ControllerDecorator):
    """
    handy auth decorator that makes doing basic or token auth easy peasy

    This is more of a base class for the other auth decorators, but it can be
    used on its own if you want, but I would look at using the other decorators
    first before deciding to use this one

    :example:
        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth

        def target(controller, *args, **kwargs):
            if controller.request.get_bearer_token() != "foo":
                raise ValueError("invalid bearer token")

        class Default(Controller):
            @AuthDecorator(target=target)
            def GET(self):
                return "hello world"
    """
    scheme = ""
    """Needed for WWW-Authenticate header

    https://tools.ietf.org/html/rfc7235#section-4.1
    """

    realm = ""
    """Optional namespace for WWW-Authenticate header"""

    async def handle(self, *args, **kwargs):
        target = self.definition_kwargs.get("target", None)
        if not target:
            if self.definition_args and callable(self.definition_args[0]):
                target = self.definition_args[0]

        if target:
            ret = target(*args, **kwargs)
            while inspect.iscoroutine(ret):
                ret = await ret

            return ret

        else:
            raise NotImplementedError()

    async def handle_handle_error(self, controller, e):
        if isinstance(e, CallError):
            await super().handle_error(controller, e)

        elif isinstance(e, NotImplementedError):
            raise CallError(
                403,
                "You need a target function to use authentication"
            ) from e

        else:
            raise AccessDenied(
                String(e),
                scheme=self.scheme,
                realm=self.realm,
            ) from e


class auth_basic(AuthDecorator):
    """Auth decorator that checks for username, password in an Authorization
    basic header

    :example:

        # create a basic http auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth_basic

        def target(controller, username, password):
            return username == "foo" and password == "bar"

        class Default(Controller):
            @auth_basic(target=target)
            def GET(self):
                return "hello world"
    """
    scheme = AccessDenied.SCHEME_BASIC

    async def handle_kwargs(self, controller, **kwargs):
        username, password = controller.request.get_auth_basic()

        if not username:
            raise ValueError("username is required")

        if not password:
            raise ValueError("password is required")

        return {
            "controller": controller,
            "username": username,
            "password": password,
        }


class auth_bearer(AuthDecorator):
    """Auth decorator that checks for token in an authorization Bearer header

    :example:

        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth_token

        def target(controller, token):
            return token == "foo"

        class Default(Controller):
            @auth_token(target=target)
            def GET(self):
                return "hello world"
    """
    scheme = AccessDenied.SCHEME_BEARER

    async def handle_kwargs(self, controller, **kwargs):
        token = controller.request.get_auth_bearer()
        if not token:
            raise ValueError("Authorization bearer token is required")

        return {
            "controller": controller,
            "token": token,
        }

