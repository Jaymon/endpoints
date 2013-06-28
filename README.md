# Endpoints

Trying to make creating an API as simple as possible

## How does it work?

`endpoints` translates requests to python modules without any configuration. It uses the convention:

    METHOD /module/class/args?kwargs

To find the modules, you can assign a module prefix, to make it easier to bundle your controllers to something like a `controllers` module. Some examples of how http requests would be interpretted:

    GET /foo -> prefix.foo.Default.get()
    POST /foo/bar -> prefix.foo.Bar.post()
    GET /foo/bar/che -> prefix.foo.Bar.get(che)
    POST /foo/bar/che?baz=foo -> prefix.foo.Bar.post(che, baz=foo)

**todo, add better examples and examples of glue code to use endpoints in your project**

### Versioning requests

Endpoints has support for `accept` [header](http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html) versioning, inspired by this [series of blog posts](http://urthen.github.io/2013/05/09/ways-to-version-your-api/).

**todo, add examples of versioning**

## Install

Use PIP

    pip install git+https://github.com/firstopinion/endpoints#egg=endpoints


### To run tests

To run the tests, you'll also need to install the `testdata` module: 

    pip install git+https://github.com/Jaymon/testdata#egg=testdata

To run the tests:

    python endpoints_test.py

