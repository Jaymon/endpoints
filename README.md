# Endpoints

Quickest API builder in the West! 

_Endpoints_ is a lightweight REST api framework written in python and used in multiple production systems that handle millions of requests daily.


## 5 Minute Getting Started

### Installation

First, install endpoints with the following command.

    $ pip install endpoints

If you want the latest and greatest you can also install from source:

    $ pip install -U "git+https://github.com/jaymon/endpoints#egg=endpoints"

**Note:** if you get the following error

    $ pip: command not found

you will need to [install pip](https://pip.pypa.io/en/stable/installing/).


### Set Up Your Controller File

Create a controller file with the following command:

    $ touch controllers.py

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


### Start a Server

Now that you have your `controllers.py`, let's use the built-in WSGI server to serve them, we'll set our `controllers.py` file as the [controller prefix](docs/PREFIXES.md) so Endpoints will know where to find the [Controller classes](docs/CONTROLLERS.md) we just defined:

    $ endpoints --prefix=controllers --host=localhost:8000


### Test it out

Using curl:

    $ curl http://localhost:8000
    "boom"
    $ curl http://localhost:8000/foo
    "bang"
    $ curl http://localhost:8000/ -d "name=Awesome you"
    "hello Awesome you"

That's it. Easy peasy!

Can you figure out what path endpoints was following in each request?

We see in the ***first request*** that the Controller module was accessed, then the Default class, and then the GET method.

In the ***second request***, the Controller module was accessed, then the Foo class as specified, and then the GET method.

Finally, in the ***last request***, the Controller module was accessed, then the Default class, and finally the POST method with the passed in argument as JSON.


## How does it work?

*Endpoints* translates requests to python modules without any configuration.

It uses the following convention.

    METHOD /module/class/args?kwargs

_Endpoints_ will use the base module you set as a reference point to find the correct submodule using the path specified by the request.

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


### One more example

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

If you have gotten to this point, congratulations. You understand the basics of endpoints. If you don't understand endpoints then please go back and read from the top again before reading any further.


## Learn more about Endpoints

Now you should dive into some of the other features discussed in the [docs folder](https://github.com/jaymon/endpoints/tree/master/docs).

