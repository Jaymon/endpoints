from __future__ import absolute_import
import logging

from decorators import FuncDecorator

from ..exception import CallError, AccessDenied


logger = logging.getLogger(__name__)


class auth(FuncDecorator):
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
    def normalize_target_params(self, request, *args, **kwargs):
        param_args = [request] + list(args)
        return param_args, kwargs

    def target(self, request, *args, **kwargs):
        try:
            return self.target_callback(request, *args, **kwargs)

        except (AttributeError, TypeError) as e:
            logger.debug(e, exc_info=True)
            raise CallError(403, "You need a validator function to use authentication")

    def handle_target(self, request, *args, **kwargs):

        try:
            param_args, param_kwargs = self.normalize_target_params(request, *args, **kwargs)
            ret = self.target(*param_args, **param_kwargs)
            if not ret:
                raise ValueError("target did not return True")

        except CallError:
            raise

        except Exception as e:
            logger.debug(e, exc_info=True)
            raise AccessDenied(self.realm, e.message)

    def decorate(self, func, realm='', target=None, *anoop, **kwnoop):
        self.realm = realm
        if target:
            self.target_callback = target

        def decorated(decorated_self, *args, **kwargs):
            self.handle_target(decorated_self.request, *args, **kwargs)
            return func(decorated_self, *args, **kwargs)

        return decorated


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
    def normalize_target_params(self, request, *args, **kwargs):
        username, password = request.get_auth_basic()
        kwargs = {
            "request": request,
            "username": username,
            "password": password,
        }
        return [], kwargs

    def decorate(self, func, target):
        return super(basic_auth, self).decorate(func, realm="basic", target=target)


class client_auth(basic_auth):
    """
    handy OAuth client auth decorator that checks for client_id and client_secret

    example --

    # create a token auth decorator
    from endpoints import Controller
    from endpoints.decorators.auth import client_auth

    class Default(Controller):
        @client_auth(client_apps=[("foo", "bar")])
        def GET(self):
            return "hello world"
    """
    def target_callback(self, request, client_id, client_secret, client_apps):
        found_client_app = self.find_client_app(client_id, client_secret, client_apps)
        if not found_client_app:
            raise ValueError("No valid client_id and client_secret auth found")
        return True

    def find_client_apps(self):
        """compile all the client_apps we want to validate agains

        this is the method that should be overridden in a subclass

        return -- list -- a list of tuples containing (client_id, client_secret) to
            validate against
        """
        client_apps = []
        try:
            client_apps = self.client_apps
        except AttributeError:
            pass
        return client_apps


    def find_client_app(self, client_id, client_secret, client_apps):
        """This will handled authenticating against a tuple (client_apps) of
        (client_id, client_secret) that can be passed into the decorator

        client_id -- string -- the found request client id
        client_secret -- string -- the found request client_secret
        client_apps -- list -- a list of (client_id, client_secret, options) tuples to compare
            the passed in client_id and client_secret against

        return -- tuple -- the found matching client_app from the client_apps list
        """
        found_client_app = None
        for client_t in client_apps:
            clen = len(client_t)
            app_cid = client_t[0]
            app_cs = client_t[1]
            if client_id == app_cid and client_secret == app_cs:
                found_client_app = client_t
                break

        return found_client_app

    def find_client_params(self, request, *args, **kwargs):
        """try and get client id and secret first from basic auth header, then from
        GET or POST parameters

        request -- Request -- the active Request instance
        *args -- list -- any path passed to controller
        **kwargs -- dict -- the combined GET and POST variables passed to controller

        return -- tuple -- client_id, client_secret
        """
        client_id, client_secret = request.get_auth_basic()
        if not client_id and not client_secret:
            client_id = kwargs.get('client_id', '')
            client_secret = kwargs.get('client_secret', '')

        if not client_id: raise ValueError("client_id is required")
        if not client_secret: raise ValueError("client_secret is required")

        return client_id, client_secret

    def normalize_target_params(self, request, *args, **kwargs):
        client_id, client_secret = self.find_client_params(request, *args, **kwargs)
        kwargs = {
            "request": request,
            "client_id": client_id,
            "client_secret": client_secret,
            "client_apps": self.find_client_apps(),
        }
        return [], kwargs

    def decorate(self, func, client_apps=None):
        if client_apps:
            self.client_apps = client_apps

        return super(client_auth, self).decorate(func, target=None)


class token_auth(auth):
    """
    handy token auth decorator that checks for access_token in an authorization Bearer
    header

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
    def normalize_target_params(self, request, *args, **kwargs):
        access_token = request.get_auth_token()
        kwargs = {
            "request": request,
            "access_token": access_token,
        }
        return [], kwargs

    def decorate(self, func, target):
        return super(token_auth, self).decorate(func, realm="Bearer", target=target)


