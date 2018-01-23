# Authentication

Validating access to certain resources is pretty common and so _endpoints_ provides [helper decorators](https://github.com/firstopinion/endpoints/blob/master/endpoints/decorators/auth.py) to make this process easier and customizable.


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

class auth_user(basic_auth):
    """validate a user in our system and set request.user if a valid user is found"""

    def target(self, request, username, password):
        # validate username and password using app specific db or whatnot
        user = magical_db_check(username, password)
        request.user = user
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


### Example 1. Create a permissions checker

Sometimes, you might only want certain users to be able to access certain endpoints, so let's create a decorator that can take a set of permissions and then check those permissions.


```python
from endpoints.decorators.auth import AuthDecorator


class PermAuth(AuthDecorator):

    def decorate(self, func, *perms):
        self.perms = perms
        return super(PermAuth, self).decorate(func)

    def normalize_target_params(self, request, controller_args, controller_kwargs):
        user = get_user(request)
        return [], {
            'user_perms': set(user.perms),
            'valid_perms': set(self.perms),
        }

    def target(self, request, user, user_perms, valid_perms):
        return len(user_perms.intersection(valid_perms)) > 0
```

First, we setup our `PermAuth` decorator to accept one or more permissions, we do this by overriding the `decorate` method and saving those passed in permissions for later use:

```python
def decorate(self, func, *perms):
    self.perms = perms
```

Next, we override `normalize_target_params` to setup the params that will be sent to our `target` method, this method returns a tuple `list, dict` that will get sent to our target method in the form of: `*args, **kwargs`.

In this instance, our `normalize_target_params` pulls our user out from some magical `get_user` and then returns that user's permissions along with our saved permissions from the `decorate` method.

And finally, we add our `target` method to check the values `normalize_target_params` gave us.

Now, we can use this decorator on our Controller methods:

```python
from endpoints import Controller


class Default(Controller):
    @PermAuth("bar", "che") # bar and che can access GET
    def GET(self):
        return "user can GET\n"

    @PermAuth("bar") # you must have bar perms to POST
    def POST(self, **kwargs):
        return "user can POST\n"

```

Now let's try it out, but first we'll need to flesh out our `get_user` method:

```python

def get_user(request):
    class User(object):
        def __init__(self, *perms):
            self.perms = perms

    mapping = {
        ("alice", "1234"): User("bar"),
        ("bob", "1234"): User("che")
    }

    return mapping[request.get_auth_basic()]
```


You can find the above code in `examples/authex1.py`. So let's start our server:

    $ cd example
    $ python ../endpoints/bin/wsgiserver.py --prefix authex1 --host 127.0.0.1:8080

And then let's make some requests to test it out:


    $ curl -u "alice:1234" "http://127.0.0.1:8080"
    "user can GET"
    $ curl -u "alice:1234" "http://127.0.0.1:8080" -X "POST"
    "user can POST"
    $ curl -u "bob:1234" "http://127.0.0.1:8080" -X "POST"
    {"errmsg": "PermAuth check failed"}
    $ curl -u "bob:1234" "http://127.0.0.1:8080"
    "user can GET"

Yay, it works as expected!

