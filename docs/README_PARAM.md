# Parameters

You probably want to send some values to your server so _endpoints_ provides a helper decorator to make this process easier and customizable.


## param decorator

The **param** decorator tries to act very similar api to Python's built-in [argparse.add_argument method](https://docs.python.org/2/library/argparse.html#adding-arguments) but has a more limited vocabulary of flags you can set, but should feel familiar.

By default the **param** decorator checks both _GET_ and _POST_ values with _POST_ taking precedence, if you would like to only check _POST_ parameters, use the **post_param** decorator, if you only want to check _GET_ parameters, then use the **get_param** decorator.

The flags you can pass to the any of the decorators are:

* dest -- string -- the key in kwargs this param will be set into
* type -- type -- a python type like int or float
* action -- string --
    * store -- default
    * store_false -- set if you want default to be true, and false if param is passed in
    * store_true -- opposite of store_false
    * store_list -- set to have a value like 1,2,3 be blown up to ['1', '2', '3']
    * append -- if multiple param values should be turned into an array (eg, `foo=1&foo=2` would become `foo=[1, 2]`)
    * append_list -- it's store_list + append, so `foo=1&foo=2,3` would be `foo=[1, 2, 3]`
* default -- mixed -- the value that should be set if query param isn't there, if this is callable (eg, `time.time` or `datetime.utcnow`) then it will be called every time the decorated method is called
* required -- boolean -- True if param is required, default is true
* choices -- set() -- a set of values to be in tested against (eg, val in choices)
* allow_empty -- boolean -- True allows values like False, 0, '' through,
    default False, this will also let through any empty value that was set
    via the default flag
* max_size -- int -- the maximum size of the param
* min_size -- int -- the minimum size of the param
* regex -- regexObject -- if you would like the param to be validated with a regular exception, uses the `re.search()` method
* help -- string -- a helpful description for this param


Here's an example:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
    @param('bar', help="the bar of foo")
    @param('che', type=int, choices=[1, 2, 3], help="The specific che you want")
    @param('baz', required=False, help="You don't need to pass up a baz")
    @param('bam', default="bang", help="the bam you want, defaults to bang")
    def POST(self, **kwargs):
        pass
```

Another example:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
  @param('param1', default="some val")
  @param('param2', choices=['one', 'two'])
  def GET(self, **params): pass
```


### Positional arguments

What happens if you want to pass up values in the path part of the url (eg, the _/foo/bar_ part of _http://example.com/foo/bar_ url?). You can use integers in place of the name value of the param, like so:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
    @param(0, help="this will be in args[0]")
    @param(1, type=int, choices=[1, 2, 3], help="this will be in args[1]")
    @param('bar', help="this will be in kwargs['bar']")
    def POST(self, *args, **kwargs):
        pass
```


### Lists

Sometimes you need to send up a list of something:

```
http://example.com/foo?bar=1,2,3,4,5
```

You can do that using the `append_list` action:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
    @param('bar', action="append_list", help="kwargs['bar'] will contain [1, 2, 3, 4, 5]")
    def POST(self, **kwargs):
        pass
```


### Empty values

By default, _endpoints_ isn't wild about empty values (eg, `""`) and it treats them as a bad request, but if you are planning on sending those values up you can tell _endpoints_ that they are ok:

```python
from endpoints import Controller
from endpoints.decorators import param

class Foo(Controller):
    @param('bar', allow_empty=True, help="bar can now contain empty string")
    def POST(self, **kwargs):
        pass
```


## get_param decorator

Same as **param** but only checks **GET** query arguments passed in the actual url:

```python
from endpoints import Controller
from endpoints.decorators import get_param

class Foo(Controller):
    @get_param('bar', help="the ?bar=... part of the url")
    def GET(self, **kwargs):
        pass
```


## post_param decorator

Same as **param** but only checks **POST** body arguments posted to the given url.

```python
from endpoints import Controller
from endpoints.decorators import post_param

class Foo(Controller):
    @post_param('bar', help="must be sent in the body of the request")
    def POST(self, **kwargs):
        pass
```


## require_params decorator

There is also a `require_params` decorator that provides a quick way to ensure certain parameters were provided.

```python
from endpoints import Controller
from endpoints.decorators import require_params

class Foo(Controller):
  @require_params('param1', 'param2', 'param3')
  def GET(self, **params): pass
```

The require_params decorator as used above will make sure `param1`, `param2`, and `param3` were all present in the `**params` dict.

