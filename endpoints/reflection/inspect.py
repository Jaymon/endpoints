# -*- coding: utf-8 -*-
import re
import io
from collections import defaultdict, Counter
from collections.abc import Callable
import inspect
from typing import (
    Any, # https://docs.python.org/3/library/typing.html#the-any-type
)
import functools
import logging

from datatypes import (
    ReflectClass,
    ReflectCallable,
    Boolean,
    ClasspathFinder,
    NamingConvention,
)
from datatypes.reflection.inspect import ReflectArgument, ReflectObject

from ..compat import *
from ..utils import MimeType
from ..config import environ


logger = logging.getLogger(__name__)


class ReflectController(ReflectClass):
    def __init__(self, target, **kwargs):
        """
        :param target: type, the controller class
        :keyword module_keys: list[str], the module path keys
        :keyword class_keys: list[str], the Controller path keys used in
            Pathfinder 
        :keyword modules: list[ModuleType], the modules corresponding to
            the module keys
        """
        super().__init__(target)

        self.module_keys = list(kwargs.get("module_keys", []))
        self.modules = kwargs.get("modules", [])

        self.class_keys = list(kwargs.get("class_keys", []))

    def reflect_url_modules(self):
        """Reflect the controller modules for this controller

        Controller modules are modules that can be part of a request path

        :returns: generator[ReflectModule], this returns the reflected module
            for each iteration
        """
        if mks := self.module_keys:
            for i, mk in enumerate(mks):
                rm = self.create_reflect_module(self.modules[i])
                rm.module_key = mk
                yield rm

    def reflect_http_methods(self, http_verb=""):
        """Reflect the controller http methods

        :returns generator[ReflectMethod], the controller method.
            There can be multiple of each http method name, so this can
            yield N GET methods, etc.
        """
        method_names = self.get_http_method_names()
        if http_verb:
            items = []
            if http_verb in method_names:
                items.append((http_verb, method_names[http_verb]))

        else:
            items = method_names.items()

        for method_http_verb, method_names in items:
            for method_name in method_names:
                yield self.create_reflect_http_method(
                    method_http_verb,
                    method_name
                )

    @functools.cache
    def reflect_http_handler_methods(self, http_verb):
        http_methods = list(self.reflect_http_methods(http_verb))
        if not http_methods:
            http_methods = list(self.reflect_http_methods("ANY"))

        return http_methods

    def has_http_handler_method(self, http_verb) -> bool:
        """Return True if `http_verb` has a handler method that can answer
        requests for the given verb. This will always return True if the
        `ANY` handler method is defined on the class

        :param http_verb: str, something like `GET` or `POST`
        :returns: bool, True if there are handler http methods for verb
        """
        http_methods = self.get_http_method_names()
        for verb in [http_verb.upper(), "ANY"]:
            if http_methods.get(verb, None):
                return True

        return False

    def create_reflect_http_method(
        self,
        http_verb,
        method_name,
        **kwargs
    ):
        """Creates ReflectMethod instances which are exclusively for
        a Controller's <HTTP-VERB>_* methods that handle requests

        :param http_verb: str, the http verb/method (eg "GET") that this method
            is handling, this is separate from the method name because of
            verbs like "ANY" and suffixes on method names like GET_1
        :param method_name: str, the Controller's method name that will handle
            the http_verb
        :keyword reflect_http_method_class: Optional[ReflectMethod], an
            instance of this class will be created and returned
        :returns: ReflectMethod
        """
        target = self.get_target()
        return kwargs.get("reflect_http_method_class", ReflectMethod)(
            getattr(target, method_name),
            http_verb,
            self,
            target_class=target,
            name=method_name
        )

    def get_module_url_path(self) -> str:
        """Get the url path for just the module of this controller"""
        path = ""
        if module_path := "/".join(self.module_keys):
            path += "/" + module_path

        return path

    def get_url_path(self) -> str:
        """Get the root url path for this controller

        This will not include any url path params. Since methods can define
        url path params you want to call this same method on ReflectMethod
        instances to get the full url path for a given http verb
        """
        path = "/" + "/".join(self.get_url_parts())
        return path

    def get_url_parts(self) -> list[str]:
        """Get the url path as an array of parts"""
        # the path part that is covered by python modules
        for k in self.module_keys:
            yield k

        # the path part that is covered by classes that this controller
        # is defined in (eg, a class that has a property that is another
        # class, ..., and finally a class that has a Controller class as
        # a class property
        for k in self.class_keys:
            yield k

        # the last part is the class url name if this class has one
        if k := self.get_url_name():
            yield k

    def get_url_name(self) -> str:
        """Get the url name of this class, the reason why this is separate
        from `.name` is because the controller's name can be different than
        the url name"""
        return self.get_class().get_name()

    def reflect_url_paths(self):
        """Returns all the url paths of this controller

        The http methods on the controller can have their own url paths,
        and OPTIONS is nebulous and should be included on all the paths
        of this controller. This compiles all the paths and returns
        `ReflectMethod` instances for each url path

        :returns: dict[str, list[ReflectMethod]]
        """
        reflect_options = None
        for rm in self.reflect_http_methods("OPTIONS"):
            reflect_options = rm
            break

        url_paths = defaultdict(list)
        for rm in self.reflect_http_methods():
            if rm.http_verb != "OPTIONS":
                url_path = rm.get_url_path()
                if reflect_options and url_path not in url_paths:
                    url_paths[url_path].append(reflect_options)

                url_paths[url_path].append(rm)

        return url_paths

    @functools.cache
    def get_http_method_names(self):
        """An HTTP method (eg GET or POST) needs to be handled by a controller
        class. So a controller can have a method named GET and that will be
        called when GET <PATH-TO-CONTROLLER> is called. But wait, there's more,
        there can actually be multiple methods defined that all start with
        <HTTP-METHOD> (eg, GET_1, GET_2, etc)

        Although you can define any http methods (a method is valid if it is
        all uppercase), here is a list of rfc approved http request methods:

            http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

        :returns: dict[str, list[str]], the keys are the HTTP verb and the
            values are all the method names that satisfy that HTTP verb.
            these method names will be in alphabetical order to make it so
            they can always be checked in the same order
        """
        method_names = defaultdict(set)

        controller_class = self.get_target()

        members = inspect.getmembers(controller_class)
        for member_name, member in members:
            prefix, sep, postfix = member_name.partition("_")
            if prefix.isupper() and callable(member):
                if prefix != "OPTIONS" or controller_class.cors:
                    method_names[prefix].add(member_name)

        # after compiling them put them in alphabetical order
        for prefix in method_names.keys():
            method_names[prefix] = list(method_names[prefix])
            method_names[prefix].sort()

        return method_names


