# Authentication

Validating access to certain endpoints is pretty common and so _endpoints_ provides helper decorators to make this process easier and customizable.

## Http basic authentication

Want to have the browser prompt for a username and password? Use the `endpoints.decorators.auth.basic_auth` decorator:

```python
# controller.py
# create a basic http auth decorator

from endpoints import Controller
from endpoints.decorators.auth import basic_auth

def target(request, username, password):
    return username == "foo" and password == "bar"


class Default(Controller):
    @basic_auth(target=target)
    def GET(self):
        return "hello world"
```

That's it, now any request to `/` will prompt for username and password if not provided.


## Other authentication

Check out the `endpoints.decorators.auth` module for other authentication decorators

* `client_auth` - Similar to `basic_auth` but checks for **client_id** and **client_secret** instead of username and password.
* `token_auth` - Checks for an `Authorization  Bearer <TOKEN>` header.


## Customization

You can extend any of the auth decorators to fit them into your own system:

```python
from endpoints.decorators.auth import basic_auth

class auth_user(auth_basic):
    """validate a user in our system and set request.user if a valid user is found"""

    def target(self, request, username, password):
        # validate username and password using app specific db or whatnot
        return True # true if user is valid, false otherwise

    def decorate(self, f):
        # get rid of letting the decorator take a target keyword since we use self.target
        return super(auth_user, self).decorate(f, target=None)
```


But there is an `AuthDecorator` specifically designed for easy overriding for general purpose authentication, it expects that the child class will implement a `target` method that takes same params as a controller and, also like a controller, request is available through the instance property `self.request`.

```python
from endpoints import Controller
from endpoints.decorators.auth import AuthDecorator

class auth(AuthDecorator):
    def target(self, *args, **kwargs):
        if kwargs["key"] != foo
            raise ValueError("invalid access token")


class Default(Controller):
    @auth()
    def GET(self):
        return "hello world"
```

