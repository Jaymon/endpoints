# -*- coding: utf-8 -*-
import itertools
from collections import defaultdict
import inspect
from typing import (
    Any, # https://docs.python.org/3/library/typing.html#the-any-type
    get_args, # https://stackoverflow.com/a/64643971
    get_origin,
)
from types import (
    UnionType,
    GenericAlias,
)
import json

from datatypes import (
    ReflectClass,
    ReflectCallable,
    classproperty,
    cachedproperty,
    Dirpath,
    NamingConvention,
    ClassFinder,
)

from .compat import *
from .utils import Url


class ReflectController(ReflectClass):
    def __init__(self, keys, value):
        super().__init__(value["class"])
        self.keys = keys
        self.value = value

    def reflect_http_methods(self, http_method_name=""):
        """Reflect the controller http methods

        :returns generator[ReflectMethod], the controller method.
            There can be multiple of each http method name, so this can
            yield N GET methods, etc.
        """
        method_names = self.value["method_names"]

        for method_prefix, method_names in method_names.items():
            if not http_method_name or method_prefix == http_method_name:
                for method_name in method_names:
                    yield self.create_reflect_http_method(
                        getattr(self.target, method_name),
                        method_prefix,
                        name=method_name
                    )

    def create_reflect_http_method(self, *args, **kwargs):
        kwargs.setdefault("target_class", self.target)
        kwargs["reflect_controller"] = self
        return kwargs.get("reflect_http_method_class", ReflectMethod)(
            *args,
            **kwargs
        )


class ReflectMethod(ReflectCallable):
    def __init__(self, target, http_method_name, reflect_controller, **kwargs):
        super().__init__(target, **kwargs)
        self.http_method_name = http_method_name
        self._reflect_controller = reflect_controller

    def reflect_controller(self):
        return self._reflect_controller

    def has_body(self):
        return self.name in set(["PUT", "POST", "PATCH"])

    def reflect_params(self):
        unwrapped = self.get_unwrapped()
        if params := getattr(unwrapped, "params", []):
            for param in (p.param for p in params):
                yield self.create_reflect_param(param)

    def reflect_body_params(self):
        if self.has_body():
            for rp in self.reflect_params():
                if rp.target.is_kwarg:
                    yield rp

    def reflect_url_params(self):
        for rp in self.reflect_params():
            if not rp.target.is_kwarg or not self.has_body():
                yield rp

    def reflect_path_params(self):
        for rp in self.reflect_params():
            if not rp.target.is_kwarg:
                yield rp

    def create_reflect_param(self, *args, **kwargs):
        kwargs["reflect_method"] = self
        return kwargs.get("reflect_param_class", ReflectParam)(
            *args,
            **kwargs
        )

    def get_url_path(self):
        return "/" + "/".join(
            itertools.chain(
                self.reflect_controller().keys,
                (f"{{{p.name}}}" for p in self.reflect_path_params())
            )
        )


class ReflectParam(object):
    def __init__(self, target, reflect_method, **kwargs):
        self.target = target
        self._reflect_method = reflect_method

        if "name" in kwargs:
            self.name = kwargs["name"]

        else:
            if target.is_kwarg:
                self.name = target.name

            else:
                si = reflect_method.get_signature_info()
                if len(si["names"]) > target.index:
                    self.name = si["names"][target.index]

                else:
                    self.name = target.index

    def reflect_controller(self):
        return self.reflect_method().reflect_controller()

    def reflect_method(self):
        return self._reflect_method

    def get_parameter_kwargs(self):
        kwargs = {}

        param = self.target
        if param.is_kwarg:
            kwargs["in"] = "query"
            kwargs["name"] = param.name
            kwargs["required"] = param.flags.get("required", False)
            kwargs["allowEmptyValue"] = param.flags.get("allow_empty", False)

        else:
            kwargs["in"] = "path"
            kwargs["name"] = self.name

            # spec: "If the parameter location is "path", this property is
            # REQUIRED and its value MUST be true"
            kwargs["required"] = True

        kwargs["description"] = param.flags.get("help", "")

        return kwargs