class ReflectMethod(ReflectCallable):
    """Reflect a controller http handler method

    these are methods on the controller like GET and POST
    """
    @classmethod
    def http_verb_has_body(self, http_verb):
        """Returns True if http_verb accepts a body in the request"""
        return http_verb in set(["PUT", "POST", "PATCH"])

    def __init__(self, target, http_verb, reflect_controller, **kwargs):
        """
        :param target: callable, the controller method
        :param http_verb: str, since method names can be things like
            GET_1, etc. this should be the actual http method (eg GET for
            any GET_* methods)
        :param reflect_controller: ReflectController, since reflected
            controllers are instantiated a certain way this gets passed in
            so things like .reflect_class work as expected
        """
        super().__init__(target, **kwargs)
        self.http_verb = http_verb
        self._reflect_controller = reflect_controller

    def reflect_class(self):
        return self._reflect_controller

    def reflect_params(self):
        """This will reflect all params in the method signature"""
        for param in self.get_params():
            yield self.create_reflect_param(param)

    def reflect_body_params(self):
        """This will reflect all the params that are usually passed up using
        the body on a POST request"""
        if self.has_body():
            for rp in self.reflect_params():
                if rp.is_keyword():
                    yield rp

    def reflect_url_params(self):
        """This will reflect params that need to be in the url path or the
        query part of the url"""
        for rp in self.reflect_params():
            if rp.is_positional() or not self.has_body():
                yield rp

    def reflect_query_params(self):
        """This will reflect params that need to be in the query part of the
        url"""
        for rp in self.reflect_params():
            if rp.is_keyword() and not self.has_body():
                yield rp

    def reflect_path_params(self):
        """This will reflect params that need to be in the url path"""
        for rp in self.reflect_params():
            if rp.is_positional():
                yield rp

    def create_reflect_param(self, *args, **kwargs):
        kwargs["reflect_method"] = self
        return kwargs.pop("reflect_param_class", ReflectParam)(
            *args,
            **kwargs,
        )

    def create_reflect_http_method(self, http_verb, **kwargs):
        """Basically clone this instance but for the specific http_verb

        This is mainly for things like ANY

        :param http_verb: str, the http verb (eg, GET or POST)
        :returns: ReflectMethod, it will have the same target as
            self.get_target() but, most likely, a different http_verb
        """
        return self.reflect_class().create_reflect_http_method(
            http_verb,
            self.name,
            **kwargs
        )

    def create_reflect_argument(self, target, *args, **kwargs):
        if target:
            params = self.get_param_info()
            if target.name in params:
                kwargs.setdefault("reflect_param", params[target.name])

        kwargs.setdefault("reflect_argument_class", ReflectArgument)
        return super().create_reflect_argument(target, *args, **kwargs)

    def reflect_arguments(self, *args, **kwargs):
        params = self.get_param_info()

        # resolve any aliases
        for name, rp in params.items():
            if name not in kwargs:
                for n in rp.flags["aliases"]:
                    if n in kwargs:
                        kwargs[name] = kwargs.pop(n)
                        break

        yield from super().reflect_arguments(*args, **kwargs)

    def get_url_path(self):
        """Get the path for this method. The reason why this is on the method
        and not the controller is because there could be path parameters
        for specific methods which means a controller, while having the
        same root path, can have different method paths"""
        path = self.reflect_class().get_url_path()
        url_params = "/".join(
            f"{{{p.name}}}" for p in self.reflect_path_params()
        )

        if url_params:
            if not path.endswith("/"):
                path += "/"

            path += url_params

        return path

    def get_version(self):
        """Get the version for this method"""
        version = ""

        for rd in self.reflect_ast_decorators():
            if rd.name == "version":
                dargs, dkwargs = rd.get_parameters()
                version = dargs[0]
                break

        return version

    @functools.cache
    def get_param_info(self):
        params = {}
        for rp in self.reflect_params():
            params[rp.name] = rp

        return params

    def get_success_media_types(self) -> list[tuple[type, str|Callable]]:
        """Get the success response media types for this method

        This follows the same format as `Controller.get_response_media_types`
        """
        media_types = []

        if rrt := self.reflect_return_type():
            if rrt.is_union():
                rts = rrt.reflect_types()

            else:
                rts = [rrt]

            for rt in rts:
                media_type = ""

                if rt.is_annotated():
                    info = rt.get_metadata_info()
                    media_type = info["keywords"].get("media_type", "")
                    if not media_type:
                        if info["positionals"]:
                            media_type = info["positionals"][0]

                    if media_type:
                        for rct in rt.reflect_cast_types():
                            rmt = (rct.get_origin_type(), media_type)
                            media_types.append(rmt)

                if not media_type:
                    controller_class = self.get_class()
                    url_name = controller_class.get_name()
                    if url_name and "." in url_name:
                        if media_type := MimeType.find_type(url_name):
                            rmt = (rt.get_origin_type(), media_type)
                            media_types.append(rmt)

                if not media_type:
                    cmedia_types = controller_class.get_response_media_types()

                    for rct in rt.reflect_cast_types():
                        for mtinfo in cmedia_types:
                            exactcheck = rct.is_type(mtinfo[0])
                            anycheck = (
                                mtinfo[0] is Any
                                or mtinfo[0] is object
                            )
                            if exactcheck or anycheck:
                                media_type = mtinfo[1]
                                rmt = (rct.get_origin_type(), mtinfo[1])
                                media_types.append(rmt)

                                if exactcheck:
                                    break

        return media_types

    def get_error_media_types(self) -> list[tuple[type, str|Callable]]:
        """Get the error response media types for this method

        This follows the same format as `Controller.get_response_media_types`
        """
        media_types = []
        for t in self.get_class().get_response_media_types():
            body_types, body_media_type = t
            if not isinstance(body_types, tuple):
                body_types = (body_types,)
            for body_type in body_types:
                if issubclass(body_type, Exception):
                    media_types.append(t)

        return media_types

    def get_request_media_types(self) -> list[str]:
        """Get the request response media types for this method

        Annoyingly, this returns a different format than the other media_types
        methods
        """
        media_types = []
        if self.has_body():
            counts = Counter()
            non_files = True

            for rp in self.reflect_body_params():
                counts["params"] += 1
                if rp.is_file():
                    counts["files"] += 1
                    if not rp.is_required():
                        counts["optional_files"] += 1

            if counts["files"] > 0:
                media_types.append("multipart/form-data")
                non_files = counts["optional_files"] == counts["files"]

            if non_files:
                primary_media_type = environ.RESPONSE_MEDIA_TYPE
                default_media_type = "application/x-www-form-urlencoded"

                if primary_media_type:
                    media_types.append(primary_media_type)

                if default_media_type != primary_media_type:
                    media_types.append(default_media_type)

        return media_types

    @functools.cache
    def get_method_info(self):
        method_info = {
            "response_media_types": [
                *self.get_success_media_types(),
                *self.get_error_media_types(),
            ],
        }
        method_info.setdefault("method_name", self.name)
        method_info["params"] = self.get_param_info()

        return method_info

    def has_body(self):
        """Returns True if http_verb accepts a body in the request"""
        return self.http_verb_has_body(self.http_verb)


