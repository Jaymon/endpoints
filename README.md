# Endpoints

Quickest api builder in the west, maybe even the world!

## How does it work?

`endpoints` translates requests to python modules without any configuration. It uses the convention:

    METHOD /module/class/args?kwargs

To find the modules, you can assign a module prefix, to make it easier to bundle your controllers to something like a `controllers` module. Some examples of how http requests would be interpretted:

    GET /foo -> prefix.foo.Default.GET()
    POST /foo/bar -> prefix.foo.Bar.POST()
    GET /foo/bar/che -> prefix.foo.Bar.GET(che)
    POST /foo/bar/che?baz=foo -> prefix.foo.Bar.POST(che, baz=foo)

**todo, add better examples and examples of glue code to use endpoints in your project**

The `example` directory has a little server that will demonstrate how endpoints works, you can run it:

    $ cd /path/to/endpoints/example
    $ python server.py

Then, in another terminal window:

    $ curl http://localhost:8000
    $ curl http://localhost:8000/foo

### Versioning requests

Endpoints has support for `accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).

**todo, add examples of versioning**

## Install

Use PIP

    pip install endpoints

If you want the latest and greatest, you can also install from source:

    pip install git+https://github.com/firstopinion/endpoints#egg=endpoints

### To run tests

To run the tests, you'll also need to install the `testdata` module: 

    pip install testdata

To run the tests:

    python -m unittest endpoints_test