class Field(dict):
    def __init__(self, field_type, **kwargs):
        self.name = kwargs.pop("name", "")

        kwargs.setdefault("required", False)
        kwargs["type"] = field_type
        super().__init__(**kwargs)

    def __set_name__(self, owner, name):
        if not owner.fields:
            owner.fields = {}

        self.owner_name = name

        if not self.name:
            # we add underscores to get around python method and keyword
            # name collisions (eg "in", "get")
            self.name = name.strip("_")

        owner.fields[self.name] = self

    def get_factory_method(self, owner, name, field):
        name = NamingConvention(name)
        method_name = f"create_{name.varname()}"
        return getattr(owner, method_name, None)

#     def get_factory_class(self):
#         for t in self.get_factory_classes():
#             return t
# 
#         field_type = self["type"]
#         raise ValueError(
#             f"Could not find a factory class from {field_type}"
#         )


    def get_factory_classes(self):
        # TODO -- return the class from the type that can be used to create
        # an instance
        ret = {}

        def get_classes(field_type):
            if isinstance(field_type, UnionType):
                for ft in get_args(field_type):
                    yield from get_classes(ft)

            elif isinstance(field_type, GenericAlias):
                yield from get_classes(get_origin(field_type))
                for ft in get_args(field_type):
                    yield from get_classes(ft)

            elif issubclass(field_type, OpenABC):
                if field_type is not OpenABC:
                    name = NamingConvention(field_type.__name__)
                    yield f"{name.varname()}_class", field_type

        for class_varname, klass in get_classes(self["type"]):
            ret[class_varname] = klass

        return ret
        #yield from get_classes(self["type"])


class OpenABC(dict):
    """The base type for all the OpenAPI objects"""

    fields = None

    parent = None

    root = None

    classes = ClassFinder()

    def find_reflect_controller(self):
        parent = self
        while parent := parent.parent:
            if r := getattr(parent, "reflect_controller", None):
                return r

    def find_reflect_method(self):
        parent = self
        while parent := parent.parent:
            if r := getattr(parent, "reflect_method", None):
                return r

    def __init__(self, parent, **kwargs):
        if parent:
            self.parent = parent
            self.root = parent.root

        else:
            self.root = self

        super().__init__()

        self.insert(**kwargs)

    def __init_subclass__(cls):
        """When a child class is loaded into memory it will be saved into
        .orm_classes, this way every orm class knows about all the other orm
        classes, this is the method that makes that possible magically

        https://peps.python.org/pep-0487/
        """
        cls.classes.add_class(cls)
        super().__init_subclass__()

    def __getattr__(self, key):
        try:
            return self.__getitem__(key)

        except KeyError as e:
            raise AttributeError(key) from e

    def __delattr__(self, key):
        try:
            return self.__delitem__(key)

        except KeyError as e:
            raise AttributeError(key) from e

    def insert(self, *args, **kwargs):
        if self.fields:
            d = dict(*args, **kwargs)
            for k, field in self.fields.items():
                if k in kwargs:
                    self[k] = kwargs[k]

                else:
                    if m := field.get_factory_method(self, k, field):
                        if v := m(**field.get_factory_classes(), **kwargs):
                            self[k] = v

                if k not in self and "default" in field:
                    self[k] = field["default"]

            if "summary" in self.fields and "summary" not in self:
                if desc := self.get("description", ""):
                    self["summary"] = self["description"].partition("\n")[0]

    def update(self, *args, **kwargs):
        if self.fields:
            for k, v in dict(*args, **kwargs).items():
                if k in self.fields:
                    self[k] = v


class Info(OpenABC):
    """Represents an OpenAPI info object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#info-object

    Required:
        * title: str
        * version: str
    """
    _title = Field(str, default="Endpoints API")

    _description = Field(str)

    _summary = Field(str)

    _termsOfService = Field(str)

    _contact = Field(OpenABC)

    _license = Field(OpenABC)

    _version = Field(str, default="0.1.0")

    def create_description(self, **kwargs):
        rc = ReflectClass(self.root.application)
        return rc.get_docblock()


class Server(OpenABC):
    """Represents an OpenAPI server object

    From the docs:
        the default value would be a Server Object with a url value of /

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-object
    """
    _url = Field(str, default="/")

    _description = Field(str)

    _variables = Field(dict[str, OpenABC])


