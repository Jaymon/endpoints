# -*- coding: utf-8 -*-
import itertools
from collections import defaultdict
import inspect
import uuid
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
import datetime

from datatypes import (
    ReflectClass,
    ReflectCallable,
    ReflectType,
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
                    yield self.create_reflect_http_method_instance(
                        getattr(self.target, method_name),
                        method_prefix,
                        name=method_name
                    )

    def create_reflect_http_method_instance(self, *args, **kwargs):
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
                yield self.create_reflect_param_instance(param)

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

    def create_reflect_param_instance(self, *args, **kwargs):
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

#     def get_parameter_kwargs(self):
#         kwargs = {}
# 
#         param = self.target
#         if param.is_kwarg:
#             kwargs["in"] = "query"
#             kwargs["name"] = param.name
#             kwargs["required"] = param.flags.get("required", False)
#             kwargs["allowEmptyValue"] = param.flags.get("allow_empty", False)
# 
#         else:
#             kwargs["in"] = "path"
#             kwargs["name"] = self.name
# 
#             # spec: "If the parameter location is "path", this property is
#             # REQUIRED and its value MUST be true"
#             kwargs["required"] = True
# 
#         kwargs["description"] = param.flags.get("help", "")
# 
#         return kwargs

    def is_required(self):
        return self.target.flags.get("required", False)


class Field(dict):
    def __init__(self, field_type, **kwargs):
        self.name = kwargs.pop("name", "")
        self.owner = OpenABC

        kwargs.setdefault("required", False)
        kwargs["type"] = field_type
        super().__init__(**kwargs)

    def __set_name__(self, owner, name):
        if not owner.fields:
            owner.fields = {}

        self.owner = owner
        self.owner_name = name

        if not self.name:
            # we add underscores to get around python method and keyword
            # name collisions (eg "in", "get")
            self.name = name.strip("_")

        owner.fields[self.name] = self

    def get_value_method(self, owner, name, field):
        name = NamingConvention(name)
        method_name = f"get_{name.varname()}_value"
        return getattr(owner, method_name, None)

    def get_factory_classes(self):
        return list(self._get_factory_classes(self["type"]))

    def _get_factory_classes(self, klass):
        def is_factory_class(klass):
            return issubclass(klass, OpenABC) and klass is not OpenABC

        if isinstance(klass, UnionType):
            for ft in get_args(klass):
                yield from self._get_factory_classes(ft)

        elif isinstance(klass, GenericAlias):
            origin_class = get_origin(klass)
            if is_factory_class(origin_class):
                yield origin_class

            else:
                yield from self._get_factory_classes(origin_class)
                for ft in get_args(klass):
                    yield from self._get_factory_classes(ft)

        elif is_factory_class(klass):
            for subclass in self.owner.classes.get_abs_classes(klass):
                yield subclass

#     def _get_factory_classes(self, klass):
#         if isinstance(klass, UnionType):
#             for ft in get_args(klass):
#                 yield from self._get_factory_classes(ft)
# 
#         elif isinstance(klass, GenericAlias):
#             yield from self._get_factory_classes(get_origin(klass))
#             for ft in get_args(klass):
#                 yield from self._get_factory_classes(ft)
# 
#         elif issubclass(klass, OpenABC):
#             if klass is not OpenABC:
#                 name = NamingConvention(klass.__name__)
#                 yield f"{name.varname()}_class", klass
# 
#                 for subclass in OpenABC.classes.get_abs_classes(klass):
#                     name = NamingConvention(subclass.__name__)
#                     yield f"{name.varname()}_class", subclass
# 
#     def get_factory_classes(self):
#         # TODO -- return the class from the type that can be used to create
#         # an instance
#         return {n: c for n, c in self._get_factory_classes(self["type"])} 

    def get_factory_class(self):
        return self.get_factory_classes()[0]


class OpenFinder(ClassFinder):
#     def __init__(self, *args, **kwargs):
#         self.class_names = {}
#         super().__init__(*args, **kwargs)

    def _is_valid_subclass(self, klass):
        return issubclass(klass, OpenABC) and klass is not OpenABC

    def add_node(self, key, node, value):
        super().add_node(key, node, value)

        # this is the root node
        if not self.parent and len(self) == 1:
            self.class_keys = {}

        class_key = f"{NamingConvention(key.__name__).varname()}_class"
        self.root.class_keys[class_key] = key


class OpenABC(dict):
    """The base type for all the OpenAPI objects"""

    fields = None

    parent = None

    root = None

    classfinder = OpenFinder()

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

    def __init__(self, parent, *args, **kwargs):
        if parent:
            self.parent = parent
            self.root = parent.root

        else:
            self.root = self

        super().__init__()

        self.init_instance(*args, **kwargs)
        self.set_keys(**kwargs)

    def __init_subclass__(cls):
        """When a child class is loaded into memory it will be saved into
        .orm_classes, this way every orm class knows about all the other orm
        classes, this is the method that makes that possible magically

        https://peps.python.org/pep-0487/
        """
        cls.classfinder.add_class(cls)
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

    def __setitem__(self, key, value):
        if isinstance(value, OpenABC):
            value.validate()

        super().__setitem__(key, value)

    def init_instance(self, *args, **kwargs):
        pass

    def set_keys(self, *args, **kwargs):
        if self.fields:
#             d = dict(*args, **kwargs)
            for k, field in self.fields.items():
                if k in kwargs:
                    if kwargs[k]:
                        self[k] = kwargs[k]

                else:
                    if m := field.get_value_method(self, k, field):
                        if v := m(**kwargs):
                            self[k] = v

                if k not in kwargs and k not in self:
                    if "default" in field:
                        self[k] = field["default"]

#                 if field["required"] and k not in self:
#                     raise KeyError(
#                         f"{self.__class__.__name__}[{k}]"
#                     )

            if "summary" in self.fields and "summary" not in self:
                if desc := self.get("description", ""):
                    self["summary"] = self["description"].partition("\n")[0]

#     def update(self, *args, **kwargs):
#         if self.fields:
#             for k, v in dict(*args, **kwargs).items():
#                 if k in self.fields:
#                     self[k] = v

#     def create_field_value(self, field, *args, **kwargs):
#         pass

    def create_instance(self, class_key, *args, **kwargs):
        if class_key in kwargs:
            open_class = kwargs[class_key]

        else:
            open_class = self.classfinder.class_keys[class_key]

        return open_class(self, *args, **kwargs)

    def create_schema_instance(self, **kwargs):
        return self.create_instance("schema_class", **kwargs)

    def validate(self):
        if self.fields:
            for k, field in self.fields.items():
                if field["required"] and k not in self:
                    raise KeyError(
                        f"{self.__class__.__name__}[{k}]"
                    )


class Info(OpenABC):
    """Represents an OpenAPI info object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#info-object

    Required:
        * title: str
        * version: str
    """
    _title = Field(str, required=True, default="Endpoints API")

    _description = Field(str)

    _summary = Field(str)

    _termsOfService = Field(str)

    _contact = Field(OpenABC)

    _license = Field(OpenABC)

    _version = Field(str, required=True, default="0.1.0")

#     def get_description_value(self, **kwargs):
#         rc = ReflectClass(self.root.application)
#         return rc.get_docblock()


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
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#reference-object
    """
    pass


class Response(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#responses-object
    """
    pass


class Example(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#example-object
    """
    pass


class Schema(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object

    Validation is based off of:
        https://json-schema.org/draft/2020-12/schema

    https://json-schema.org/draft/2020-12/meta/validation
    """
    # https://json-schema.org/understanding-json-schema/reference/type
    _type = Field(
        str|list[str],
        choices=[
            "string",
            "integer",
            "number",
            "object",
            "array",
            "boolean",
            "null"
        ]
    )

    # https://json-schema.org/understanding-json-schema/reference/string
    _minLength = Field(int)
    _maxLength = Field(int)
    _pattern = Field(str)
    _format = Field(str)

    # https://json-schema.org/understanding-json-schema/reference/numeric
    _multipleOf = Field(int)
    _minimum = Field(int)
    _exclusiveMinimum = Field(int)
    _maximum = Field(int)
    _exclusiveMaximum = Field(int)

    # https://json-schema.org/understanding-json-schema/reference/object
    _properties = Field(dict[str, dict])
    _patternProperties = Field(dict[str, dict])
    _additionalProperties = Field(bool)
    _unevaluatedProperties = Field(bool)
    _required = Field(list[str])
    _propertyNames = Field(dict)
    _minProperties = Field(int)
    _maxProperties = Field(int)

    # https://json-schema.org/understanding-json-schema/reference/array
    _items = Field(dict[str, dict]|bool)
    _prefixItems = Field(list[dict])
    _unevaluatedItems = Field(bool)
    _contains = Field(dict)
    _minContains = Field(int)
    _maxContains = Field(int)
    _minItems = Field(int)
    _maxItems = Field(int)
    _uniqueItems = Field(bool)

    # https://json-schema.org/understanding-json-schema/reference/annotations
    _examples = Field(list)
    _deprecated = Field(bool)
    _title = Field(str)
    _description = Field(str)
    _default = Field(str)
    _readOnly = Field(bool)
    _writeOnly = Field(bool)

    # https://json-schema.org/understanding-json-schema/reference/comments
    _comments = Field(str, name="$comment")

    # https://json-schema.org/understanding-json-schema/reference/enum
    _enum = Field(list[str])

    # https://json-schema.org/understanding-json-schema/reference/const
    _const = Field(Any)

    # https://json-schema.org/understanding-json-schema/reference/combining
    _allOf = Field(list[dict])
    _anyOf = Field(list[dict])
    _oneOf = Field(list[dict])
    _not = Field(dict)

    # https://json-schema.org/understanding-json-schema/reference/conditionals
    _dependentRequired = Field(dict[str, dict])
    _dependentSchemas = Field(dict[str, dict])
    _if = Field(dict)
    _then = Field(dict)
    _else = Field(dict)

    # https://json-schema.org/understanding-json-schema/reference/schema
    _schema = Field(
        str,
        name="$schema",
        default="https://json-schema.org/draft/2020-12/schema"
    )



    #     def __init__(self, parent, **kwargs):
#         super().__init__(parent)
# 
#         self["type"] = "object"
#         self["required"] = []
#         self["properties"] = {}

#     def add_property(self, prop, **kwargs):
#         prop.parent = self
#         self["properties"][prop.name] = prop
# 
#         if prop.is_required():
#             self["required"].append(prop.name)

    def add_param(self, reflect_param):
        if self["type"] != "object":
            raise ValueError(
                f"Attempted to add param to {self['type']} schema"
            )

        if "properties" not in self:
            self["properties"] = {}

        schema = self.create_schema_instance()
        schema.set_param(reflect_param)
        schema.pop("$schema", None)

        self["properties"][reflect_param.name] = schema

        if reflect_param.is_required():
            if "required" not in self:
                self["required"] = []

            self["required"].append(reflect_param.name)

    def set_param(self, reflect_param):
        self.reflect_param = reflect_param
        self.update(self.get_param_fields(reflect_param))

    def get_param_fields(self, reflect_param):
        ret = {}
        param = reflect_param.target

        # !!! these type checks should probably be handled in the Param class
        list_actions = set(["append", "append_list", "store_list"])
        if param.flags["action"] in list_actions:
            t = list

        else:
            t = param.flags.get("type", str)
            if t is None:
                t = str

        ret.update(self.get_type_fields(t))

        min_size = param.flags.get("min_size", 0)
        max_size = param.flags.get("max_size", 0)
        if size := self.get_size_fields(ret["type"], min_size, max_size):
            self.update(size)

        if desc := param.flags.get("help", ""):
            ret["description"] = desc

        if "choices" in param.flags:
            ret["enum"] = list(param.flags["choices"])

        if "regex" in param.flags:
            ret["pattern"] = param.flags["regex"]

        return ret

    def get_size_fields(self, schema_type, min_size, max_size):
        """
        """
        ret = {}

        if schema_type == "string":
            # https://json-schema.org/understanding-json-schema/reference/string#length
            if min_size:
                ret["minLength"] = min_size

            if max_size:
                ret["maxLength"] = max_size

        elif schema_type == "integer" or schema_type == "number":
            # https://json-schema.org/understanding-json-schema/reference/numeric#range
            if min_size:
                ret["minimum"] = min_size

            if max_size:
                ret["maximum"] = max_size

        elif schema_type == "object":
            # https://json-schema.org/understanding-json-schema/reference/object#size
            if min_size:
                ret["minProperties"] = min_size

            if max_size:
                ret["maxProperties"] = max_size

        elif schema_type == "array":
            # https://json-schema.org/understanding-json-schema/reference/array#length
            if min_size:
                ret["minItems"] = min_size

            if max_size:
                ret["maxItems"] = max_size

        return ret

    def get_type_fields(self, t):
        """Convert a python type t to a JSON Schema type

        https://json-schema.org/understanding-json-schema/reference/type
        """
        ret = {}
        rt = ReflectType(t)

        if rt.is_stringish():
            ret["type"] = "string"

        elif rt.is_bool():
            ret["type"] = "boolean"

        elif rt.is_int():
            ret["type"] = "integer"

        elif rt.is_numberish():
            ret["type"] = "number"

        elif rt.is_dictish():
            ret["type"] = "object"

        elif rt.is_listish():
            ret["type"] = "array"

            items = []
            for at in ret.get_value_types():
                items.append(self.get_type_fields(at))

            if items:
                if len(items) > 1:
                    # https://stackoverflow.com/a/70863145
                    ret["items"] = {"anyOf": items}

                else:
                    ret.append({"items": items[0]})

        elif rt.is_type(uuid.UUID):
            ret["type"] = "string"
            ret["format"] = "uuid"

        elif rt.is_type(datetime.date):
            ret["type"] = "string"

            # https://json-schema.org/understanding-json-schema/reference/string#format
            if rt.is_type(datetime.datetime):
                ret["format"] = "date-time"

            else:
                ret["format"] = "date"

        elif rt.is_none():
            ret["type"] = "null"

        else:
            raise ValueError(f"Not sure how to handle type {t}")

        return ret

#         if t is None:
#             ret = "null"
# 
#         elif issubclass(t, str):
#             ret = "string"
# 
#         elif issubclass(t, bool):
#             ret = "boolean"
# 
#         elif issubclass(t, int):
#             ret = "integer"
# 
#         elif issubclass(t, float):
#             ret = "number"
# 
#         elif issubclass(t, datetime.date):
#             ret = "string"
# 
#         elif issubclass(t, Sequence):
#             ret = "array"
# 
#         elif issubclass(t, Mapping):
#             ret = "object"
# 
#         else:
#             if (
#                 "list" in self.param.flags["action"]
#                 or "append" in self.param.flags["action"]
#             ):
#                 ret = "array"
# 
#             else:
#                 raise ValueError(f"Not sure how to handle type {t}")
# 
#         return ret




# class Property(OpenABC):
#     """
# 
#     https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object
# 
#     looks like section 10.2 of the json schema spec has the keywords
#     https://json-schema.org/draft/2020-12/json-schema-core#name-keywords-for-applying-subsc
# 
#     """
#     def __init__(self, parent, param, **kwargs):
#         self.param = param
# 
#         super().__init__(parent)
# 
#         self.name = param.name
#         self["type"] = self.get_type()
#         if size := self.get_size():
#             self.update(size)
# 
#         if desc := param.flags.get("help", ""):
#             self["description"] = desc
# 
#         if "choices" in param.flags:
#             self["enum"] = list(param.flags["choices"])
# 
#     def get_size(self):
#         """
#         https://json-schema.org/understanding-json-schema/reference/numeric#range
#         """
#         ret = {}
# 
#         if "min_size" in self.param.flags:
#             ret["minimum"] = self.param.flags["min_size"]
# 
#         if "max_size" in self.param.flags:
#             ret["maximum"] = self.param.flags["max_size"]
# 
#         return ret
# 
#     def is_required(self):
#         return self.param.flags.get("required", False)


class MediaType(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#media-type-object

    TODO -- file uploads:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#considerations-for-file-uploads
    """
    _schema = Field(Schema)

    _example = Field(Any)

    _examples = Field(dict[str, Example|Reference])

    # this one has some strange requirements so I'm ignoring it right now
    #_encoding = Field(dict[str, Encoding])

#     def __init__(self, parent, **kwargs):
#         super().__init__(parent)
# 
#         self["schema"] = self.create_schema(**kwargs)

    def add_param(self, reflect_param):
        if "schema" not in self:
            self["schema"] = self.create_schema_instance(type="object")

        self["schema"].add_param(reflect_param)

#     def create_schema(self, **kwargs):
#         return kwargs.get("schema_class", Schema)(
#             self,
#             **kwargs
#         )


class RequestBody(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#request-body-object

    Required:
        * content: dict[string, MediaType]
    """
    _description = Field(str)

    _content = Field(dict[str, MediaType], required=True)

    _required = Field(bool)

    def add_param(self, reflect_param):
        for media_type in self["content"].values():
            media_type.add_param(reflect_param)

#     def add_property(self, prop, **kwargs):
#         if "content" not in self:
#             self["content"] = self.create_content(**kwargs)
# 
#         for content_type, media_type in self["content"].items():
#             media_type.add_property(prop, **kwargs)

    def get_content_value(self, **kwargs):
        return {
            "*/*": self.create_instance("media_type_class", **kwargs)
        }

#     def create_media_type(self, **kwargs):
#         return kwargs.get("media_type_class", MediaType)(
#             self,
#             **kwargs
#         )


class Parameter(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#parameter-object

    This is for: path, query, header, and cookie params, not body params
    """
    _name = Field(str, required=True)

    _in = Field(str, required=True)

    _description = Field(str)

    _required = Field(bool)

    _deprecated = Field(bool)

    _allowEmptyValue = Field(bool, default=False)

    _schema = Field(Schema)

    _example = Field(Any)

    _examples = Field(dict[str, Example|Reference])

    def set_param(self, reflect_param):
        self.reflect_param = reflect_param
        self.update(self.get_param_fields(reflect_param))

    def get_param_fields(self, reflect_param):
        ret = {}
        param = self.reflect_param.target

        if param.is_kwarg:
            ret["in"] = "query"
            ret["name"] = param.name
            ret["required"] = param.flags.get("required", False)
            ret["allowEmptyValue"] = param.flags.get("allow_empty", False)

        else:
            ret["in"] = "path"
            ret["name"] = reflect_param.name

            # spec: "If the parameter location is "path", this property is
            # REQUIRED and its value MUST be true"
            ret["required"] = True

        if desc := param.flags.get("help", ""):
            ret["description"] = desc

        schema = self.create_schema_instance()
        schema.set_param(reflect_param)
        ret["schema"] = schema

        return ret

#     def create_param_schema_instance(self, reflect_param):
#         schema = self.create_schema_instance()
#         schema.set_param(reflect_param)
#         return schema


# class ParamParameter(Parameter):
#     """Represents an OpenAPI Parameter object from an endpoints param
#     decorator
# 
#     https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#parameter-object
#     """
#     def insert(self, reflect_param, **kwargs):
#         self.reflect_param = reflect_param
#         super().insert(**kwargs)
# 
#     def create_in(self, **kwargs):
#         return "query" if self.reflect_param.target.is_kwarg else "path"
# 
#     def create_name(self, **kwargs):
#         return self.reflect_param.target.name
# 
#     def create_required(self, **kwargs):
#         if self.reflect_param.target.is_kwarg:
#             return self.reflect_param.target.flags.get("required", False)
# 
#         else:
#             # spec: "If the parameter location is "path", this property is
#             # REQUIRED and its value MUST be true"
#             self["required"] = True
# 
#     def create_allow_empty_value(self, **kwargs):
#         return self.reflect_param.target.flags.get("allow_empty", False)
# 
#     def create_description(self, **kwargs):
#         return self.reflect_param.target.flags.get("help", "")


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

    def init_instance(self, reflect_method, **kwargs):
        self.name = reflect_method.http_method_name.lower()
        self.reflect_method = reflect_method

#         # TODO -- add responses

    def get_request_body_value(self, **kwargs):
        if self.reflect_method.has_body():
            request_body = self.create_instance(
                "request_body_class",
                **kwargs
            )

            for reflect_param in self.reflect_method.reflect_body_params():
                request_body.add_param(reflect_param)

            return request_body

    def get_parameters_value(self, **kwargs):
        parameters = []

        # this is a positional argument (part of path) or query param
        # (after the ? in the url)
        for reflect_param in self.reflect_method.reflect_url_params():
            parameter = self.create_instance("parameter_class")
            parameter.set_param(reflect_param)
#             parameter = self.create_param_parameter_instance(reflect_param)
            parameters.append(parameter)

        return parameters

#     def create_param_parameter_instance(self, reflect_param):
#         parameter = self.create_instance("parameter_class")
#         parameter.set_param(reflect_param)
#         return parameter


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
                f"PathItem has multiple {operation.name} keys"
            )

        else:
            self[operation.name] = operation


class Paths(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object
    """
    def add_controller(self, reflect_controller, **kwargs):
        for reflect_method in reflect_controller.reflect_http_methods():
            path = reflect_method.get_url_path()
            if path not in self:
                self[path] = self.create_instance(
                    "path_item_class",
                    **kwargs
                )

            op = self.create_instance(
                "operation_class",
                reflect_method,
                **kwargs
            )
            self[path].add_operation(op)

    def add_pathfinder(self, pathfinder):
        for keys, value in pathfinder.get_class_items():
            reflect_controller = self.create_reflect_controller_instance(
                keys,
                value
            )

            self.add_controller(reflect_controller)

    def create_reflect_controller_instance(self, keys, value, **kwargs):
        return kwargs.get("reflect_controller_class", ReflectController)(
            keys,
            value
        )


class OpenAPI(OpenABC):
    """Represents an OpenAPI 3.1.0 document

    https://github.com/OpenAPITools/openapi-generator
    https://github.com/OAI/OpenAPI-Specification

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

    _paths = Field(Paths[str, PathItem])

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
#         https://pyyaml.org/
#         https://stackoverflow.com/a/18210750
#         """
#         pass

    def write_json(self, directory):
        """Writes openapi.json file to directory
        """
        dp = Dirpath(directory)
        fp = dp.get_file("openapi.json")
        # https://docs.python.org/3/library/json.html#encoders-and-decoders
        data = json.dumps(self)
        # TODO -- maybe add an is_valid that will run for each object and
        # make sure are the fields that are marked required exist
        pout.v(data)

        pass

    def get_info_value(self, **kwargs):
        return self.create_instance("info_class", **kwargs)

    def get_paths_value(self, **kwargs):
        """Represents a Pseudo OpenApi paths object

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object

        The keys are the path (starting with /) and the value are a Path Item
        object

        :returns: generator[str, PathItem]
        """
        paths = self.create_instance("paths_class", **kwargs)
        paths.add_pathfinder(self.application.router.pathfinder)
        return paths



#         return
# #         paths_class = self._paths.get_factory_class()
# #         paths = paths_class()
# 
#         pathfinder = self.application.router.pathfinder
#         for keys, value in pathfinder.get_class_items():
#             paths.update(
#                 self.create_controller_paths(
#                     keys,
#                     value,
#                     **kwargs
#                 )
#             )
# 
#         return paths
# 
#     def create_controller_paths(self, keys, value, **kwargs):
#         rc = kwargs.get("reflect_controller_class", ReflectController)(
#             keys,
#             value
#         )
#         return kwargs.get("paths_class", Paths)(
#             self,
#             reflect_controller=rc
#         )

