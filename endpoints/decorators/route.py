# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import inspect
import re

from decorators import FuncDecorator

from ..exception import CallError


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
            ret_func = slf.find_func(self, func, args, kwargs)
            if not ret_func:
                raise CallError(404, "No matches for request were found")

            return ret_func(self, *args, **kwargs)

        return decorated

    def find_func(self, func_self, func, func_args, func_kwargs):
        ret_func = None
        for klass in inspect.getmro(func_self.__class__):
            name = self.format_name(klass.__name__, func)
            try:
                for d in self.callbacks[name]:
                    if d["callback"](func_self, *func_args, **func_kwargs):
                        ret_func = d["func"]
                        break

            except KeyError:
                pass

            finally:
                if ret_func:
                    break

        return ret_func

    def get_name(self, func):

        frame = inspect.currentframe()
        frames = inspect.getouterframes(frame)
        pout.v(frames)


        name = ""
        module = inspect.getmodule(func)
        _, line_i = inspect.getsourcelines(func)
        pout.v(_)
        mod_lines, _ = inspect.getsourcelines(module)
        i = line_i
        while i >= 0:
            # so we have a little bit of a pickle here, we need the class name but
            # the class isn't actually loaded yet, but we can get the module, so
            # we are going to just look at the actual source code to find the class
            # name, because if we tried to pull the class some other way it would
            # fail because python hasn't fully loaded the module, I'm actually
            # surprised we can even get the module
            m = re.match(r"^\s*class\s+([^\s\(]+)", mod_lines[i])
            if m:
                name = m.group(1)
                break

            else:
                i -= 1

        return self.format_name(name, func)

    def format_name(self, clsname, func):
        name = "{}.{}".format(clsname, func.__name__)
        return name

    def add_callback(self, func, callback):
        #pout.v(vars(func), dir(func), func)
        name = self.get_name(func)
        callbacks = self.callbacks
        callbacks.setdefault(name, [])
        callbacks[name].append({"func": func, "callback": callback})
        self.callbacks = callbacks
        #pout.v(func.__name__, func.__class__, callback)

