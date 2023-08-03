# Routing

For the most part, routing is automatic depending on what you name your controllers, so you should understand how controllers work first:

[README about controllers](https://github.com/firstopinion/endpoints/blob/master/docs/CONTROLLERS.md)


## The Route Decorator

You can have different controller methods (eg, **GET**, **POST**) handle a given request depending on the request by using the `@route` decorator on your various Controller methods. So, let's say you have a `controllers.py` which contained:

```python
# controllers.py
from endpoints import Controller
from endpoints.decorators import route

class Default(Controller):
    # this GET will handle / requests
    @route(lambda req: len(req.path_args) == 0)
    async def GET_1(self, username):
        return "/"

    # this GET will handle /:uid/:title requests
    @route(lambda req: len(req.path_args) == 2)
    async def GET_2(self, uid, title):
        return "/:uid/:title"

    # this GET will handle /:username requests
    @route(lambda req: len(req.path_args) == 1)
    async def GET_3(self, username):
        return "/:username"
```

Now, your call requests would be translated like this:

|HTTP Request           | Path Followed                   |
|---------------------- | ------------------------------- |
|GET /                  | controllers.Default.GET_1()     |
|GET /foo               | controllers.Default.GET_2()     |
|GET /foo/bar           | controllers.Default.GET_3()     |


We used `lambda` in the example but the `@route` decorator can take any callable, as long as that callable takes one parameter (the Request instance) and returns a boolean (True if the decorated method should handle the request, False otherwise).

