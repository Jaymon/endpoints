# Parameters

At some point, you'll probably want to send some values to your server so _endpoints_ supports Python annotations of the method signature to make sure you get the parameters you want.

Endpoints uses the annotations to cast the passed up value to match the given annotation so make sure the annotation, when called, can accept the raw value. Whatever is returned from the type annotation is passed to the method.

Here's an example:

```python
from typing import Literal
from endpoints import Controller

class Foo(Controller):
    async def POST(
        self,
        bar, 
        che: Literal[1, 2, 3],
        baz: bool = False,
        bam: str = "bang"
    ):
        """
        :param bar: the bar of foo
        :param che: The specific che you want
        :param baz: You don't need to pass up a baz
        :param bam: the bam you want, defaults to bang
        """
        pass
```

Another example:

```python
from endpoints import Controller

class Param2(str):
    def __new__(cls, v):
        if v not in ["one", "two"]:
            raise ValueError(v)
        
        return super().__new__(cls, v)

class Foo(Controller):
    async def GET(self, param1="some val", param2: Param2):
        pass
```


### Positional arguments

What happens if you want to pass up values in the path part of the url (eg, the _/foo/bar_ part of a _http://example.com/foo/bar_ url)? You can do that like this:

```python
from endpoints import Controller

class Foo(Controller):
    async def POST(self, bar, che, /, bam):
        """
        `bar` and `che` need to be passed up in the url path, while `bam` 
        can be passed up in the query string:
        
            /foo/<BAR>/<CHE>?bam=<BAM>
        pass
```


### Lists

Sometimes you need to send up a list of something:

```
http://example.com/foo?bar=1,2,3,4,5
```

You can do that with something like:

```python
from endpoints import Controller

class Foo(Controller):
    async def POST(self, bar: list[int]):
        pass
```

And `bar` will contain `[1, 2, 3, 4, 5]`
