# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from ...compat import *
from ...decorators import FuncDecorator
from ...utils import MimeType, String
from .core import Templates


class view(FuncDecorator):
    """take the controller's returned value and template it using the passed in
    template_name, which does not need an extension

    :Example:
        class Default(Controller):
            @html("foo")
            def GET(self, **kwargs):
                return kwargs
    """
    template_class = Templates

    def decorate(self, f, template_name, **kwargs):

        template_class = kwargs.pop("template_class", self.template_class)
        directories = kwargs.pop("directories", None)
        renderer = template_class(directories)
        content_type = MimeType.find("html")

        def decorated(self, *args, **kwargs):
            request = self.request

            response = self.response
            response.set_header("Content-Type", content_type)

            # let's convert the controller's return value into actual html
            d = f(self, *args, **kwargs)

            d.setdefault("template_name", template_name)
            d.setdefault("controller", self)
            d.setdefault("request", request)
            d.setdefault("response", response)

            return renderer.render(template_name, d)

        return decorated

