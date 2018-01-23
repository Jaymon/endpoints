# Example

This is just a simple example to demonstrate how Endpoints handles requests.

* Start the server

        $ python server.py


* Make some requests

        $ curl -v http://localhost:8000/
        $ curl -v http://localhost:8000/cors
        $ curl -v http://localhost:8000/foo
        $ curl -v -d '{"foo": "bar"}' "http://localhost:8000/cors"

* Kill the server with ctrl-c

