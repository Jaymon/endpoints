# Endpoints

Quickest API builder in the West! Lovingly crafted for [First Opinion](http://firstopinionapp.com/).

## Getting Started in 5 Minutes

### Installation

First, install endpoints with the following command.

    $ pip install endpoints

If you want the latest and greatest you can also install from source:

    pip install git+https://github.com/firstopinion/endpoints#egg=endpoints

**Note:** if you get the following error

    $ pip: command not found

you will need to install pip using the following command.

    $ sudo easy_install pip

### Set Up Your Controller File

Create a controller file with the following command:

    $ touch mycontroller.py

Add the following code to your new Controller file. These classes are examples of possible *endpoints*.

```python
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

### Set Up A Simple Python Server
Type the following commands to set a few environment variables for your server

    $ export ENDPOINTS_PREFIX=mycontroller
    $ export ENDPOINTS_SIMPLE_HOST=localhost:8000

Now create a server file:

    $ touch myserver.py

and add the necessary code to run a simple server:

```python
import os

from endpoints.interface.simple import Server

s = Server()
s.serve_forever()
```

Start your server file:

    $ python myserver.py

## How does it work?

*Endpoints* translates requests to python modules without any configuration.

It uses the following convention.

    METHOD /module/class/args?kwargs

Endpoints will use the base module you set as a reference point to find the correct submodule using the path specified by the request.

Requests are translated from the left bit to the right bit of the path.
So for the path `/foo/bar/che/baz`, endpoints would check for the `foo` module, then the `foo.bar` module, then the `foo.bar.che` module, etc. until it fails to find a valid module.

Once the module is found, endpoints will then attempt to find the class with the remaining path bits. If no class is found the class named `Default` will be used.

This makes it easy to bundle your controllers into something like a "Controllers" module.

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

As shown above, we see that **endpoints essentially travels the path from the base module down to the appropriate submodule according to the request given.**

### Example

Let's say your site had the following setup:

    site/controllers/__init__.py

and the file `controllers/__init__.py` contained:

```python
from endpoints import Controller

class Default(Controller):
  def GET(self):
    return "called /"

class Foo(Controller):
  def GET(self):
    return "called /foo"
```

then your call requests would be translated like this:

|HTTP Request   | Path Followed             |
|-------------- | ------------------------- |
|GET /          | controllers.Default.GET() |
|GET /foo       | controllers.Foo.GET()     |

### Try it!
Run the following requests on the simple server you created. You should see the following output following each request.

    $ curl "http://localhost:8000/"
    boom
    $ curl "http://localhost:8000/foo"
    bang
    $ curl -H "Content-Type: application/json" -d '{"name": "world"}'
    "http://localhost:8000/"
    hello world

Can you figure out what path endpoints was following in each request?

We see in the ***first request*** that the Controller module was accessed, then the Default class, and then the GET method.

In the ***second request***, the Controller module was accessed, then the Foo class as specified, and then the GET method.

Finally, in the ***last request***, the Controller module was accessed, then the Default class, and finally the POST method with the passed in argument as JSON.

## Fun with parameters, decorators, and more

If you have gotten to this point, congratulations. You understand the basics of endpoints. If you have gotten to this point, and still don't understand endpoints then please go back and make sure you do before reading any further.

There are a few tricks and features of endpoints that are important to cover as they will add *fun*ctionality to your program.

### Handling path parameters and query vars

You can define your controller methods to accept certain path params and to accept query params:

```python
class Foo(Controller):
  def GET(self, one, two=None, **params): pass
  def POST(self, **params): pass
```

your call requests would be translated like this:

|HTTP Request                           | Path Followed                                         |
|-------------------------------------- | ----------------------------------------------------- |
|GET /foo/one                           | controllers.Default.GET()                             |
|GET /foo/one?param1=val1&param2=val2   | prefix.Foo.GET("one", param1="val1", param2="val2")   |
|GET /foo                               | 404, no one path param                                |
|GET /foo/one/two                       | prefix.Foo.GET("one", "two")                          |

Post requests are also merged with the `**params` on the controller method, with the `POST` params taking precedence:

For example, if the HTTP request is:

    POST /foo?param1=GET1&param2=GET2 body: param1=POST1&param3=val3

The following path would be:

    prefix.Foo.POST(param1="POST1", param2="GET2", param3="val3")

### Handy decorators

The `endpoints.decorators` module gives you some handy decorators to make parameter handling and error checking easier:

For example, the `param` decorator can be used similarly to Python's built-in [argparse.add_argument()](https://docs.python.org/2/library/argparse.html#the-add-argument-method) method as shown below.

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @param('param1', default="some val")
  @param('param2', choices=['one', 'two'])
  def GET(self, **params): pass
```

Other examples of decorators include `get_param` and `post_param`. The former checks that a query parameter exists. The latter is only concerned with posted parameters.

There is also a `require_params` decorator that provides a quick way to ensure certain parameters were provided.

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @require_params('param1', 'param2', 'param3')
  def GET(self, **params): pass
```

The require_params decorator as used above will make sure `param1`, `param2`, and `param3` were all present in the `**params` dict.

#### Authentication

The `auth` decorator tries to make user authentication easier. It takes a **realm** and a **target** callback in order to perform the authentication.

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

    site/controllers/ __init__.py

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

|HTTP Request                           | Path Followed                 |
|-------------------------------------- | ----------------------------- |
|GET / with Accept: */*                 | controllers.Default.GET()     |
|GET /foo with Accept: */*              | controllers.Foo.GET()         |
|GET / with Accept: */*;version=v2      | controllers.Default.GET_v2()  |
|GET /foo with Accept: */*;version=v2   | controllers.Foo.GET_v2()      |

**Note:** attaching the `;version=v2` to the `Accept` header changes the method that is called to handle the request.

### CORS support

Endpoints has a `CorsMixin` you can add to your controllers to support [CORS requests](http://www.w3.org/TR/cors/):

```python
from endpoints import Controller, CorsMixin

class Default(Controller, CorsMixin):
  def GET(self):
    return "called / supports cors"


The `CorsMixin` will handle all the `OPTION` requests, and setting all the headers, so you don't have to worry about them (unless you want to).

## Built in servers

Endpoints comes with wsgi and [Python Simple Server](https://docs.python.org/2/library/basehttpserver.html) support.

### Sample wsgi script for uWSGI

```python
import os
from endpoints.interface.wsgi import Server

os.environ['ENDPOINTS_PREFIX'] = 'mycontroller'
application = Server()
```

That's all you need to set it up if you need it. Then you can start a [uWSGI](http://uwsgi-docs.readthedocs.org/) server to test it out:

    uwsgi --http :9000 --wsgi-file YOUR_FILE_NAME.py --master --processes 1 --thunder-lock --chdir=/PATH/WITH/YOUR_FILE_NAME/FILE

## Development

### Unit Tests

To run the tests:

    python -m unittest endpoints_test

Check the `tests_require` parameter in the `setup.py` script to see what modules are needed to run the tests.

## License

MIT
