# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging


# configure root endpoints logging handler to avoid "No handler found" warnings.
# this has to go before importing child modules to make sure they don't configure
# their loggers before Null logger is added
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


from .reflection import Reflect, ReflectController, ReflectMethod
from .exception import (
    CallError,
    Redirect,
    CallStop,
    AccessDenied,
    CloseConnection,
)
from .http import Request, Response, Url
from .utils import AcceptHeader
from .call import Controller, Router, Call
from . import decorators
from .decorators import param, route, version # this is for fluidity/convenience


__version__ = '4.0.4'

