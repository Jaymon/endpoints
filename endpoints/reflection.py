# -*- coding: utf-8 -*-
import itertools
from collections import defaultdict

from datatypes import (
    ReflectClass,
    ReflectCallable,
)

from .utils import Url


class AttributeDict(dict):
    def __getattr__(self, key):
        try:
            return self.__getitem__(key)

        except KeyError as e:
            raise AttributeError(key) from e

#     def __setattr__(self, key, value):
#         return self.__setitem__(key, value)

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
#         self.path_item_class = kwargs.get("path_item_class", PathItem)

    def write_yaml(self, directory):
        """Writes openapi.yaml file to directory

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#document-structure
        """
        pass

    def write_json(self, directory):
        """Writes openapi.json file to directory
        """
        pass

#     def set_paths(self, **kwargs):
#         paths = {}
#         path_item_class = kwargs.get("path_item_class", PathItem)
# 
#         pathfinder = self.application.router.pathfinder
#         for keys, value in pathfinder.get_class_items():
#             pi = path_item_class(self, keys, value)
#             yield pi.get_path(), pi

    def create_info(self, **kwargs):
        return kwargs.get("info_class", Info)(self, **kwargs)

    def create_server(self, **kwargs):
        return kwargs.get("server_class", Server)(self, **kwargs)

#     def create_path_item(self, keys, values, **kwargs):
#         operation_class = kwargs.get("operation_class", Operation)
# 
#         for http_op, method_names in value["method_names"].items():
#             for method_name in method_names:
#                 method = getattr(value["class"], method_name)
#                 op = operation_class(
#                     self,
#                     keys,
#                     value,
#                     method,
#                     **kwargs
#                 )
# 
#     def create_operation(self, keys, values, method, **kwargs):




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

#                 ops = defaultdict(list)

                for method_name in method_names:
                    #controller = value["class"](None, None)
                    #method = getattr(controller, method_name)
                    #pout.v(method.__wrapped__.get_wrapped_method(method))

                    op = operation_class(
                        self,
                        op_name,
                        value,
                        getattr(value["class"], method_name),
                        **kwargs
                    )

                    path = op.get_path()
                    if path in paths:
                        self.update_path_item(
                            path,
                            paths[path],
                            op,
                            **kwargs
                        )

                    else:
                        paths[path] = self.create_path_item(
                            path,
                            value,
                            op,
                            **kwargs
                        )

#                     ops[op["in"]].append(op)



#             pi = path_item_class(self, keys, value)
# 
# 
#             yield pi.get_path(), pi
        return paths

    def create_path_item(self, path, value, operation, **kwargs):
        path_item_class = kwargs.get("path_item_class", PathItem)
        pi = path_item_class(
            self,
            value,
            **kwargs
        )

        pi[operation.name] = operation
        return pi

    def update_path_item(self, path, path_item, operation, **kwargs):
        if operation.name in path_item:
            raise ValueError(
                f"Path {path} has multiple {operation.name} keys"
            )


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

#         if url := Url():
#             self.url = url
# 
#         else:
#             # from the docs:
#             # the default value would be a Server Object with a url value of /
#             self.url = "/"


# class Paths(dict):
#     """Represents an OpenApi paths object
# 
#     https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object
# 
#     The keys are the path (starting with /) and the value are a Path Item
#     object
#     """
#     def __init__(self, openapi, **kwargs):
#         self.openapi = openapi


class PathItem(AttributeDict):
    """Represents an OpenAPI path item object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#path-item-object
    """
    def __init__(self, parent, value, **kwargs):
        self.parent = parent
        self.value = value

#         self.operation_class = kwargs.get("operation_class", Operation)

        super().__init__()

        r = ReflectClass(value["class"])
        self["description"] = r.get_docblock()
        if self.description:
            self["summary"] = self.description.partition("\n")[0]

#     def get_operations(self):
#         for http_method, method_names in self.value["method_names"].items():
#             if len(method_names) > 1:
#                 raise ValueError(
#                     "OpenAPI currently doesn't support multiple"
#                     f" {http_method} methods"
#                 )
# 
#             yield http_method.lower(), self.operation_class(
#                 self,
#                 getattr(value["class"], method_names[0]),
#             )


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


#         pout.v(r.get_unwrapped().params)
#         pout.v(method)


#         descriptor = r.get_descriptor()
#         pout.i(descriptor)
#         pout.v(descriptor.__wrapped__.params)

        self["description"] = self.reflect_method.get_docblock()
        if self.description:
            self["summary"] = self.description.partition("\n")[0]

#         pout.v(method.params)

        #params = defaultdict(list)
        self["parameters"] = []

        has_body = self.has_body()
        unwrapped = self.reflect_method.get_unwrapped()
        if params := getattr(unwrapped, "params", []):
            for param in (p.param for p in params):
                if param.is_kwarg:
                    if has_body:
                        # TODO this is a body parameter
                        s = self.create_schema(param, **kwargs)
                        pass

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

                    #params[p["in"]].append(p)

        # TODO -- add responses

    def create_parameter(self, param, **kwargs):
        return kwargs.get("parameter_class", ParamParameter)(
            self,
            param,
            **kwargs
        )

    def create_schema(self, param, **kwargs):
        return kwargs.get("schema_class", Schema)(
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
        self["schema"] = self.create_schema(**kwargs)

    def create_schema(self, **kwargs):
        schema = kwargs.get("property_class", Property)(
            self,
            self.param,
            **kwargs
        )

        # description is not needed for this schema
        schema.pop("description", "")
        return schema


class Property(AttributeDict):
    """

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object
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
        if isinstance(t, str):
            ret = "string"

        elif isinstance(t, bool):
            ret = "boolean"

        elif isinstance(t, int):
            ret = "integer"

        elif isinstance(t, float):
            ret = "number"

        elif isinstance(t, Sequence):
            ret = "array"

        elif isinstance(t, Mapping):
            ret = "object"

        else:
            if (
                "list" in self.param.flags["action"]
                or "append" in self.param.flags["action"]
            ):
                ret = "array"

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

