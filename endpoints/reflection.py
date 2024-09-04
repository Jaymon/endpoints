# -*- coding: utf-8 -*-
import itertools
from collections import defaultdict

from datatypes import (
    ReflectClass,
    ReflectCallable,
)

from .compat import *
from .utils import Url


class AttributeDict(dict):
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


class OpenAPI(AttributeDict):
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
    def __init__(self, application, **kwargs):
        self.parent = None
        self.application = application

        self["openapi"] = "3.1.0"

        self["info"] = self.create_info(**kwargs)
        self["server"] = self.create_server(**kwargs)
        self["paths"] = self.create_paths(**kwargs)

    def write_yaml(self, directory):
        """Writes openapi.yaml file to directory

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#document-structure
        """
        pass

    def write_json(self, directory):
        """Writes openapi.json file to directory
        """
        pass

    def create_info(self, **kwargs):
        return kwargs.get("info_class", Info)(self, **kwargs)

    def create_server(self, **kwargs):
        return kwargs.get("server_class", Server)(self, **kwargs)

    def create_paths(self, **kwargs):
        """Represents a Pseudo OpenApi paths object

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object

        The keys are the path (starting with /) and the value are a Path Item
        object

        :returns: generator[str, PathItem]
        """
        paths = {}

        operation_class = kwargs.get("operation_class", Operation)

        pathfinder = self.application.router.pathfinder
        for keys, value in pathfinder.get_class_items():
            for op_name, method_names in value["method_names"].items():
                for method_name in method_names:
                    op = operation_class(
                        self,
                        op_name,
                        value,
                        getattr(value["class"], method_name),
                        **kwargs
                    )

                    path = op.get_path()
                    if path in paths:
                        paths[path].add_operation(op, **kwargs)

                    else:
                        paths[path] = self.create_path_item(
                            path,
                            value,
                            op,
                            **kwargs
                        )

        return paths

    def create_path_item(self, path, value, operation, **kwargs):
        path_item_class = kwargs.get("path_item_class", PathItem)
        pi = path_item_class(
            self,
            path,
            value,
            **kwargs
        )

        pi[operation.name] = operation
        return pi


class Info(AttributeDict):
    """Represents an OpenAPI info object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#info-object

    Required:
        * title: str
        * version: str
    """
    def __init__(self, parent, **kwargs):
        self.parent = parent

        super().__init__()

        self["title"] = kwargs.get("title", "Endpoints API")
        self["version"] = kwargs.get("version", "0.1.0")


class Server(AttributeDict):
    """Represents an OpenAPI server object

    From the docs:
        the default value would be a Server Object with a url value of /

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-object
    """
    def __init__(self, parent, **kwargs):
        self.parent = parent

        super().__init__()

        self["url"] = Url(path="/")


class PathItem(AttributeDict):
    """Represents an OpenAPI path item object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#path-item-object
    """
    def __init__(self, path, parent, value, **kwargs):
        self.path = path
        self.parent = parent
        self.value = value
        self.reflect_class = ReflectClass(value["class"])

        super().__init__()

        self["description"] = self.reflect_class.get_docblock()
        if self["description"]:
            self["summary"] = self["description"].partition("\n")[0]

    def add_operation(self, operation, **kwargs):
        if operation.name in self:
            raise ValueError(
                f"Path {self.path} has multiple {operation.name} keys"
            )


class Operation(AttributeDict):
    """Represents an OpenAPI operation object

    An operation is an HTTP scheme handler (eg GET, POST)

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#operation-object
    """
    def __init__(self, parent, name, value, method, **kwargs):
        self.parent = parent
        self.name = name.lower()
        self.value = value
        self.method = method
        self.reflect_method = ReflectCallable(method, value["class"])

        super().__init__()

        self["description"] = self.reflect_method.get_docblock()
        if self["description"]:
            self["summary"] = self["description"].partition("\n")[0]

        self.add_params(**kwargs)

        # TODO -- add responses

    def add_params(self, **kwargs):
        self["parameters"] = []

        if has_body := self.has_body():
            self["requestBody"] = self.create_request_body(**kwargs)

        has_body = self.has_body()
        unwrapped = self.reflect_method.get_unwrapped()
        if params := getattr(unwrapped, "params", []):
            for param in (p.param for p in params):
                if param.is_kwarg:
                    if has_body:
                        prop = self.create_property(param, **kwargs)
                        self["requestBody"].add_property(prop, **kwargs)

                    else:
                        # this is a query param
                        self["parameters"].append(self.create_parameter(
                            param,
                            **kwargs
                        ))

                else:
                    # this is a positional argument
                    self["parameters"].append(self.create_parameter(
                        param,
                        **kwargs
                    ))

    def create_parameter(self, param, **kwargs):
        return kwargs.get("parameter_class", ParamParameter)(
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
        return "/" + "/".join(
            itertools.chain(
                self.value["module_keys"],
                self.value["class_keys"],
                (f"{{{p.name}}}" for p in self.parameters if p["in"] == "path")
            )
        )

    def has_body(self):
        return self.name in set(["put", "post", "patch"])


#    This is for: path, query, header, and cookie params, not body params

class ParamParameter(AttributeDict):
    """Represents an OpenAPI Parameter object from an endpoints param
    decorator

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#parameter-object

    Required:
        * name
        * in
    """
    def __init__(self, parent, param, **kwargs):
        self.parent = parent
        self.param = param

        super().__init__()

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


class RequestBody(AttributeDict):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#request-body-object

    Required:
        * content: dict[string, MediaType]
    """
    def __init__(self, parent, **kwargs):
        self.parent = parent

        super().__init__()

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


class MediaType(AttributeDict):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#media-type-object

    TODO -- file uploads:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#considerations-for-file-uploads
    """
    def __init__(self, parent, **kwargs):
        self.parent = parent

        super().__init__()

        self["schema"] = self.create_schema(**kwargs)

    def add_property(self, prop, **kwargs):
        self["schema"].add_property(prop, **kwargs)

    def create_schema(self, **kwargs):
        return kwargs.get("schema_class", Schema)(
            self,
            **kwargs
        )


class Schema(AttributeDict):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object
    """
    def __init__(self, parent, **kwargs):
        self.parent = parent

        super().__init__()

        self["type"] = "object"
        self["required"] = []
        self["properties"] = {}

    def add_property(self, prop, **kwargs):
        prop.parent = self
        self["properties"][prop.name] = prop

        if prop.is_required():
            self["required"].append(prop.name)


class Property(AttributeDict):
    """

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object

    looks like section 10.2 of the json schema spec has the keywords
    https://json-schema.org/draft/2020-12/json-schema-core#name-keywords-for-applying-subsc

    """
    def __init__(self, parent, param, **kwargs):
        self.parent = parent
        self.param = param

        super().__init__()

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

