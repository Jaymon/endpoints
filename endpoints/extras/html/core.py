# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

from jinja2 import Environment, FileSystemLoader

from ...compat import *
from ... import environ
from ...utils import Path, String


class Templates(object):
    """Handles Jinja2 template rendering

    Based on code originally from bang.config.Theme

    Template functionality is a thin wrapper around Jinja functionality that
    handles templating things

    Jinja docs:
        http://jinja.pocoo.org/docs/dev/
        https://jinja.palletsprojects.com/en/master/api/

    Jinja template syntax documentation:
        https://jinja.palletsprojects.com/en/master/templates/
    """
    def __init__(self, directories=None, **kwargs):

        if not directories:
            directories = list(environ.paths("HTML_TEMPLATE_PATH")) + list(environ.paths("HTML_TEMPLATE_DIR"))
        self.directories = [Path(d) for d in directories]

        # https://jinja.palletsprojects.com/en/master/api/#jinja2.Environment
        self.interface = Environment(
            loader=FileSystemLoader(self.directories),
            #extensions=['jinja2.ext.with_'] # http://jinja.pocoo.org/docs/dev/templates/#with-statement
            lstrip_blocks=kwargs.pop("lstrip_blocks", True),
            trim_blocks=kwargs.pop("trim_blocks", True),
        )

        self.templates = {}
        for d in self.directories:
            for f in d.rglob("*.html"):
                rel_f = f.relative_to(d)
                #fileroot, fileext = os.path.splitext(rel_f)
                self.templates[rel_f] = f

    def get_template_name(self, template_name):
        if not template_name.endswith(".html"):
            template_name += ".html"
        return template_name

    def render(self, template_name, d=None, **kwargs):
        """
        https://jinja.palletsprojects.com/en/master/api/#jinja2.Template.render
        """
        d = d or {}
        d.update(kwargs)

        tmpl = self.interface.get_template(self.get_template_name(template_name))
        html = tmpl.render(**d)
        return html

    def has(self, template_name):
        """Return True if template_name exists"""
        return self.get_template_name(template_name) in self.templates

