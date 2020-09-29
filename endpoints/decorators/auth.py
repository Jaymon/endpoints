# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging

from ..exception import CallError, AccessDenied
from ..utils import String
from .base import TargetDecorator


logger = logging.getLogger(__name__)


class auth(TargetDecorator):
    """
    handy auth decorator that makes doing basic or token auth easy peasy

    This is more of a base class for the other auth decorators, but it can be used
    on its own if you want, but I would look at using the other decorators first
    before deciding to use this one

    the request .get_auth_client(), .get_auth_basic(), .get_auth_schem(), and 
    .get_auth_bearer() methods and .access_token property should come in handy here

    :example:
        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth

        def target(controller, *args, **kwargs):
            if controller.request.access_token != "foo":
                raise ValueError("invalid access token")

        class Default(Controller):
            @auth("Bearer", target=target)
            def GET(self):
                return "hello world"
    """
    scheme = ""
    """Needed for WWW-Authenticate header https://tools.ietf.org/html/rfc7235#section-4.1"""

    realm = ""
    """Optional namespace for WWW-Authenticate header"""

    def handle_error(self, controller, e):
        logger.debug(e, exc_info=True)
        if isinstance(e, NotImplementedError):
            raise CallError(403, "You need a validator function to use authentication")
        else:
            raise AccessDenied(
                String(e),
                scheme=self.scheme,
                realm=self.realm,
            )

    def definition(self, target=None, *anoop, **kwnoop):
        """makes target optional since auth decorators are made to have target passed
        in or to easily be extended"""
        return super(auth, self).definition(target=target)


class auth_basic(auth):
    """
    handy basic auth decorator that checks for username, password in an auth header

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

    def handle_args(self, controller, controller_args, controller_kwargs):
        username, password = controller.request.get_auth_basic()

        if not username: raise ValueError("username is required")
        if not password: raise ValueError("password is required")

        return [controller, username, password]


class auth_client(auth_basic):
    """
    handy OAuth client auth decorator that checks for client_id and client_secret

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
    def handle_args(self, controller, controller_args, controller_kwargs):
        client_id, client_secret = controller.request.client_tokens

        if not client_id: raise ValueError("client_id is required")
        if not client_secret: raise ValueError("client_secret is required")

        return [controller, client_id, client_secret]


class auth_token(auth):
    """
    handy token auth decorator that checks for access_token in an authorization
    Bearer header

    :example:

        # create a token auth decorator
        from endpoints import Controller
        from endpoints.decorators.auth import auth_token

        def target(request, access_token):
            return access_token == "foo"

        class Default(Controller):
            @auth_token(target=target)
            def GET(self):
                return "hello world"
    """
    scheme = AccessDenied.SCHEME_BEARER

    def handle_args(self, controller, controller_args, controller_kwargs):
        access_token = controller.request.access_token

        if not access_token: raise ValueError("access_token is required")

        return [controller, access_token]

