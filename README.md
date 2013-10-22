# Endpoints

Quickest api builder in the west!

## How does it work?

`endpoints` translates requests to python modules without any configuration. It uses the convention:

    METHOD /module/class/args?kwargs

To find the modules, you assign a base module that endpoints will use as a reference point to find the correct submodule using the path. This makes it easier to bundle your controllers into something like a `controllers` module. Some examples of how http requests would be interpretted:

    GET / -> prefix.Default.GET()
    GET /foo -> prefix.foo.Default.GET()
    POST /foo/bar -> prefix.foo.Bar.POST()
    GET /foo/bar/che -> prefix.foo.Bar.GET(che)
    POST /foo/bar/che?baz=foo -> prefix.foo.Bar.POST(che, baz=foo)

Endpoints works from left bit to right bit of the path (so /foo/bar/che/baz, Endpoints would check for `foo` module, then `foo.bar` module, then `foo.bar.che` module, etc. until it fails to find a valid module). Once the module is found, endpoints will then attempt to find the class with the remaining path bits, if no class is found, `Default` will be used.

**todo, add better examples and examples of glue code to use endpoints in your project**

The `example` directory has a little server that will demonstrate how endpoints works, you can run it:

    $ cd /path/to/endpoints/example
    $ python server.py

Then, in another terminal window:

    $ curl http://localhost:8000
    $ curl http://localhost:8000/foo

### Versioning requests

Endpoints has support for `Accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).

**todo, add examples of versioning**

**todo, move our auth_basic, and auth_oauth decorators into a decorators sub module?** Only problem I see with this is doing the actual authentication, so there needs to be a way for the module to call another method and return if it is valid, not sure how we would want to make that generic

**todo, move the require_params decorator into a decorators sub module** - no reason for this one to be private

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

