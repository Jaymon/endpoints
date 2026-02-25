# Rate Limiting

Rate limiting certain resources is pretty common and so _endpoints_ provides [helper decorators](https://github.com/Jaymon/endpoints/blob/master/endpoints/decorators/limit.py) to make this process easier and customizable.


## Example

Want to restrict how many times a certain ip address can access a resource?

```python
# controller.py

from endpoints import Controller
from endpoints.decorators.limit import RateLimitDecorator


class ratelimit_ip(RateLimitDecorator):
    async def get_key(self, controller, *args, **kwargs):
        return controller.request.ip_address


class Default(Controller):
    @ratelimit_ip(limit=10, ttl=3600)
    async def GET(self):
        return "hello world"
```

That's it, now any unique ip request to `/` will be limited to 10 request every hour (3600 seconds)


## Customization

You can extend any of the limit decorators to fit them into your own system or create your own using `RateLimitDecorator`:

```python
from endpoints import Controller
from endpoints.decorators.limit import RateLimitDecorator


class limit_user(RateLimitDecorator):
    async def get_key(self, controller, *args, **kwargs):
        user = await magic_call_returning_a_user_from_request(controller.request)
        return user.id if user else ""


class Default(Controller):
    @limit_user
    async def GET(self):
        return "GET uses backend's default limit and ttl"

    @limit_user(5, 7200)
    async def POST(self):
        return "POST users limit and ttl passed into backend"
```
