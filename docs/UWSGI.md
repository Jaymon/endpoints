# uWSGI

_Endpoints_ can work with the [uWSGI project](https://uwsgi-docs.readthedocs.io/en/latest/).


### Sample wsgi script for uWSGI

Create a file named _server.py_ with contents:

```python
import os
from endpoints.interface.wsgi import Application

os.environ['ENDPOINTS_PREFIX'] = 'controllers'
application = Application()
```

That's all you need to make it work. Then you can start a [uWSGI](http://uwsgi-docs.readthedocs.org/) server to test it out:

    $ uwsgi --http :8000 --wsgi-file server.py --master --processes 1 --thunder-lock --chdir=.


