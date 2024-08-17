# Endpoints

Quickest API builder in the West! 

_Endpoints_ is a lightweight REST api framework written in python that supports both WSGI and ASGI. _Endpoints_ has been used in multiple production systems that handle millions of requests daily.


## 5 Minute Getting Started

### Installation

First, install endpoints with the following command.

    $ pip install endpoints

If you want the latest and greatest you can also install from source:

    $ pip install -U "git+https://github.com/jaymon/endpoints#egg=endpoints"


### Create a Controller Module

Create a controller file with the following command:

    $ touch controllers.py

Add the following code to the `controllers.py` file (These controller classes are just to help you get started and understand how endpoints works).

```python
from endpoints import Controller

class Default(Controller):
  """The special class `Default` handles / requests"""
  async def GET(self):
    return "Default handler"

  async def POST(self, **kwargs):
    return 'hello {}'.format(kwargs['name'])

class Foo(Controller):
  """This class handles `/foo` requests"""
  async def GET(self):
    return "Foo handler"
```


### Start a WSGI Server

Now that you have your `controllers.py`, let's use the built-in WSGI server to serve them, we'll set our `controllers.py` file as the [controller prefix](docs/PREFIXES.md) so Endpoints will know where to find the [Controller classes](docs/CONTROLLERS.md) we just defined:

    $ endpoints --prefix=controllers --host=localhost:8000


### Start an ASGI Server

Install [Daphne](https://github.com/django/daphne):

    $ pip install -U daphne

And start it:

    $ ENDPOINTS_PREFIX=controllers daphne -b localhost -p 8000 -v 3 endpoints.interface.asgi:ApplicationFactory

### Test it out

Using curl:

    $ curl http://localhost:8000
    "Default handler"
    $ curl http://localhost:8000/foo
    "Foo handler"
    $ curl http://localhost:8000/ -d "name=Awesome you"
    "hello Awesome you"

That's it. Easy peasy!

In the ***first request*** (`/`), the `controllers` module was accessed, then the `Default` class, and then the `GET` method.

In the ***second request*** (`/foo`), the `controllers` module was accessed, then the `Foo` class as specified in the path of the url, and then the `GET` method.

Finally, in the ***last request***, the `controllers` module was accessed, then the `Default` class, and finally the `POST` method with the passed in argument as JSON.


## How does it work?

*Endpoints* translates requests to python modules without any configuration.

It uses the following convention.

    METHOD /module/class/args?kwargs

_Endpoints_ will use the prefix module you set as a reference point to find the correct submodule using the path specified by the request.

Requests are translated from the left bit to the right bit of the path.
So for the path `/foo/bar/che/baz`, endpoints would first check for the `foo` module, then the `foo.bar` module, then the `foo.bar.che` module, etc. until it fails to find a valid module.

Once the module is found, endpoints will then attempt to find the class with the remaining path bits. If no matching class is found then a class named `Default` will be used if it exists.

This makes it easy to bundle your controllers into a `controllers` package/module.

Below are some examples of HTTP requests and how they would be interpreted using endpoints.

**Note:** prefix refers to the name of the base module that you set.

|HTTP Request                           | Path Followed                     |
|---------------------------------------|---------------------------------- |
|GET /                                  | prefix.Default.GET()              |
|GET /foo                               | prefix.foo.Default.GET()          |
|POST /foo/bar                          | prefix.foo.Bar.POST()             |
|GET /foo/bar/che                       | prefix.foo.Bar.GET(che)           |
|GET /foo/bar/che?baz=foo               | prefix.foo.Bar.GET(che, baz=foo)  |
|POST /foo/bar/che with body: baz=foo   | prefix.foo.Bar.POST(che, baz=foo) |


### One more example

Let's say your site had the following setup:

    site/controllers/__init__.py

and the file `controllers/__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
  async def GET(self):
    return "called /"

class Foo(Controller):
  async def GET(self):
    return "called /foo"
```

then your call requests would be translated like this:

|HTTP Request   | Path Followed             |
|-------------- | ------------------------- |
|GET /          | controllers.Default.GET() |
|GET /foo       | controllers.Foo.GET()     |


## Learn more about Endpoints

The [docs](https://github.com/jaymon/endpoints/tree/master/docs) contain more information about how _Endpoints_ works and what can be done with it.

