# Endpoints

Quickest api builder in the west! Lovingly crafted for [First Opinion](http://firstopinionapp.com/).

## 1 Minute getting started

First, install endpoints:

    $ pip install endpoints

Then create a controller file:

    $ touch mycontroller.py

And add some controller classes:

```python
# mycontroller.py

from endpoints import Controller

class Default(Controller):
    def GET(self):
        return "boom"

    def POST(self, **kwargs):
        return 'hello {}'.format(kwargs['name'])

class Foo(Controller):
    def GET(self):
        return "bang"
```

Set a couple environment variables for a simple python server:

    $ export ENDPOINTS_PREFIX=mycontroller
    $ export ENDPOINTS_SIMPLE_HOST=localhost:8000

Now create a server file:

    $ touch myserver.py

And add the necessary code to run a simple server:

```python
# myserver.py

import os

from endpoints.interface.simple import Server

s = Server()
s.serve_forever()
```

Start your server file:

    $ python myserver.py

And make some requests:

    $ curl "http://localhost:8000/"
    boom
    $ curl "http://localhost:8000/foo"
    bang
    $ curl -H "Content-Type: application/json" -d '{"name": "world"}' "http://localhost:8000/"
    hello world

Congratulations, you've created a webservice.

## How does it work?

Endpoints translates requests to python modules without any configuration. It uses the convention:

    METHOD /module/class/args?kwargs

To find the modules, you assign a base module (a prefix) that endpoints will use as a reference point to find the correct submodule using the path. This makes it easy to bundle your controllers into something like a `controllers` module. Some examples of how http requests would be interpretted:

    GET / -> prefix.Default.GET()
    GET /foo -> prefix.foo.Default.GET()
    POST /foo/bar -> prefix.foo.Bar.POST()
    GET /foo/bar/che -> prefix.foo.Bar.GET(che)
    GET /foo/bar/che?baz=foo -> prefix.foo.Bar.GET(che, baz=foo)
    POST /foo/bar/che with body: baz=foo -> prefix.foo.Bar.POST(che, baz=foo)

Requests are translated from the left bit to the right bit of the path (so for the path `/foo/bar/che/baz`, Endpoints would check for the `foo` module, then the `foo.bar` module, then the `foo.bar.che` module, etc. until it fails to find a valid module). Once the module is found, endpoints will then attempt to find the class with the remaining path bits. If no class is found, `Default` will be used.


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


### Handy decorators

The `endpoints.decorators` module gives you some handy decorators to make parameter handling and error checking easier:

#### Fun with parameters

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @param('param1', default="some val")
  @param('param2', choices=['one', 'two'])
  def GET(self, **params): pass
```

For the most part, the `param` decorator tries to act like Python's built-in [argparse.add_argument()](https://docs.python.org/2/library/argparse.html#the-add-argument-method) method.

There is also a `get_param` decorator when you just want to make sure a query param exists and don't care about post params and a `post_param` when you only care about posted parameters. There is also a `require_params` decorator that is a quick way to just make sure certain parameters were passed in:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @require_params('param1', 'param2', 'param3')
  def GET(self, **params): pass
```

That will make sure `param1`, `param2`, and `param3` were all present in the `**params` dict.

#### Authentication

The `auth` decorator tries to make user authentication easier, it takes a **realm** and a **target** callback in order to perform the authentication.

```python
from endpoints import Controller
from endpoints.decorators import auth

def target(request):
  username, password = request.get_auth_basic()
  if username != "foo" or password != "bar":
    raise ValueError("authentication failed")

class Foo(Controller):
  @auth("Basic", target)
  def GET(self, **params): pass
```

The `auth` decorator can also be subclassed and customized.


### Versioning requests

Endpoints has support for `Accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).

You can activate versioning just by adding a new method to your controller using the format:

    METHOD_VERSION

So, let's say you have your controllers set up like this:

    site/
      controllers/
        __init__.py

and `controllers.__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
    def GET(self):
        return "called version 1 /"
    def GET_v2(self):
        return "called version 2 /"

class Foo(Controller):
    def GET(self):
        return "called version 1 /foo"
    def GET_v2(self):
        return "called version 2 /foo"
```

Then, your call requests would be translated like this:

    GET / with Accept: */*;version=v1 -> controllers.Default.GET()
    GET /foo with Accept: */*;version=v1 -> controllers.Foo.GET()

    GET / with Accept: */*;version=v2 -> controllers.Default.GET_v2()
    GET /foo with Accept: */*;version=v2 -> controllers.Foo.GET_v2()


### CORS support

Endpoints has a `CorsMixin` you can add to your controllers to support [CORS requests](http://www.w3.org/TR/cors/):

```python
from endpoints import Controller, CorsMixin

class Default(Controller, CorsMixin):
    def GET(self):
        return "called / supports cors"
```

The `CorsMixin` will handle all the `OPTION` requests, and setting all the headers, so you don't have to worry about them (unless you want to).

### Yield support (experimental)

Want to defer some processing until after you have responded to the client? Then use yield in your controller:

```python
class Foo(Controller):
    def POST(self, **kwargs):
        # let the client know you got the stuff
        yield {'success': True}

        # do some other stuff with the received input
        for k, v in kwargs:
            do_something(k, v)
```

**NOTE** that this does not work with the WSGI interface and I'm not sure there is a way to make it work :(


### Built in servers

Endpoints comes with wsgi and [Python Simple Server](https://docs.python.org/2/library/basehttpserver.html) support.


#### Sample wsgi script for uWSGI

```python
import os
from endpoints.interface.wsgi import Server

os.environ['ENDPOINTS_PREFIX'] = 'mycontroller'
application = Server()
```

Yup, that's all you need to do to set it up, then you can start a [uWSGI](http://uwsgi-docs.readthedocs.org/) server to test it out:

    uwsgi --http :9000 --wsgi-file YOUR_FILE_NAME.py --master --processes 1 --thunder-lock --chdir=/PATH/WITH/YOUR_FILE_NAME/FILE


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

