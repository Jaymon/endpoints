# Endpoints Template Support

This uses [Jinja2](https://jinja.palletsprojects.com/) for templating templating.

You can install all the dependencies for this module using pip:

```bash
$ pip install endpoints[template]
```


## Template Folder

You can place all your template files in a directory and then add an environment variable so Endpoints can pick it up:

```bash
export ENDPOINTS_TEMPLATE_PATH="/path/to/template/files"
```

You can specify multiple paths by using the operating system's path separator (which on Linux and macOS is the colon):

```bash
export ENDPOINTS_TEMPLATE_PATH="/path/1/to/templates:/path/2/to/templates"
```


## Template Controller Decorator

Once you have your templates created, you can access them using the `template` decorator on a Controller method:

```python
from endpoints import Controller
from endpoints.extras.template import template


class Default(Controller):
    @template("<TEMPLATE_NAME>")
    def GET(self):
        return {
            "foo": "bar"
        }
```

The values returned from the controller's `GET` method will be passed to the `<TEMPLATE_NAME>` template and the rendered html will be returned to the client.