# Controllers

The **Controller** is the heart of _Endpoints_. Every request will go through a controller class.


## Create your first controller class

Create a file named _controllers.py_ with the following contents:

```python
from endpoints import Controller

class Hello(Controller):
    def GET(self):
        return "hello world"
```

Now you can make a request:

    $ curl http://localhost:8000/hello
    "hello world"


Now let's try some different stuff:

    $ curl http://localhost:8000/hello -d "name=Alice"
    {"errno": 501, "errmsg": "POST /hello not implemented"}

We received a 501 response because our `Hello` controller has no **POST** method, let's add one:

```python
from endpoints import Controller
from endpoints.decorators import param

class Hello(Controller):
    def GET(self):
        return "hello world"

    @param("name")
    def POST(self, **kwargs):
        return "hello {}".format(kwargs["name"])
```

Let's see if it worked:

    $ curl http://localhost:8000/hello -d "name=Alice"
    "hello Alice"


Nice, but now we want to be even more clever, we want **GET** to act differently depending on who has signed in:


```python
from endpoints import Controller
from endpoints.decorators.auth import basic_auth
from endpoints.decorators import route

class auth(basic_auth):
    def target(self, request, username, password):
        ret = False
        if username == "Alice" and password == "1234":
            request.username = "Alice"
            ret = True
        elif username == "Bob" and password == "5678":
            request.username = "Bob"
            ret = True
        return ret


class Hello(Controller):
    @auth()
    @route(lambda request: request.username == "Alice")
    def GET_alice(self):
        return "hello Alice"

    @auth()
    @route(lambda request: request.username == "Bob")
    def GET_bob(self, **kwargs):
        return "hola Bob"
```

Let's see it in action:

    $ curl -v "http://localhost:8000/hello" -u "Alice:1234"
    "hello Alice"
    $ curl -v "http://localhost:8000/hello" -u "Bob:5678"
    "hola Bob"


Hopefully that gives you a feel for how to define your own controllers and some of the ways you can customize them.


### Handling path parameters and query vars

You can define your controller methods to accept certain path params and to accept query params:

```python
class Foo(Controller):
  def GET(self, one, two=None, **params): pass
  def POST(self, **params): pass
```

your call requests would be translated like this:

|HTTP Request                           | Path Followed                                              |
|-------------------------------------- | ---------------------------------------------------------- |
|GET /foo/one                           | controllers.Default.GET()                                  |
|GET /foo/one?param1=val1&param2=val2   | controllers.Foo.GET("one", param1="val1", param2="val2")   |
|GET /foo                               | 405, no `one` path param to pass to GET                    |
|GET /foo/one/two                       | controllers.Foo.GET("one", "two")                          |

Post requests are also merged with the `**params` on the controller method, with the `POST` params taking precedence:

For example, if the HTTP request is:

    POST /foo?param1=GET1&param2=GET2 with body: param1=POST1&param3=val3

The following path would be:

    prefix.Foo.POST(param1="POST1", param2="GET2", param3="val3")


### CORS support

Every _Endpoints_ Controller has [Cors support](http://www.w3.org/TR/cors/) by default. This support will handle all the `OPTION` requests, and setting all the appropriate headers, so you don't have to worry about them (unless you want to).
You can turn Cors support off by setting `cors = False` on the Controller:

```python
from endpoints import Controller

class Default(Controller):

  cors = False # Turn off cors

  def GET(self):
    return "This will not have CORS support"
```

