# Rate Limiting

Rate limiting certain resources is pretty common and so _endpoints_ provides [helper decorators](https://github.com/firstopinion/endpoints/blob/master/endpoints/decorators/limit.py) to make this process easier and customizable.


## Example

Want to restrict how many times a certain ip address can access a resource? Use the `endpoints.decorators.limit.ratelimit_ip` decorator:

```python
# controller.py

from endpoints import Controller
from endpoints.decorators.limit import ratelimit_ip


class Default(Controller):
    @ratelimit_ip(limit=10, ttl=3600)
    async def GET(self):
        return "hello world"
```

That's it, now any unique ip request to `/` will be limited to 10 request every hour (3600 seconds)


## The Limit Decorators

* `ratelimit_ip` - limit requests for a unique ip address.
* `ratelimit_param` - limit requests to a certain parameter.
* `ratelimit_param_ip` - limit requests to a certain parameter and a unique ip address.


## Customization

You can extend any of the limit decorators to fit them into your own system or create your own using `RateLimitDecorator`:

```python
from endpoints import Controller
from endpoints.decorators.limit import RateLimitDecorator, RateLimitBackend

class Backend(RateLimitBackend):
    DEFAULT_LIMIT = 10
    DEFAULT_TTL = 3600
    async def handle(self, request, key, limit, ttl):
        if not limit:
            limit = self.DEFAULT_LIMIT
        if not ttl:
            ttl = self.DEFAULT_TTL

        # check key to see if it should be rejected based on limit and ttl
        # and return True (the request is valid) or False (the request will
        # be denied)

class limit_user(RateLimitDecorator):
    backend_class = Backend

    async def normalize_key(self, request, *args, **kwargs):
        user = await some_call_that_returns_user_from_some_db_using_request_info(request)
        return user.id if user else ""

class Default(Controller):
    @limit_user
    async def GET(self):
        return "GET uses backend's default limit and ttl"

    @limit_user(5, 7200)
    async def POST(self):
        return "POST users limit and ttl passed into backend"
```
