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
    """WARNING -- The functionality in this decorator is *highly* experimental

    Restrict method calls to certain conditions, this is handy when you want to
    do different things depending on the parameters and path variables that are
    sent up

    :example:
        class Default(Controller):
            # run this when /foo is requested
            @when(lambda: self, *args, **kwargs: args[0] == "foo")
            def GET(self, *args, **kwargs): pass

            # run this when /bar is requested
            @when(lambda: self, *args, **kwargs: args[0] == "bar")
            def GET(self, *args, **kwargs): pass
    """

    callbacks = {}
    """class property that holds the mapping on where each call should be routed"""

    def decorate(slf, func, callback, *args, **kwargs):
        slf.add_callback(func, callback)
        def decorated(self, *args, **kwargs):
            try:
                ret_func = slf.find_func(self, func, args, kwargs)
                return ret_func(self, *args, **kwargs)

            except TypeError as e:
                raise CallError(404, e)

        return decorated

    def find_func(self, func_self, func, func_args, func_kwargs):
        ret_func = None
        for klass in inspect.getmro(func_self.__class__):
            name = self.format_name(klass.__name__, func.__name__)
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

        # so we have a little bit of a pickle here, we need the class name but
        # the class isn't actually loaded yet, but we can get the module, so
        # we are going to just look at the actual source code to find the class
        # name, because if we tried to pull the class some other way it would
        # fail because python hasn't fully loaded the module, I'm actually
        # surprised we can even get the module
        class_name = ""
        method_name = ""
        method_line_i = 0

        regex = re.compile(r"^\s*class\s+([^\s\(]+)")
        frame = inspect.currentframe()
        frames = inspect.getouterframes(frame)
        for frame_i, frame in enumerate(frames):
            m = regex.match("".join(frame[4]))
            if m:
                class_name = m.group(1)
                method_line_i = frames[frame_i - 1][2]
                break

        module = inspect.getmodule(func)
        mod_lines, _ = inspect.getsourcelines(module)
        i = method_line_i
        regex = re.compile(r"^\s*def\s+([^\s\(]+)")
        while i < len(mod_lines):
            m = regex.match(mod_lines[i])
            if m:
                method_name = m.group(1)
                break

            else:
                i += 1

        return self.format_name(class_name, method_name)

    def format_name(self, class_name, method_name):
        name = "{}.{}".format(class_name, method_name)
        return name

    def add_callback(self, func, callback):
        #pout.v(vars(func), dir(func), func)
        name = self.get_name(func)
        callbacks = self.callbacks
        callbacks.setdefault(name, [])
        callbacks[name].append({"func": func, "callback": callback})
        self.callbacks = callbacks
        #pout.v(func.__name__, func.__class__, callback)

