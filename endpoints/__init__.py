import logging
from logging import NullHandler

from .reflection import Reflect
from .exception import CallError, Redirect, CallStop, AccessDenied
from .http import Request, Response, Url
from .utils import AcceptHeader
from .call import Controller, Router
from . import decorators


# configure root endpoints logging handler to avoid "No handler found" warnings.
# I got this from requests module
logger = logging.getLogger(__name__)
if logger.handlers:
    logger.addHandler(NullHandler())
del(logger)


__version__ = '1.1.24'

