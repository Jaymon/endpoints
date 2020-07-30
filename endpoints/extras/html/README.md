# Endpoints HTML Support

This uses [Jinja2](https://jinja.palletsprojects.com/) for HTML templating.

You can install all the dependencies for this module using pip:

```bash
$ pip install endpoints[html]
```

## Template Folder

You can place all your template files (which should end with `.html`) in a directory and then add an environment variable so Endpoints can pick it up:

```bash
export ENDPOINTS_HTML_TEMPLATE_PATH="/your/path/to/html/template/files"
```

## View Decorator

Once you have your templates created, you can access them using the `view` decorator on a Controller:

```python
from endpoints import Controller
from endpoints.extras.html import view


class Default(Controller):
    @view("<TEMPLATE_NAME>")
    def GET(self):
        return {
            "foo": "bar"
        }
```

The values returned from the `GET` method will be passed to the `<TEMPLATE_NAME>` template and the rendered html will be returned to the client.