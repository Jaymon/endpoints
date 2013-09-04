import os
import sys
import importlib
import inspect
import re

class Reflect(object):
    """
    Reflect the controllers to reveal information about what endpoints are live
    """
    def __init__(self, controller_prefix, content_type=None):
        self.controller_prefix = controller_prefix

    def normalize_endpoint(self, endpoint, *args, **kwargs):
        """
        handy for adding any args, or kwargs accumulated through all the calls to the endpoint

        endpoint -- dict -- the endpoint information dict
        """
        return endpoint

    def normalize_controller_module(self, controller_prefix, fname, *args, **kwargs):
        """
        normalize controller bits to a python module

        example -- controller_prefix="foo", fname="bar" --> return "foo.bar"

        return -- string -- the full.python.module that can be imported
        """
        return u".".join([controller_prefix, fname])

    def walk_files(self, controller_path):
        """
        walk all the controllers that are submodules of controller_path

        controller_path -- string -- the path to where the controllers are

        return -- generator -- (file, args, kwargs) it yields each file and any extra info
        """
        for root, dirs, files in os.walk(controller_path, topdown=True):
            for f in files:
                yield f, [], {}
            break

    def get_controller_modules(self):
        """
        get all the controller modules

        this will find any valid controller modules and yield all the endpoints in them

        return -- generator -- endpoint info found in each controller module file
        """
        controller_path = self.find_controller_path()
        controller_prefix = self.controller_prefix
        for f, args, kwargs in self.walk_files(controller_path):
                fname, fext = os.path.splitext(f)
                if fext.lower() != u".py": continue
                if fname == u"__init__": continue

                controller_module = self.normalize_controller_module(controller_prefix, fname, *args, **kwargs)

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
        if not controller_prefix:
            raise ValueError("reflect only works when you use a controller_prefix")

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

    def get_endpoints_in_controller(self, controller, *args, **kwargs):
        """
        get all the endpoints in this controller

        return -- list -- a list of dicts with information about each endpoint in the controller
        """
        module = importlib.import_module(controller)
        classes = inspect.getmembers(module, inspect.isclass)
        #options = set(['get', 'head', 'post', 'put', 'delete', 'trace', 'options', 'connect', 'patch'])
        for k, v in classes:
            k = k.lower()
            public = not k.startswith(u'_') and not getattr(v, 'private', False)
            if public:
                methods = inspect.getmembers(v, inspect.ismethod)
                v_options = []
                option_regex = re.compile(ur"[A-Z][A-Z0-9_]+")
                for method_name, method in methods:
                    if option_regex.match(method_name):
                        v_options.append(method_name)

                if v_options:
                    doc = inspect.getdoc(v)
                    name = controller.rpartition(".")[2].lower()
                    endpoint = [u""]
                    for n in [name, k]:
                        if n != 'default': endpoint.append(n)
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

    def normalize_controller_module(self, controller_prefix, fname, version, *args, **kwargs):
        return u".".join([controller_prefix, version, fname])

    def normalize_endpoint(self, endpoint, version, *args, **kwargs):
        endpoint['headers'] = {}
        endpoint['headers']['Accept'] = "{};version={}".format(self.content_type, version)
        endpoint['version'] = version
        return endpoint

    def walk_files(self, controller_path):
        for root, versions, _ in os.walk(controller_path, topdown=True):
            for version in versions:
                for root,  _, files in os.walk(os.path.join(controller_path, version), topdown=True):
                    for f in files:
                        yield f, [], {'version': version}


