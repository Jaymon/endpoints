# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import inspect

from decorators import FuncDecorator

#from ..exception import CallError, AccessDenied


logger = logging.getLogger(__name__)


"""
I'm not sure I can find a way to globally lock the methods to the right class
since they don't include the class they are defined in

http://stackoverflow.com/a/25959545/5006
http://stackoverflow.com/questions/961048/get-class-that-defined-method

here were some links on what I am trying to do
from Guido himself:
http://www.artima.com/weblogs/viewpost.jsp?thread=101605
http://www.artima.com/forums/flat.jsp?forum=106&thread=101605

builds on guido's ideas:
    http://www.ianbicking.org/more-on-multimethods.html

other examples:
    http://bob.ippoli.to/archives/2005/03/30/five-minute-multimethods-in-python-using-dispatch/
    http://stackoverflow.com/questions/22377338/how-to-write-same-name-methods-with-different-parameters-in-python
"""

class when(FuncDecorator):
    callbacks = {}
    def decorate(slf, func, callback, *args, **kwargs):
        slf.add_callback(func, callback)
        def decorated(self, *args, **kwargs):

            name = slf.format_name(self.__class__, func)
            pout.v(name, slf.callbacks)

            #pout.v(slf.callbacks[func.__name__])

            return func(self, *args, **kwargs)
            # TODO -- figure out how to set ETag
            #if not self.response.has_header('ETag')

        return decorated

    # there is a way to do this, save it globally under GET, and then when the actual
    # method is called, at that point I will have the class, once I have the class
    # can get it's class methods and match up the ids to the global GET methods, so
    # then I know which ones exist? Wait, but they will actually be hidden by the
    # decorator, so I might not be able to get them, bah

    def get_name(self, func):
        name = ""
        module = inspect.getmodule(func)
        _, line_i = inspect.getsourcelines(func)
        mod_lines, _ = inspect.getsourcelines(module)
        pout.v(mod_lines)


        #classes = (c for c in inspect.getmembers(module, inspect.isclass) if c[1].__module__ == module.__name__)
        from ..core import Controller
        def is_subcontroller(c):
            try:
                return issubclass(c, Controller)
            except TypeError:
                return False
        #classes = (c for c in inspect.getmembers(module, inspect.isclass))
        classes = (c for c in inspect.getmembers(module, is_subcontroller))
        for clsname, klass in classes:
            pout.v(inspect.getmro(klass))
            cls_lines, cls_line_i = inspect.getsourcelines(klass)
            pout.v(klass, line_i, cls_line_i, len(cls_lines))
            if line_i >= cls_line_i and line_i <= (cls_line_i + len(cls_lines)):
                name = self.format_name(klass, func)
                break

        return name

    def format_name(self, klass, func):
        name = "{}.{}".format(klass.__name__, func.__name__)
        return name

    def add_callback(self, func, callback):
        #pout.v(vars(func), dir(func), func)
        name = self.get_name(func)
        callbacks = self.callbacks
        callbacks.setdefault(name, [])
        callbacks[name].append({"func": func, "callback": callback})
        self.callbacks = callbacks
        #pout.v(func.__name__, func.__class__, callback)

