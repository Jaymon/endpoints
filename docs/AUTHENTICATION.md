# Authentication

Validating access to certain resources is pretty common and so _endpoints_ provides [helper decorators](https://github.com/firstopinion/endpoints/blob/master/endpoints/decorators/auth.py) to make this process easier and customizable.


## Http basic authentication

Want to have the browser prompt for a username and password? Use the `endpoints.decorators.auth.auth_basic` decorator:

```python
# controller.py
# create a basic http auth decorator

from endpoints import Controller
from endpoints.decorators.auth import AuthBackend, auth_basic

class Backend(AuthBackend):
    async def auth_basic(self, controller, username, password):
        return username == "foo" and password == "bar"

class Default(Controller):
    @basic_auth(backend_class=Backend)
    async def GET(self):
        return "hello world"
```

That's it, now any request to `/` will prompt for username and password if not provided.


## Other authentication

Check out the `endpoints.decorators.auth` module for other authentication decorators

* `auth_client` - Similar to `auth_basic` but checks for **client_id** and **client_secret** instead of username and password.
* `auth_token` - Checks for an `Authorization  Bearer <TOKEN>` header.


## Customization

You can extend any of the auth decorators to fit them into your own system:

```python
from endpoints.decorators.auth import AuthBackend, auth_basic

class Backend(AuthBackend):
    async def auth_user(self, controller, username, password):
        # validate username and password using app specific db or whatnot
        user = magical_db_check(username, password)
        request.user = user
        return True # true if user is valid, false otherwise

class auth_user(auth_basic):
    """validate a user in our system and set request.user if a valid user is found"""
    backend_class = Backend
``` 

There is also an `AuthDecorator` specifically designed for easy overriding for general purpose authentication:

```python
from endpoints import Controller
from endpoints.decorators.auth import AuthBackend, AuthDecorator

class Backend(AuthBackend):
    async def auth(self, controller, controller_args, controller_kwargs):
        # check something or do something to validate the request
        # return True if auth was valid, False otherwise
        
    
class auth(AuthDecorator):
    backend_class = Backend


class Default(Controller):
    @auth()
    def GET(self):
        return "hello world"
```


### Example 1. Create a permissions checker

Sometimes, you might only want certain users to be able to access certain endpoints, so let's create a decorator that can take a set of permissions and then check those permissions.


```python
from endpoints.decorators.auth import AuthBackend, AuthDecorator

class Backend(AuthBackend):
    async def perm_auth(self, user_perms, valid_perms):
        return len(user_perms.intersection(valid_perms)) > 0

class perm_auth(AuthDecorator):
    backend_class = Backend
    
    def definition(self, *perms):
        self.perms = perms

    async def handle_kwargs(self, controller, controller_args, controller_kwargs):
        user = await get_user(request)
        return {
            'method_name': "perm_auth",
            'user_perms': set(user.perms),
            'valid_perms': set(self.perms),
        }
```

First, we setup our `PermAuth` decorator to accept one or more permissions, we do this by overriding the `definition` method and saving those passed in permissions for later use:

```python
def definition(self, *perms):
    self.perms = perms
```

Next, we override `handle_kwargs` to setup the params that will be sent to our `Backend.auth` method, this method returns a `dict` that will get sent to our `Backend.auth` method in the form of: `**kwargs`.

In this instance, our `handle_kwargs` pulls our user out from some magical async `get_user` method and then returns that user's permissions along with our saved permissions set in the `definition` method.

And finally, we add our `Backend.auth` method to check the values `handle_kwargs` gave us.

Now, we can use this decorator on our Controller methods:

```python
from endpoints import Controller

class Default(Controller):
    @perm_auth("bar", "che") # bar and che can access GET
    async def GET(self):
        return "user can GET\n"

    @perm_auth("bar") # you must have bar perms to POST
    async def POST(self, **kwargs):
        return "user can POST\n"

```
