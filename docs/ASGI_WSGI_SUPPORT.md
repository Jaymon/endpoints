_Endpoints_ supports the asgi and wsgi protocols.


## ASGI

Example asgi script:

```python
from endpoints.interface.asgi import Application

application = Application(controller_prefixes=["controllers"])
```


## WSGI

Create a file named something like `wsgi.py` with:

```python
from endpoints.interface.wsgi import Application

application = Application(controller_prefixes=["controllers"])
```

That's all you need to make it work. 

You could use this file with something like the [uWSGI](http://uwsgi-docs.readthedocs.org/) server to test it out:

    $ uwsgi --http :8000 --wsgi-file wsgi.py --master --processes 1 --thunder-lock --chdir=.


