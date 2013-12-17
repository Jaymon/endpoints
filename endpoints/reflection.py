import os
import sys
import importlib
import inspect
import re
import fnmatch

from .core import Controller

class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    controller_prefix = u''

    @property
    def controller_path(self):
        if not hasattr(self, '_controller_path'):
            self._controller_path = self.find_controller_path()

        return self._controller_path

    def __init__(self, controller_prefix, content_type=None):
        self.controller_prefix = controller_prefix
        if not controller_prefix:
            raise ValueError("reflect only works when you use a controller_prefix")

    def normalize_endpoint(self, endpoint, *args, **kwargs):
        """
        handy for adding any args, or kwargs accumulated through all the calls to the endpoint

        endpoint -- dict -- the endpoint information dict
        """
        return endpoint

    def normalize_controller_module(self, controller_submodule_path, *args, **kwargs):
        """
        normalize controller bits to a python module

        example -- self.controller_prefix="foo", fname="bar" --> return "foo.bar"

        controller_submodule_path -- string -- the path to module in the controller path (eg, if
            self.controller path was /foo then module_path can be something like /foo/bar/che.py)

        return -- string -- the full.python.module that can be imported
        """
        ret = u""
        filesubpath = controller_submodule_path.replace(self.controller_path, '', 1)
        fbase, fext = os.path.splitext(filesubpath)
        fbits = filter(None, fbase.split(os.sep))
        if fbits[-1] == u"__init__":
            fbits = fbits[0:-1]

        ret = u".".join([self.controller_prefix] + fbits)
        return ret

    def walk_files(self, controller_path):
        """
        walk all the controllers that are submodules of controller_path

        controller_path -- string -- the path to where the controllers are

        return -- generator -- (file, args, kwargs) it yields each file and any extra info
        """
        r = re.compile('^(?:__init__|[^_][^.]+)\.py$', re.I)
        for root, dirs, files in os.walk(controller_path, topdown=True):
            #for f in fnmatch.filter(files, '?*.py'):
            for f in files:
                if r.match(f):
                    yield os.path.join(root, f), [], {}

    def get_controller_modules(self):
        """
        get all the controller modules

        this will find any valid controller modules and yield all the endpoints in them

        return -- generator -- endpoint info found in each controller module file
        """
        controller_prefix = self.controller_prefix
        for f, args, kwargs in self.walk_files(self.controller_path):
            controller_module = self.normalize_controller_module(f, *args, **kwargs)

            for endpoint, args, kwargs in self.get_endpoints_in_controller(controller_module, *args, **kwargs):
                yield endpoint, args, kwargs

    def get_endpoints(self):
        """
        go through all the controllers in controller prefix and return them

        return -- list -- a list of endpoints found
        """
        pre_module_names = set(sys.modules.keys())

        l = []

        for endpoint, args, kwargs in self.get_controller_modules():
            l.append(self.normalize_endpoint(endpoint, *args, **kwargs))

        new_module_names = set(sys.modules.keys()) - pre_module_names

        # remove any new modules that were added when this was run
        for n in new_module_names: sys.modules.pop(n, None)

        return l

    def find_controller_path(self):
        """
        find the base controller path using this class's set controller_prefix

        return -- string -- the controller base directory
        """
        controller_prefix = self.controller_prefix
        controller_path = u""
        controller_dirs = controller_prefix.split(u".")
        for p in sys.path:
            fullp = os.path.join(p, *controller_dirs)
            if os.path.isdir(fullp):
                controller_path = fullp
                break

        if not controller_path:
            raise IOError("could not find a valid path for controllers in module: {}".format(controller_prefix))

        return controller_path

    def get_endpoints_in_controller(self, controller_name, *args, **kwargs):
        """
        get all the endpoints in this controller

        return -- list -- a list of dicts with information about each endpoint in the controller
        """
        module = importlib.import_module(controller_name)
        classes = inspect.getmembers(module, inspect.isclass)
        for class_name, v in classes:
            if not issubclass(v, Controller): continue
            if class_name.startswith(u'_') or getattr(v, 'private', False):
                continue

            class_name = class_name.lower()
            v_options = v.get_methods()
            if v_options:
                doc = inspect.getdoc(v)

                name = controller_name.replace(self.controller_prefix, '', 1).lower()
                endpoint = name.split(u".")
                if class_name != "default":
                    endpoint.append(class_name)

                if len(endpoint) == 1:
                    endpoint = u"/"
                else:
                    endpoint = u"/".join(endpoint)

                d = {
                    'endpoint': endpoint,
                    'options': v_options,
                    'doc': doc if doc else u""
                }
                yield d, args, kwargs


class VersionReflect(Reflect):
    """
    same as Reflect, but for VersionCall
    """
    def __init__(self, controller_prefix, content_type=None):
        self.content_type = content_type
        super(VersionReflect, self).__init__(controller_prefix)

    def normalize_endpoint(self, endpoint, version, *args, **kwargs):
        endpoint['headers'] = {}
        endpoint['headers']['Accept'] = "{};version={}".format(self.content_type, version)
        endpoint['version'] = version
        return endpoint

    def walk_files(self, controller_path):
        base_controller_prefix = self.controller_prefix
        base_controller_path = controller_path
        for root, versions, _ in os.walk(controller_path, topdown=True):
            for version in versions:
                self.controller_prefix = u".".join([base_controller_prefix, version])
                self._controller_path = os.path.join(base_controller_path, version)
                for f, args, kwargs in super(VersionReflect, self).walk_files(self._controller_path):
                    kwargs['version'] = version
                    yield f, args, kwargs

                self.controller_prefix = base_controller_prefix
                self._controller_path = base_controller_path

            break

