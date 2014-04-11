# Endpoints

Quickest api builder in the west! Built for [First Opinion](http://firstopinionapp.com/).


## How does it work?

Endpoints translates requests to python modules without any configuration. It uses the convention:

    METHOD /module/class/args?kwargs

To find the modules, you assign a base module (a prefix) that endpoints will use as a reference point to find the correct submodule using the path. This makes it easier to bundle your controllers into something like a `controllers` module. Some examples of how http requests would be interpretted:

    GET / -> prefix.Default.GET()
    GET /foo -> prefix.foo.Default.GET()
    POST /foo/bar -> prefix.foo.Bar.POST()
    GET /foo/bar/che -> prefix.foo.Bar.GET(che)
    POST /foo/bar/che?baz=foo -> prefix.foo.Bar.POST(che, baz=foo)

Requests are translated from left bit to right bit of the path (so for path `/foo/bar/che/baz`, Endpoints would check for the `foo` module, then the `foo.bar` module, then the `foo.bar.che` module, etc. until it fails to find a valid module). Once the module is found, endpoints will then attempt to find the class with the remaining path bits, if no class is found, `Default` will be used.


### Example

So, if you set up your site like this:

    site/
      controllers/
        __init__.py

and the `controllers.__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
    def GET(self):
        return "called /"

class Foo(Controller):
    def GET(self):
        return "called /foo"
```

Then, your call requests would be translated like this:

    GET / -> controllers.Default.GET()
    GET /foo -> controllers.Foo.GET()


### Handling path parameters and query vars

You can define your controller methods to accept certain path params and to accept query params:

```python
class Foo(Controller):
  def GET(self, one, two=None, **params): pass
  def POST(self, **params): pass
```

your call requests would be translated like this:

    GET /foo/one -> prefix.Foo.GET("one")
    GET /foo/one?param1=val1&param2=val2 -> prefix.Foo.GET("one", param1="val1", param2="val2")
    GET /foo -> 404, no one path param
    GET /foo/one/two -> prefix.Foo.GET("one", "two")

Post requests are also merged with the `**params` on the controller method, with the `POST` params taking precedence:

    POST /foo?param1=GET1&param2=GET2 body: param1=POST1&param3=val3 -> prefix.Foo.POST(param1="POST1", param2="GET2", param3="val3")


#### Fun with parameters

The `endpoints.decorators` module gives you some handy decorators to make parameter handling and error checking easier:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @param('param1', default="some val")
  @param('param2', choices=['one', 'two'])
  def GET(self, **params): pass
```

For the most part, the `param` decorator tries to act like Python's built-in [argparse.add_argument()](https://docs.python.org/2/library/argparse.html#the-add-argument-method) method.

There is also a `get_param` decorator when you just want to make sure a query param exists and don't care about post params and a `post_param` when you only care about posted parameters. There is also a `require_params` decorator that is a quick way to just make sure certain params were passed in:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @require_params('param1', 'param2', 'param3')
  def GET(self, **params): pass
```

That will make sure `param1`, `param2`, and `param3` were all present in the `**params` dict.


### Example application

The `example` directory has a little server that will demonstrate how endpoints works, you can run it:

    $ cd /path/to/endpoints/example
    $ python server.py

Then, in another terminal window:

    $ curl http://localhost:8000
    $ curl http://localhost:8000/foo


### Versioning requests

Endpoints has support for `Accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).

If you are using versioning, then the prefix for each controller would be `prefix.version`. Let's say you've set up your versioned site like this:

    site/
      controllers/
        __init__.py
        v1/
          __init__.py
        v2/
          __init__.py

and `controllers.v1.__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
    def GET(self):
        return "called version 1 /"

class Foo(Controller):
    def GET(self):
        return "called version 1 /foo"
```

And `controllers.v2.__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
    def GET(self):
        return "called version 2 /"

class Foo(Controller):
    def GET(self):
        return "called version 2 /foo"
```

Then, your call requests would be translated like this:

    GET / with Accept: */*;version=v1 -> controllers.v1.Default.GET()
    GET /foo with Accept: */*;version=v1 -> controllers.v1.Foo.GET()

    GET / with Accept: */*;version=v2 -> controllers.v2.Default.GET()
    GET /foo with Accept: */*;version=v2 -> controllers.v2.Foo.GET()


### CORS support

Endpoints has a `CorsMixin` you can add to your controllers to support [CORS requests](http://www.w3.org/TR/cors/):

```python
from endpoints import Controller, CorsMixin

class Default(Controller, CorsMixin):
    def GET(self):
        return "called / supports cors"
```

The `CorsMixin` will handle all the `OPTION` requests, and setting all the headers, so you don't have to worry about them (unless you want to).

**todo, move our auth_basic, and auth_oauth decorators into a decorators sub module?** Only problem I see with this is doing the actual authentication, so there needs to be a way for the module to call another method and return if it is valid, not sure how we would want to make that generic or if it is worth trying to make that generic. The other issue is we use [decorators](https://github.com/firstopinion/decorators) for all those decorators and I'm not sure I want to introduce a dependency.


## Install

Use PIP

    pip install endpoints

If you want the latest and greatest, you can also install from source:

    pip install git+https://github.com/firstopinion/endpoints#egg=endpoints


### To run tests

To run the tests, you'll also need to install the `testdata` module: 

    pip install testdata

To run the tests:

    python -m unittest endpoints_test


## License

MIT