class Reference(OpenABC):
    pass


class Response(OpenABC):
    pass


class MediaType(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#media-type-object

    TODO -- file uploads:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#considerations-for-file-uploads
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent)

        self["schema"] = self.create_schema(**kwargs)

    def add_property(self, prop, **kwargs):
        self["schema"].add_property(prop, **kwargs)

    def create_schema(self, **kwargs):
        return kwargs.get("schema_class", Schema)(
            self,
            **kwargs
        )


class RequestBody(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#request-body-object

    Required:
        * content: dict[string, MediaType]
    """
    _description = Field(str)

    _content = Field(dict[str, MediaType])

    _required = Field(bool)

    def add_param(self, param, **kwargs):
        pout.v(param)

    def add_property(self, prop, **kwargs):
        if "content" not in self:
            self["content"] = self.create_content(**kwargs)

        for content_type, media_type in self["content"].items():
            media_type.add_property(prop, **kwargs)

    def create_content(self, **kwargs):
        return {
            "*/*": self.create_media_type(**kwargs)
        }

    def create_media_type(self, **kwargs):
        return kwargs.get("media_type_class", MediaType)(
            self,
            **kwargs
        )


class Schema(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent)

        self["type"] = "object"
        self["required"] = []
        self["properties"] = {}

    def add_property(self, prop, **kwargs):
        prop.parent = self
        self["properties"][prop.name] = prop

        if prop.is_required():
            self["required"].append(prop.name)


class Property(OpenABC):
    """

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object

    looks like section 10.2 of the json schema spec has the keywords
    https://json-schema.org/draft/2020-12/json-schema-core#name-keywords-for-applying-subsc

    """
    def __init__(self, parent, param, **kwargs):
        self.param = param

        super().__init__(parent)

        self.name = param.name
        self["type"] = self.get_type()
        if size := self.get_size():
            self.update(size)

        if desc := param.flags.get("help", ""):
            self["description"] = desc

        if "choices" in param.flags:
            self["enum"] = list(param.flags["choices"])

    def get_type(self):
        t = self.param.flags["type"]
        if not t:
            ret = "string"

        elif issubclass(t, str):
            ret = "string"

        elif issubclass(t, bool):
            ret = "boolean"

        elif issubclass(t, int):
            ret = "integer"

        elif issubclass(t, float):
            ret = "number"

        elif issubclass(t, Sequence):
            ret = "array"

        elif issubclass(t, Mapping):
            ret = "object"

        else:
            if (
                "list" in self.param.flags["action"]
                or "append" in self.param.flags["action"]
            ):
                ret = "array"

            else:
                raise ValueError(f"Not sure how to handle type {t}")

        return ret

    def get_size(self):
        """
        https://json-schema.org/understanding-json-schema/reference/numeric#range
        """
        ret = {}

        if "min_size" in self.param.flags:
            ret["minimum"] = self.param.flags["min_size"]

        if "max_size" in self.param.flags:
            ret["maximum"] = self.param.flags["max_size"]

        return ret

    def is_required(self):
        return self.param.flags.get("required", False)


class Parameter(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#parameter-object
    """
    _name = Field(str, required=True)

    _in = Field(str, required=True)

    _description = Field(str)

    _required = Field(bool)

    _deprecated = Field(bool)

    _allowEmptyValue = Field(bool, default=False)

    _schema = Field(Schema)

    _example = Field(Any)

    _examples = Field(dict[str, Reference|OpenABC])


class ParamParameter(Parameter):
    """Represents an OpenAPI Parameter object from an endpoints param
    decorator

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#parameter-object

    Required:
        * name
        * in
    """
    def __init__(self, parent, param, **kwargs):
        self.param = param

        super().__init__(parent)

        if param.is_kwarg:
            self["in"] = "query"
            self["name"] = param.name
            self["required"] = param.flags.get("required", False)
            self["allowEmptyValue"] = param.flags.get("allow_empty", False)

        else:
            self["in"] = "path"
            # spec: "If the parameter location is "path", this property is
            # REQUIRED and its value MUST be true"
            self["required"] = True
            rm = parent.reflect_method

            si = rm.get_signature_info()
            if len(si["names"]) >= param.index:
                self["name"] = si["names"][param.index]

            else:
                self["name"] = param.index

        self["description"] = param.flags.get("help", "")
#         self["schema"] = self.create_property(**kwargs)
# 
#     def create_property(self, **kwargs):
#         schema = kwargs.get("property_class", Property)(
#             self,
#             self.param,
#             **kwargs
#         )
# 
#         # description is not needed for this schema
#         schema.pop("description", "")
#         return schema


class Operation(OpenABC):
    """Represents an OpenAPI operation object

    An operation is an HTTP scheme handler (eg GET, POST)

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#operation-object
    """
    _tags = Field(list[str])

    _summary = Field(str)

    _description = Field(str)

    _externalDocs = Field(OpenABC)

    _operationId = Field(str)

    _parameters = Field(list[Parameter|Reference])

    _requestBody = Field(RequestBody|Reference)

    _responses = Field(dict[str, Reference|Response])
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#responses-object
    """

    _callbacks = Field(dict[str, OpenABC])

    _deprecated = Field(bool)

    _security = Field(list[OpenABC])

    _servers = Field(list[Server])

#     def __init__(self, parent, reflect, **kwargs):
#         self.name = name.lower()
#         self.value = value
#         self.method = method
#         self.reflect_method = ReflectCallable(method, value["class"])
# 
#         super().__init__(parent)
# 
#         self["description"] = self.reflect_method.get_docblock()
#         if self["description"]:
#             self["summary"] = self["description"].partition("\n")[0]
# 
#         self.add_params(**kwargs)
#         self.add_headers(**kwargs)
# 
#         # TODO -- add responses

    def insert(self, reflect_method, **kwargs):
        self.name = reflect_method.http_method_name.lower()
        self.reflect_method = reflect_method

        super().insert(**kwargs)

        #self.add_params(**kwargs)

        #     def add_params(self, **kwargs):
# #         self["parameters"] = []
# # 
# #         if has_body := self.reflect_method.has_body():
# #             self["requestBody"] = self.create_request_body(**kwargs)
# 
#         unwrapped = self.reflect_method.get_unwrapped()
#         if params := getattr(unwrapped, "params", []):
#             for param in (p.param for p in params):
#                 self.add_param(param, **kwargs)
# 
#     def add_param(self, param, **kwargs):
#         if param.is_kwarg and self.reflect_method.has_body():
#             if "requestBody" not in self:
#                 self["requestBody"] = self.create_request_body(**kwargs)
# 
#             #prop = self.create_property(param, **kwargs)
#             #self["requestBody"].add_property(prop, **kwargs)
#             self["requestBody"].add_param(param, **kwargs)
# 
#         else:
#             if "parameters" not in self:
#                 self["parameters"] = []
# 
#             # this is a positional argument (part of path) or query param
#             # (after the ? in the url)
#             self["parameters"].append(self.create_param_parameter(
#                 param,
#                 **kwargs
#             ))

            #     def add_headers(self, **kwargs):
#         for rd in self.reflect_method.reflect_decorators():
#             if rd.name == "version":
#                 self["parameters"].append(self.create_header_parameter(
#                     rd,
#                     **kwargs
#                 ))
# 
#     def create_header_parameter(self, reflect_decorator, **kwargs):
#         return kwargs.get("header_parameter_class", HeaderParameter)(
#             self,
#             reflect_decorator,
#             **kwargs
#         )

#     def create_param_parameter(self, param, **kwargs):
#         return kwargs.get("param_parameter_class", ParamParameter)(
#             self,
#             param,
#             **kwargs
#         )

#     def create_schema(self, param, **kwargs):
#         return kwargs.get("schema_class", Schema)(
#             self,
#             param,
#             **kwargs
#         )

    def create_request_body(self, **kwargs):
        if self.reflect_method.has_body():
            rb = kwargs.get("request_body_class", RequestBody)(
                self,
                **kwargs
            )

            for p in self.reflect_method.reflect_body_params():
                pout.b("body param")
                pout.v(p)

    def create_parameters(self, **kwargs):
        parameters = []
        parameter_class = kwargs["parameter_class"]

        # this is a positional argument (part of path) or query param
        # (after the ? in the url)
        for rp in self.reflect_method.reflect_url_params():
            parameters.append(parameter_class(
                self,
                reflect_param=rp,
                **rp.get_parameter_kwargs()
            ))

        return parameter

#             pout.b("url param")
#             pout.v(p.name)
            #pout.v(p)

#     def create_property(self, param, **kwargs):
#         return kwargs.get("property_class", Property)(
#             self,
#             param,
#             **kwargs
#         )

    def get_path(self):
        keys = self.reflect_method.reflect_controller().keys
        parameters = getattr(self, "parameters", [])
        return "/" + "/".join(
            itertools.chain(
                keys,
#                 self.value["module_keys"],
#                 self.value["class_keys"],
                (f"{{{p.name}}}" for p in parameters if p["in"] == "path")
            )
        )

#     def has_body(self):
#         return self.name in set(["put", "post", "patch"])


#    This is for: path, query, header, and cookie params, not body params


class PathItem(OpenABC):
    """Represents an OpenAPI path item object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#path-item-object
    """
    _ref = Field(str, name="$ref")

    _summary = Field(str)

    _description = Field(str)

    _get = Field(Operation)

    _put = Field(Operation)

    _post = Field(Operation)

    _delete = Field(Operation)

    _options = Field(Operation)

    _head = Field(Operation)

    _patch = Field(Operation)

    _trace = Field(Operation)

    _servers = Field(list[Server])

    _parameters = Field(list[Parameter|Reference])

    def add_operation(self, operation, **kwargs):
        if operation.name in self:
            raise ValueError(
                f"Path {self.path} has multiple {operation.name} keys"
            )

        else:
            self[operation.name] = operation



class Paths(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object
    """
    def insert(self, reflect_controller, **kwargs):
        self.reflect_controller = reflect_controller

        for reflect_method in reflect_controller.reflect_http_methods():
            op = self.create_operation(reflect_method, **kwargs)

            path = op.get_path()
            if path not in self:
                self[path] = self.create_path_item(**kwargs)

            self[path].add_operation(op)

    def create_operation(self, reflect_method, **kwargs):
        return kwargs.get("operation_class", Operation)(
            self,
            reflect_method=reflect_method,
            **kwargs
        )

    def create_path_item(self, **kwargs):
        return kwargs.get("path_item_class", PathItem)(self, **kwargs)


class OpenAPI(OpenABC):
    """Represents an OpenAPI 3.1.0 document

    the document format is defined here:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#openapi-object

    Required:
        * openapi: str
        * info: Info instance

    Included:
        * server: Server instance
        * paths: dict[str, PathItem]
    """

    _openapi = Field(str, default="3.1.0", required=True)

    _info = Field(Info, required=True)

    _servers = Field(list[Server])

    _paths = Field(dict[str, PathItem])

    _components = Field(OpenABC)
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#components-object
    """

    _security = Field(OpenABC)
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#security-requirement-object
    """

    _tags = Field(OpenABC)
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#tag-object
    """

    _externalDocs = Field(OpenABC)
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#external-documentation-object
    """

    def __init__(self, application, **kwargs):
        self.application = application

        super().__init__(None, **kwargs)


#     def write_yaml(self, directory):
#         """Writes openapi.yaml file to directory
# 
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#document-structure
#         https://github.com/yaml/pyyaml
#         """
#         pass

    def write_json(self, directory):
        """Writes openapi.json file to directory
        """
        dp = Dirpath(directory)
        fp = dp.get_file("openapi.json")
        data = json.dumps(self)
        pout.v(data)

        pass

    def create_paths(self, **kwargs):
        """Represents a Pseudo OpenApi paths object

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object

        The keys are the path (starting with /) and the value are a Path Item
        object

        :returns: generator[str, PathItem]
        """
        paths = {}

        pathfinder = self.application.router.pathfinder
        for keys, value in pathfinder.get_class_items():
            paths.update(
                self.create_controller_paths(
                    keys,
                    value,
                    **kwargs
                )
            )

        return paths

    def create_controller_paths(self, keys, value, **kwargs):
        rc = kwargs.get("reflect_controller_class", ReflectController)(
            keys,
            value
        )
        return kwargs.get("paths_class", Paths)(
            self,
            reflect_controller=rc
        )