class ReflectArgument(ReflectArgument):
    def __init__(
        self,
        target,
        value,
        reflect_callable,
        reflect_param=None,
        **kwargs,
    ):
        super().__init__(target, value, reflect_callable, **kwargs)

        self._reflect_param = reflect_param

    def reflect_param(self):
        return self._reflect_param

    def normalize_value(self):
        v = self.value
        if rp := self.reflect_param():
            v = rp.normalize_value(v)

        return v


class ReflectParam(ReflectObject):
    """Reflects an inspect.Parameter instance from an http method's signature

    Reflected params only apply to http methods on controllers
    """
    @property
    def name(self):
        return self.get_target().name

    def __init__(self, param, reflect_method, **kwargs):
        super().__init__(param)

        self._reflect_method = reflect_method
        self.flags = self.get_flags(param)

    def get_flags(self, param):
        flags = {}

        flags["is_positional"] = False
        if param.kind == param.POSITIONAL_ONLY:
            flags["is_positional"] = True

        if param.default is param.empty:
            flags["required"] = True

        else:
            flags["required"] = False
            flags["default"] = param.default

        if param.annotation is param.empty:
            if param.kind == param.VAR_POSITIONAL:
                flags["type"] = list

            elif param.kind == param.VAR_KEYWORD:
                flags["type"] = dict

            else:
                flags["type"] = Any

        else:
            flags["type"] = param.annotation

            rt = self.create_reflect_type(flags["type"])
            if rt.is_annotated():
                for metadata in rt.get_metadata():
                    flags.update(metadata)

        flags.setdefault("aliases", [])
        flags["aliases"].extend(flags.pop("names", []))

        return flags

    def get_docblock(self):
        if rdb := self.reflect_method().reflect_docblock():
            name = self.name
            param_descs = rdb.get_param_descriptions()
            if name in param_descs:
                return param_descs[name]

    def reflect_class(self):
        return self.reflect_method().reflect_class()

    def reflect_module(self):
        """Returns the reflected module"""
        return self.reflect_method().reflect_module()

    def reflect_method(self):
        return self._reflect_method

    def is_required(self):
        return self.flags.get("required", False)

    def reflect_type(self):
        """Reflect the param's type argument if present"""
        return self.create_reflect_type(self.flags["type"])

    def is_keyword(self):
        return not self.is_positional()

    def is_positional(self):
        return self.flags["is_positional"]

    def is_file(self) -> bool:
        """Return True if this param is a file type"""
        return self.reflect_type().is_type(io.IOBase)

    def allow_empty(self):
        return self.flags.get("allow_empty", True)

    def normalize_value(self, val):
        """This will take the value and make sure it meets expectations

        :param val: the raw value pulled from kwargs or args
        :returns: val that has met all param checks
        :raises: ValueError if val fails any checks
        """
        flags = self.flags
        rt = self.reflect_type()

        if rt.is_listish():
            if not isinstance(val, list):
                val = [val]

            vs = []
            for v in val:
                if isinstance(v, basestring):
                    vs.extend(v.split(','))

                else:
                    vs.append(v)

            val = vs

        if regex := flags.get("regex", None):
            failed = False
            if isinstance(regex, basestring):
                if not re.search(regex, val):
                    failed = True

            else:
                if not regex.search(val):
                    failed = True

            if failed:
                raise ValueError("param failed regex check")

        if rt.is_bool():
            val = Boolean(val)

        else:
            val = rt.cast(val)

        if pchoices := set(flags.get("choices", [])):
            if rt.is_listish():
                for v in val:
                    if v not in pchoices:
                        raise ValueError(
                            "param value {} not in choices {}".format(
                                v,
                                pchoices
                            )
                        )

            else:
                if val not in pchoices:
                    raise ValueError(
                        "param value {} not in choices {}".format(
                            val,
                            pchoices
                        )
                    )

        allow_empty = flags.get("allow_empty", True)
        if not allow_empty and val is not False and not val:
            if "default" not in flags:
                raise ValueError("param was empty")

        if (min_size := flags.get("min_size", None)) is not None:
            failed = False
            if rt.is_numberish():
                if val < min_size:
                    failed = True

            else:
                if len(val) < min_size:
                    failed = True

            if failed:
                raise ValueError("param was smaller than {}".format(min_size))

        if (max_size := flags.get("max_size", None)) is not None:
            failed = False
            if rt.is_numberish():
                if val > max_size:
                    failed = True

            else:
                if len(val) > max_size:
                    failed = True

            if failed:
                raise ValueError("param was bigger than {}".format(max_size))

        return val


