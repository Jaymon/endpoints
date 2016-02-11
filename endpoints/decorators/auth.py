from __future__ import absolute_import
import logging

from ..exception import CallError, AccessDenied
from .base import TargetDecorator


logger = logging.getLogger(__name__)


class auth(TargetDecorator):
    """
    handy auth decorator that makes doing basic or token auth easy peasy

    This is more of a base class for the other auth decorators, but it can be used
    on its own if you want, but I would look at the other decorators first

    the request get_auth_client(), get_auth_basic(), and get_auth_bearer() methods
    and access_token property should come in real handy here

    example --

    # create a token auth decorator
    from endpoints import Controller
    from endpoints.decorators.auth import auth

    def target(request):
        if request.access_token != "foo":
            raise ValueError("invalid access token")

    class Default(Controller):
        @auth("Bearer", target=target)
        def GET(self):
            return "hello world"
    """
    def handle_error(self, e):
        if isinstance(e, NotImplementedError):
            raise CallError(403, "You need a validator function to use authentication")
        else:
            raise AccessDenied(self.realm, e.message)

    def decorate(self, func, realm='', target=None, *anoop, **kwnoop):
        self.realm = realm
        return super(auth, self).decorate(func, target=target)


class basic_auth(auth):
    """
    handy basic auth decorator that checks for username, password in an auth header

    example --

    # create a token auth decorator
    from endpoints import Controller
    from endpoints.decorators.auth import basic_auth

    def target(request, username, password):
        return username == "foo" and password == "bar"

    class Default(Controller):
        @basic_auth(target=target)
        def GET(self):
            return "hello world"
    """
    def normalize_target_params(self, request, controller_args, controller_kwargs):
        username, password = request.get_auth_basic()

        if not username: raise ValueError("username is required")
        if not password: raise ValueError("password is required")

        kwargs = {
            "request": request,
            "username": username,
            "password": password,
        }
        return [], kwargs

    def decorate(self, func, target=None):
        return super(basic_auth, self).decorate(func, realm="basic", target=target)


class client_auth(basic_auth):
    """
    handy OAuth client auth decorator that checks for client_id and client_secret

    example --

    # create a token auth decorator
    from endpoints import Controller
    from endpoints.decorators.auth import client_auth

    def target(request, client_id, client_secret):
        return client_id == "foo" and client_secret == "bar"

    class Default(Controller):
        @client_auth(target=target)
        def GET(self):
            return "hello world"
    """
    def normalize_target_params(self, request, controller_args, controller_kwargs):
        client_id, client_secret = request.client_tokens

        if not client_id: raise ValueError("client_id is required")
        if not client_secret: raise ValueError("client_secret is required")

        kwargs = {
            "request": request,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        return [], kwargs

    def decorate(self, func, target=None):
        return super(client_auth, self).decorate(func, target=target)


class token_auth(auth):
    """
    handy token auth decorator that checks for access_token in an authorization
    Bearer header

    example --

    # create a token auth decorator
    from endpoints import Controller
    from endpoints.decorators.auth import token_auth

    def target(request, access_token):
        return access_token == "foo"

    class Default(Controller):
        @token_auth(target=target)
        def GET(self):
            return "hello world"
    """
    def normalize_target_params(self, request, controller_args, controller_kwargs):
        access_token = request.access_token

        if not access_token: raise ValueError("access_token is required")

        kwargs = {
            "request": request,
            "access_token": access_token,
        }
        return [], kwargs

    def decorate(self, func, target=None):
        return super(token_auth, self).decorate(func, realm="Bearer", target=target)


