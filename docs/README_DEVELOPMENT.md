# Development

## Unit Tests

After cloning the repo, `cd` into the repo's directory and run:

    $ python -m unittest endpoints_test

Check the `tests_require` parameter in the `setup.py` script to see what modules are needed to run the tests because there are dependencies that the tests need that the rest of the package does not.


## Refreshing server on file change

If you are manually testing, `entr` (run arbitrary commands when files change) might be handy, it can be installed on Ubuntu via apt-get:

    $ apt-get install entr

and used with endpoints like so:

    $ ls -d * | entr sh -c "killall endpoints; endpoints --prefix=mycontroller --host=localhost:8000 &"

Hat tip to [Mindey](https://github.com/firstopinion/endpoints/issues/57) for this command.

