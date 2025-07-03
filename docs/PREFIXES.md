# Controller Prefixes

The controller prefix is a [module search path](https://docs.python.org/3/tutorial/modules.html#the-module-search-path) that tells Endpoints where you have defined all your [Controllers](CONTROLLERS.md).

Endpoints will only route to Controllers defined in these prefixes. If no prefixes are defined Endpoints will check the current working directory for an importable `controllers` module.


## Defining Controller prefixes

Define controller prefixes is to set the environment variable `ENDPOINTS_PREFIX`, for example:

	$ export ENDPOINTS_PREFIX=controllers

Now, when Endpoints is started it would route to any Controller class found in the `controllers` python module.


### Multiple Controller Prefixes

You can define multiple controller prefixes through the environment also:

	$ export ENDPOINTS_PREFIX=foo.controllers:bar.controllers
