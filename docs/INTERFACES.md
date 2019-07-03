# Interfaces

## Creating a new web interface

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


## Creating a new websocket interface

You can create a new websocket interface using `endpoints.interface.BaseWebsocketServer` which has some other methods that you can hook into to customize functionality:

* `create_websocket_request`
* `create_websocket_response_body`
* `connect_websocket_call`
* `create_websocket_call`
* `disconnect_websocket_call`

These are all already implemented but you can override them in order to customize how your websocket interface works. You can take a look at their method signatures in the code if you need to override them.


### Payload class

The `endpoints.interface.Payload` class is used by the `BaseWebsocketServer` to translate requests and responses to and from something that can be passed around.

You can customize this class by creating an object that has `dumps` and `loads` class methods and then setting it:

```python
import json

from endpoints interface import BaseWebsocketServer


class JSONPayload(object):
    @classmethod
    def loads(cls, raw):
        return json.loads(raw)

    @classmethod
    def dumps(cls, kwargs):
        return json.dumps(kwargs)


class WebsocketServer(BaseWebsocketServer):
    payload_class = JSONPayload
```
