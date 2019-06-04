# Interfaces

## Creating a new interface

You can start with a template like this:

```python
from .. import BaseServer


class Server(BaseServer):
    backend_class = None
    """the supported server's interface, there is no common interface for this class.
    Basically it is the raw backend class that the BaseServer child is translating
    for endpoints compatibility"""

    def create_backend(self, **kwargs):
        return self.backend_class(**kwargs)

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands"""
        raise NotImplementedError()

    def handle_request(self):
        raise NotImplementedError()
```


