# Controller Prefixes

The controller prefix is a [module search path](https://docs.python.org/3/tutorial/modules.html#the-module-search-path) that tells Endpoints where you have defined all your [Controllers](CONTROLLERS.md).

Endpoints will only route to Controllers defined in these prefixes.


## Defining Controller prefixes

Define controller prefixes is to set the environment variable `ENDPOINTS_PREFIX`, for example:

	$ export ENDPOINTS_PREFIX=controllers

Now, when Endpoints is started it would route to any Controller class found in the `controllers` python module.


### Multiple Controller Prefixes

You can define multiple controller prefixes through the environment also:

	$ export ENDPOINTS_PREFIX_1=foo.controllers
	$ export ENDPOINTS_PREFIX_2=bar.controllers

Endpoints will check ENDPOINTS_PREFIX_1 through ENDPOINTS_PREFIX_N as long as there is no break (ie, you can't set ENDPOINTS_PREFIX_1 and then ENDPOINTS_PREFIX_3 and expect ENDPOINTS_PREFIX_3 to be found).