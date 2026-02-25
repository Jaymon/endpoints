_Endpoints_ supports the [asgi](https://asgi.readthedocs.io/en/latest/specs/main.html) and [wsgi](https://peps.python.org/pep-3333/) protocols.

You'll want to create an entry script:

```python
# web.py

from endpoints import Application

application = Application(controller_prefixes=["controller"])
```


That's all you need to make it work. 

You could use this file with something like the [uWSGI](http://uwsgi-docs.readthedocs.org/) server to test it out:

    $ uwsgi --http :8000 --wsgi-file web.py --master --processes 1 --thunder-lock --chdir=.
