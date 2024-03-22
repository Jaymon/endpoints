# -*- coding: utf-8 -*-
import os

from ...compat import *
#from ...decorators import FuncDecorator
from ...decorators import ControllerDecorator
from ...utils import MimeType, String
from .core import Templates


class template(ControllerDecorator):
    """take the controller's returned value and template it using the passed in
    template_name, which does not need an extension

    :Example:
        class Default(Controller):
            @template("foo.html")
            def GET(self, **kwargs):
                return kwargs
    """
    render_class = Templates

    def definition(self, template_name, **kwargs):
        self.template_name = template_name

        template_class = kwargs.pop("render_class", self.render_class)
        directories = kwargs.pop("directories", None)
        self.renderer = template_class(directories)

        _, ext = os.path.splitext(template_name)
        if ext:
            ext = ext.strip(".")

        else:
            ext = "html"

        self.content_type = kwargs.pop("content_type", MimeType.find(ext))

        return super().definition(**kwargs)

    async def handle(self, controller, **kwargs):
        controller.response.set_header("Content-Type", self.content_type)

    async def get_response_body(self, controller, body):
        # let's return the rendered template using whatever the controller
        # method gave us

        template_name = self.template_name

        d = {
            "template_name": template_name,
            "controller": controller,
            "request": controller.request,
            "response": controller.response,
        }

        d.update(body)
        return self.renderer.render(template_name, d)

