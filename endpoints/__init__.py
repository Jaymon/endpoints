import logging
#from logging import NullHandler

from .reflection import Reflect, ReflectController, ReflectMethod
from .exception import CallError, Redirect, CallStop, AccessDenied
from .http import Request, Response, Url
from .utils import AcceptHeader
from .call import Controller, Router, Call
from . import decorators


# configure root endpoints logging handler to avoid "No handler found" warnings.
logger = logging.getLogger(__name__)
if logger.handlers:
    logger.addHandler(logging.NullHandler())
del(logger)


__version__ = '2.0.0'