class Pathfinder(ClasspathFinder):
    """Internal class used by Router. This holds the tree of all the
    controllers so Router can resolve the path"""
    def _get_node_module_info(self, key, **kwargs):
        """Handle normalizing each module key to kebabcase"""
        key = NamingConvention(key).kebabcase()
        return super()._get_node_module_info(key, **kwargs)

    def create_reflect_controller(self, target, **kwargs):
        return kwargs.get("reflect_controller_class", ReflectController)(
            target,
            **kwargs
        )

    def _get_node_class_info(self, key, **kwargs):
        """Handle normalizing each class key. If it's the destination key
        then it will use the controller class's .get_name method for the
        key. If it's a waypoint key then it will normalize to kebab case
        """
        if "class" in kwargs:
            # The actual controller `Che` in: Foo.Bar.Che
            rc = self.create_reflect_controller(
                kwargs["class"],
                **kwargs
            )
            key = rc.get_url_name()

        else:
            # can be `Foo` or `Bar` in: Foo.Bar.Che
            rc = None
            key = NamingConvention(key).kebabcase()


        key, value = super()._get_node_class_info(key, **kwargs)

        if rc:
            value["reflect_class"] = rc

            logger.debug(
                (
                    "Registering verbs: {}"
                    " to path: {}"
                    " and controller: {}"
                ).format(
                    ", ".join(rc.get_http_method_names().keys()),
                    rc.get_url_path(),
                    rc.classpath,
                )
            )

        return key, value

