# Interfaces

## Creating a new interface

You can start with a template like this:

```python
from endpoints.interface import BaseServer


class Server(BaseServer):
    backend_class = None
    """the supported server's interface, there is no common interface for this class.
    Basically it is the raw backend class that the BaseServer child is translating
    for endpoints compatibility"""

    @property
    def hostloc(self):
        """Return host:port string that the server is using to answer requests"""
        raise NotImplementedError()

    def create_backend(self, **kwargs):
        """create instance of the backend class.

        Endpoints works by translating incoming requests from this instance to something
        endpoints understands in create_request() and then translating the response
        from endpoints back into something the backend understands in handle_request()

        :returns: mixed, an instance of the backend class
        """
        return self.backend_class(**kwargs)

    def create_request(self, raw_request, **kwargs):
        """convert the raw interface raw_request to a request that endpoints understands

        :params raw_request: mixed, this is the request given by backend
        :params **kwargs:
        :returns: an http.Request instance that endpoints understands
        """
        raise NotImplementedError()

    def handle_request(self):
        """this should be able to get a raw_request, pass it to create_call(),
        then use the Call instance to handle the request, and then send a response
        back to the backend
        """
        raise NotImplementedError()
```

These are the methods your new interface will need to define in order to work with Endpoints.

You can look at the current built-in supported interfaces in `endpoints.interface` to see how they implemented the above `Server` class.
