# -*- coding: utf-8 -*-
import os
import logging

from jinja2 import Environment, FileSystemLoader

from ...compat import *
from ...config import environ
from ...utils import Path


logger = logging.getLogger(__name__)


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
        if directories:
            directories = [Path(d) for d in directories]

        else:
            directories = []
            for d in environ.paths("TEMPLATES_PATH"):
                directories.append(Path(d))

        self.directories = directories

        # https://jinja.palletsprojects.com/en/master/api/#jinja2.Environment
        self.interface = Environment(
            loader=FileSystemLoader(self.directories),
            lstrip_blocks=kwargs.pop("lstrip_blocks", True),
            trim_blocks=kwargs.pop("trim_blocks", True),
        )

    def get_template_name(self, template_name):
        return template_name

    def render(self, template_name, d=None, **kwargs):
        """
        https://jinja.palletsprojects.com/en/master/api/#jinja2.Template.render
        """
        d = d or {}
        d.update(kwargs)
        template_name = self.get_template_name(template_name)
        tmpl = self.interface.get_template(template_name)

        logger.debug(f"Response template: {template_name}")
        html = tmpl.render(**d)
        return html

    def has(self, template_name):
        template_name = self.get_template_name(template_name)
        for template_dir in self.directories:
            if template_dir.has_file(template_name):
                return True
        return False

