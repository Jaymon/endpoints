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

    the Request .get_auth_client(), .get_auth_basic(), .get_auth_schem(), and 
    .get_auth_bearer() methods and .access_token property should come in handy
    here

    :example:
        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth

        def target(controller, *args, **kwargs):
            if controller.request.access_token != "foo":
                raise ValueError("invalid access token")

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
                "You need a validator function to use authentication"
            ) from e

        else:
            raise AccessDenied(
                String(e),
                scheme=self.scheme,
                realm=self.realm,
            ) from e


class auth_basic(AuthDecorator):
    """
    handy basic auth decorator that checks for username, password in an auth
    header

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


class auth_client(auth_basic):
    """
    handy OAuth client auth decorator that checks for client_id and
    client_secret

    :example:

        # create a client auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth_client

        def target(controller, client_id, client_secret):
            return client_id == "foo" and client_secret == "bar"

        class Default(Controller):
            @auth_client(target=target)
            def GET(self):
                return "hello world"
    """
    async def handle_kwargs(self, controller, **kwargs):
        client_id, client_secret = controller.get_client_tokens(
            *kwargs["controller_args"],
            **kwargs["controller_kwargs"]
        )

        if not client_id:
            raise ValueError("client_id is required")

        if not client_secret:
            raise ValueError("client_secret is required")

        return {
            "controller": controller,
            "client_id": client_id,
            "client_secret": client_secret,
        }


class auth_token(AuthDecorator):
    """
    handy token auth decorator that checks for access_token in an
    authorization Bearer header

    :example:

        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth_token

        def target(controller, access_token):
            return access_token == "foo"

        class Default(Controller):
            @auth_token(target=target)
            def GET(self):
                return "hello world"
    """
    scheme = AccessDenied.SCHEME_BEARER

    async def handle_kwargs(self, controller, **kwargs):
        access_token = controller.get_access_token(
            *kwargs["controller_args"],
            **kwargs["controller_kwargs"]
        )

        if not access_token:
            raise ValueError("access_token is required")

        return {
            "controller": controller,
            "access_token": access_token,
        }

