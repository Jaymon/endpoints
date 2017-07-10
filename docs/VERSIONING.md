# Versioning


Endpoints has built-in support for `Accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).


### Versioning requests

You can activate versioning by using the `@version` decorator on your Controller methods. So, let's say you have a `controllers.py` which contained:


```python
# controllers.py
from endpoints import Controller
from endpoints.decorators import version

class Default(Controller):
  @version("", "v1") # handle any requests with no version or with v1
  def GET_1(self):
    return "called version 1 /"

  @version("v2") # handle any requests with version v2
  def GET_2(self):
    return "called version 2 /"

class Foo(Controller):
  @version("v1")
  def GET_1(self):
    return "called version 1 /foo"

  @version("v2")
  def GET_2(self):
    return "called version 2 /foo"
```

Now, your call requests would be translated like this:

|HTTP Request                                    | Path Followed                   |
|----------------------------------------------- | ------------------------------- |
|GET / with header `Accept: */*`                 | controllers.Default.GET_1()     |
|GET / with header `Accept: */*;version=v2`      | controllers.Default.GET_2()     |
|GET /foo with header `Accept: */*;version=v1`   | controllers.Foo.GET_1()         |
|GET /foo with header `Accept: */*;version=v2`   | controllers.Foo.GET_2()         |
|GET /foo with header `Accept: */*`              | Raises error                    |

Notice how modifying the _Accept_ header changes the method that is called to handle the request.

