# -*- coding: utf-8 -*-
import itertools
from collections import defaultdict
import inspect
from typing import (
    Any, # https://docs.python.org/3/library/typing.html#the-any-type
    get_args, # https://stackoverflow.com/a/64643971
)
from types import UnionType

from datatypes import (
    ReflectClass,
    ReflectCallable,
    classproperty,
    cachedproperty,
)

from .compat import *
from .utils import Url


class ReflectController(ReflectClass):
    def __init__(self, keys, value):
        super().__init__(value["class"])
        self.keys = keys
        self.value = value

#     def get_http_methods(self):
#         """Get the controller http methods
# 
#         :returns generator[str, callable], where the key is the http method
#             type (eg "GET", "POST") and the method is the controller method.
#             There can be multiple of each http method name, so this can
#             yield N GET methods, etc.
#         """
#         method_names = self.value["method_names"]
# 
#         for http_method_name, method_names in method_names.items():
#             for method_name in method_names:
#                 yield http_method_name, getattr(self.target, method_name)

    def reflect_http_methods(self):
        """Reflect the controller http methods

        :returns generator[ReflectMethod], the controller method.
            There can be multiple of each http method name, so this can
            yield N GET methods, etc.
        """
        method_names = self.value["method_names"]

        for http_method_name, method_names in method_names.items():
            for method_name in method_names:
                yield self.create_reflect_http_method(
                    http_method_name,
                    getattr(self.target, method_name),
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
    def __init__(self, http_method_name, target, reflect_controller, **kwargs):
        super().__init__(target, **kwargs)
        self.http_method_name = http_method_name
        self._reflect_controller = reflect_controller

#     def get_http_method_name(self):
#         return self._http_method_name

    def reflect_controller(self):
        return self._reflect_controller


class OpenABC(dict):
    """The base type for all the OpenAPI objects"""

#     @classproperty
#     def fields(cls):
#         fields = {}
#         for k in dir(cls):
#             v = inspect.getattr_static(cls, k)
#             if isinstance(v, Field):
#                 fields[k] = v
# 
#         return fields
#         return dict(inspect.getmembers_static(
#             cls,
#             lambda v: isinstance(v, Field)
#         ))

    fields = None

    parent = None

    root = None

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
                        if v := m(**kwargs):
                            self[k] = v

                    else:
                        field_type = field["type"]
                        if not isinstance(field_type, type):
                            if isinstance(field_type, UnionType):
                                field_type = get_args(field_type)[0]

                        if (
                            issubclass(field_type, OpenABC)
                            and field_type is not OpenABC
                        ):
                            self[k] = field_type(self)

                        elif issubclass(field_type, list):
                            self[k] = []

                        elif issubclass(field_type, dict):
                            self[k] = {}

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


class Field(dict):
    def __init__(self, field_type, **kwargs):
        self.name = kwargs.pop("name", "")

        kwargs.setdefault("required", False)
        kwargs["type"] = field_type
        super().__init__(**kwargs)

    def __set_name__(self, owner, name):
        if not owner.fields:
            owner.fields = {}
#         if not hasattr(owner, "fields"):
#             setattr(owner, "fields", {})

        if not self.name:
            # we add underscores to get around python method and keyword
            # name collisions (eg "in", "get")
            self.name = name.strip("_")

        owner.fields[self.name] = self

    def get_factory_method(self, owner, name, field):
        method_name = f"create_{name}"
        return getattr(owner, method_name, None)


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

#     def __init__(self, parent, **kwargs):
#         super().__init__(parent, **kwargs)
# 
#         self["title"] = kwargs.get("title", "Endpoints API")
#         self["version"] = kwargs.get("version", "0.1.0")

#         if v := self.create_contact():
#             self["contact"] = v
# 
#         if v := self.create_license():
#             self["license"] = v


class Server(OpenABC):
    """Represents an OpenAPI server object

    From the docs:
        the default value would be a Server Object with a url value of /

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-object
    """
    _url = Field(str, default="/")

    _description = Field(str)

    _variables = Field(dict[str, OpenABC])

#     def __init__(self, parent, **kwargs):
#         super().__init__(parent)
# 
#         self["url"] = Url(path="/")


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
        self["schema"] = self.create_property(**kwargs)

    def create_property(self, **kwargs):
        schema = kwargs.get("property_class", Property)(
            self,
            self.param,
            **kwargs
        )

        # description is not needed for this schema
        schema.pop("description", "")
        return schema


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

    def add_params(self, **kwargs):
        self["parameters"] = []

        if has_body := self.has_body():
            self["requestBody"] = self.create_request_body(**kwargs)

        has_body = self.has_body()
        unwrapped = self.reflect_method.get_unwrapped()
        if params := getattr(unwrapped, "params", []):
            for param in (p.param for p in params):
                self.add_param(param, **kwargs)

    def add_param(self, param, **kwargs):
        if param.is_kwarg:
            if has_body:
                prop = self.create_property(param, **kwargs)
                self["requestBody"].add_property(prop, **kwargs)

            else:
                # this is a query param
                self["parameters"].append(self.create_param_parameter(
                    param,
                    **kwargs
                ))

        else:
            # this is a positional argument
            self["parameters"].append(self.create_param_parameter(
                param,
                **kwargs
            ))

    def add_headers(self, **kwargs):
        for rd in self.reflect_method.reflect_decorators():
            if rd.name == "version":
                self["parameters"].append(self.create_header_parameter(
                    rd,
                    **kwargs
                ))

    def create_header_parameter(self, reflect_decorator, **kwargs):
        return kwargs.get("header_parameter_class", HeaderParameter)(
            self,
            reflect_decorator,
            **kwargs
        )

    def create_param_parameter(self, param, **kwargs):
        return kwargs.get("param_parameter_class", ParamParameter)(
            self,
            param,
            **kwargs
        )

#     def create_schema(self, param, **kwargs):
#         return kwargs.get("schema_class", Schema)(
#             self,
#             param,
#             **kwargs
#         )

    def create_request_body(self, **kwargs):
        return kwargs.get("request_body_class", RequestBody)(
            self,
            **kwargs
        )

    def create_property(self, param, **kwargs):
        return kwargs.get("property_class", Property)(
            self,
            param,
            **kwargs
        )

    def get_path(self):
        keys = self.reflect_method.reflect_controller().keys
        return "/" + "/".join(
            itertools.chain(
                keys,
#                 self.value["module_keys"],
#                 self.value["class_keys"],
                (f"{{{p.name}}}" for p in self.parameters if p["in"] == "path")
            )
        )

    def has_body(self):
        return self.name in set(["put", "post", "patch"])


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

#     def __init__(self, path, parent, value, **kwargs):
#         self.path = path
#         self.value = value
#         self.reflect_class = ReflectClass(value["class"])
# 
#         super().__init__(parent)
# 
#         self["description"] = self.reflect_class.get_docblock()
#         if self["description"]:
#             self["summary"] = self["description"].partition("\n")[0]
# 
#         for op in kwargs.get("operations", []):
#             self.add_operation(op)

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

#     def get_method_info(self, http_method_name, method, **kwargs):
#         return {
#             "http_method_name": http_method_name,
#             "controller_info": self.controller_info,
#             "method": method,
#         }

    def create_operation(self, reflect_method, **kwargs):
        return kwargs.get("operation_class", Operation)(
            self,
            reflect_method=reflect_method,
        )

    def create_path_item(self):
        return kwargs.get("path_item_class", PathItem)(self)



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

    openapi = Field(str, default="3.1.0", required=True)

    info = Field(Info, required=True)

    servers = Field(list[Server])

    paths = Field(dict[str, PathItem])

    components = Field(OpenABC)

    security = Field(OpenABC)

    tags = Field(OpenABC)

    externalDocs = Field(OpenABC)


    def __init__(self, application, **kwargs):
        self.application = application

        super().__init__(None, **kwargs)

#         self["openapi"] = "3.1.0"
#         self["info"] = self.create_info(**kwargs)
#         self["server"] = self.create_server(**kwargs)
#         self["paths"] = self.create_paths(**kwargs)
# 
#         if v := self.create_components():
#             self["components"] = v
# 
#         if v := self.create_security():
#             self["security"] = v
# 
#         if v := self.create_tags():
#             self["tags"] = v
# 
#         if v := self.create_external_docs():
#             self["externalDocs"] = v

#     def get_schema(self):
#         return {
#             "openapi": {
#                 "type": str,
#                 "default": "3.1.0"
#             },
#             "info": {
#                 "type": Info
#             },
#             "server": {
#                 "type": Server
#             },
#             "paths": {
#                 "type": dict
#             },
#             "components": {
#                 "type": OpenABC
#             },
#         }

#     def create_components(self):
#         """
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#components-object
#         """
#         pass
# 
#     def create_security(self):
#         """
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#security-requirement-object
#         """
#         pass
# 
#     def create_tags(self):
#         """
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#tag-object
#         """
#         pass
# 
#     def create_external_docs(self):
#         """
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#external-documentation-object
#         """
#         pass
# 
#     def write_yaml(self, directory):
#         """Writes openapi.yaml file to directory
# 
#         https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#document-structure
#         """
#         pass
# 
#     def write_json(self, directory):
#         """Writes openapi.json file to directory
#         """
#         pass

#     def create_info(self):
#         return Info(self)
# 
#     def create_server(self):
#         return Server(self)


#     def get_controller_info(self, keys, value, **kwargs):
#         return {
#             "keys": keys,
#             "value": value,
#             "class": value["class"],
#         }

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

#         pathfinder = self.application.router.pathfinder
#         for keys, value in pathfinder.get_class_items():
#             for op_name, method_names in value["method_names"].items():
#                 for method_name in method_names:
#                     op = self.create_operation(
#                         op_name,
#                         value,
#                         getattr(value["class"], method_name),
#                     )
# 
#                     path = op.get_path()
#                     if path in paths:
#                         paths[path].add_operation(op)
# 
#                     else:
#                         paths[path] = self.create_path_item(
#                             path,
#                             value,
#                             operations=[op],
#                         )

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

#     def create_path_item(self, *args, **kwargs):
#         return PathItem(self, *args, **kwargs)


