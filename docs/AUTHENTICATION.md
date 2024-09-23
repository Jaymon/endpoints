# Authentication

Validating access to certain resources is pretty common and so _endpoints_ provides [helper decorators](https://github.com/firstopinion/endpoints/blob/master/endpoints/decorators/auth.py) to make this process easier and customizable.


## Http basic authentication

Want to require a simple username and password? Use the `endpoints.decorators.auth.auth_basic` decorator:

```python
# controller.py
# create a basic http auth decorator

from endpoints import Controller
from endpoints.decorators.auth import auth_basic


async def target(self, controller, username, password):
    return username == "foo" and password == "bar"

class Default(Controller):
    @auth_basic(target=target)
    async def GET(self):
        return "hello world"
```

That's it, now any request to `/` will required a username and password.


## HTTP bearer authentication

Want to authenticate a token? This example (which could also be done with `auth_basic`) shows how to override the default bearer token authentication to perform token authentication.

```python
# controller.py
# create a bearer http auth decorator

from endpoints import Controller
from endpoints.decorators.auth import auth_bearer

class auth_foo(auth_bearer):
    async def target(self, controller, token):
        return token == "foo"

class Default(Controller):
    @auth_foo()
    async def GET(self):
        return "hello world"
```


## Customization

You can extend any of the auth decorators to fit them into your own system:

```python
from endpoints.decorators.auth import auth_basic


class auth_user(auth_basic):
    """validate a user in our system and set request.user if a valid user is found"""
    async def auth_user(self, controller, username, password):
        # validate username and password using app specific db or whatnot
        user = magical_db_check(username, password)
        controller.request.user = user
        return True # true if user is valid, false otherwise
``` 

There is also an `AuthDecorator` specifically designed for easy overriding for general purpose authentication:

```python
from endpoints import Controller
from endpoints.decorators.auth import AuthDecorator


class auth(AuthDecorator):
    async def handle(self, controller, **kwargs):
        # check something or do something to validate the request
        # return True if auth was valid, False otherwise
        pass


class Default(Controller):
    @auth
    def GET(self):
        return "hello world"
```


### Example 1. Create a permissions checker

Sometimes, you might only want certain users to be able to access certain endpoints, so let's create a decorator that can take a set of permissions and then check those permissions.


```python
from endpoints.decorators.auth import AuthBackend, AuthDecorator


class auth_perm(AuthDecorator):
    def definition(self, *perms):
        self.perms = perms

    async def handle_kwargs(self, controller, **kwargs):
        user = await get_user(request) # magically fetch a user
        return {
            'user_perms': set(user.perms),
            'valid_perms': set(self.perms),
        }
    
    async def handle(self, user_perms, valid_perms):
        return len(user_perms.intersection(valid_perms)) > 0
```

First, we setup our `auth_perm` decorator to accept one or more permissions, we do this by overriding the `definition` method and saving those passed in permissions for later use:

```python
def definition(self, *perms):
    self.perms = perms
```

Next, we override `handle_kwargs` to setup the params that will be sent to our `handle` method, this method returns a `dict` that will get sent to our `handle` method in the form of: `**kwargs`.

In this instance, our `handle_kwargs` pulls our user out from some magical async `get_user` method and then returns that user's permissions along with our saved permissions set in the `definition` method.

And finally, we have our `handle` method to check the values `handle_kwargs` gave us.

Now, we can use this decorator on our Controller methods:

```python
from endpoints import Controller

class Default(Controller):
    @auth_perm("bar", "che") # `bar` and `che` permissions can access GET
    async def GET(self):
        return "user can GET\n"

    @auth_perm("bar") # you must have `bar` perms to POST
    async def POST(self, **kwargs):
        return "user can POST\n"
```
