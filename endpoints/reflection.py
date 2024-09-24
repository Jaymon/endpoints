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
from .utils import Url, JSONEncoder
from .config import environ


class ReflectController(ReflectClass):
    def __init__(self, keys, value):
        super().__init__(value["class"])
        self.keys = keys
        self.value = value

    def reflect_http_methods(self, http_verb=""):
        """Reflect the controller http methods

        :returns generator[ReflectMethod], the controller method.
            There can be multiple of each http method name, so this can
            yield N GET methods, etc.
        """
        method_names = self.value["method_names"]

        for method_prefix, method_names in method_names.items():
            if not http_verb or method_prefix == http_verb:
                for method_name in method_names:
                    yield self.create_reflect_http_method_instance(
                        method_prefix,
                        name=method_name
                    )

    def create_reflect_http_method_instance(self, http_verb, **kwargs):
        """Creates ReflectMethod instances which are exclusively for
        a Controller's METHOD_* methods that handle requests"""
        target = self.get_target()
        kwargs.setdefault("target_class", target)
        return kwargs.get("reflect_http_method_class", ReflectMethod)(
            getattr(target, kwargs["name"]),
            http_verb,
            self,
            **kwargs
        )

    def get_url_path(self):
        """Get the root url path for this controller"""
        return "/" + "/".join(self.keys)


class ReflectMethod(ReflectCallable):
    """Reflect a controller http handler method

    these are methods on the controller like GET and POST
    """
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

    def has_body(self):
        """Returns True if this method accepts a body in the request"""
        return self.name in set(["PUT", "POST", "PATCH"])

    def reflect_params(self):
        """This will reflect all params defined with the @param decorator"""
        unwrapped = self.get_unwrapped()
        if params := getattr(unwrapped, "params", []):
            for param in (p.param for p in params):
                yield self.create_reflect_param_instance(param)

    def reflect_body_params(self):
        """This will reflect all the params that are usually passed up using
        the body on a POST request"""
        if self.has_body():
            for rp in self.reflect_params():
                if rp.target.is_kwarg:
                    yield rp

    def reflect_url_params(self):
        """This will reflect params that need to be in the url path or the
        query part of the url"""
        for rp in self.reflect_params():
            if not rp.target.is_kwarg or not self.has_body():
                yield rp

    def reflect_path_params(self):
        """This will reflect params that need to be in the path"""
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
        """Get the path for this method. The reason why this is on the method
        and not the controller is because there could be path parameters
        for specific methods which means a controller, while having the
        same root path, can have different method paths"""
        return "/".join(
            itertools.chain(
                self.reflect_class().get_url_path(),
                (f"{{{p.name}}}" for p in self.reflect_path_params())
            )
        )

    def get_http_verbs(self):
        """Controllers support an ANY catch-all method, this doesn't work
        for things like OpenAPI so this returns all the http methods this
        method should be used for. By default, ANY would return GET and POST

        :returns: generator[str]
        """
        if self.http_verb == "ANY":
            names = ["GET", "POST"]

        else:
            names = [self.http_verb]

        return names


class ReflectParam(object):
    """Reflects a Param instance"""
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

    def reflect_class(self):
        return self.reflect_method().reflect_class()

    def reflect_method(self):
        return self._reflect_method

    def is_required(self):
        return self.target.flags.get("required", False)

    def reflect_type(self):
        list_actions = set(["append", "append_list", "store_list"])
        if self.flags["action"] in list_actions:
            t = list

        else:
            t = self.flags.get("type", str)
            if t is None:
                t = str

        return self.create_reflect_type(t)


class Field(dict):
    """Represents a field on an OpenABC instance

    By default, fields should be defined on OpenABC children prefixed with
    an underscore, this is because many fields would conflict with python
    keywords (like `in`), this underscore will be stripped for the
    OpenABC.fields dict that maps field names to their Field instances
    """
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


class OpenFinder(ClassFinder):
    """Used by OpenABC to keep track of all children"""
    def _is_valid_subclass(self, klass):
        return issubclass(klass, OpenABC) and klass is not OpenABC

    def add_node(self, key, node, value):
        super().add_node(key, node, value)

        # this is the root node
        if not self.parent and len(self) == 1:
            self.class_keys = {}

        class_key = f"{NamingConvention(key.__name__).varname()}_class"
        self.root.class_keys[class_key] = key


class OpenEncoder(JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.item_separator = ": "
        self.indent = 2
        self.sort_keys = True

#     def encode(self, o):
#         pout.v(type(o))
#         return super().encode(o)



class OpenABC(dict):
    """The base type for all the OpenAPI objects

    Children classes have a few ways to customize functionality:

        * define `init_instance`, this allows a child class to require 
            arguments when being created, and also allows instance
            customization
        * override `set_keys`, this allows children to customize/normalize
            the keys/values after all the introspection stuff has ran. Any
            child that overrides this method *should* call super
        * define `get_<FIELDNAME>_value(**kwargs)`, this method should always
            take `**kwargs` and it should return whatever the value the
            child wants for that key. The majority of customizations will
            probably be in these methods

    You should always create OpenABC instances using:

        .create_instance(class_key, *args, **kwargs)

    the `class_key` is the class name you want to create, for example, if you
    wanted to create a `Parameter` instance, you would pass in
    "parameter_class" as the class_key. The class keys are found in
    `.classfinder.class_keys` of any OpenABC instance.

    The primary external hook for creating an OpenAPI document is to use the
    `OpenAPI` class, this class takes an interface Application instance:

        from endpoints.interface.asgi import Application
        from endpoints.reflection import OpenAPI

        application = Application()
        oa = OpenAPI(application)
        oa.write_json("/some/directory")
    """

    fields = None
    """Holds all the fields defined for the child instance"""

    parent = None
    """Holds the OpenABC class that created this instance"""

    root = None
    """Holds the absolute root of the OpenApi document, this will
    be an OpenAPI instance"""

    classfinder = OpenFinder()
    """This is used for children to easily get the absolute child class and
    is used in .create_instance"""

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
        """This is here for children to set arguments the class needs to
        successfully get setup"""
        pass

    def set_keys(self, **kwargs):
        if self.fields:
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

            if "summary" in self.fields and "summary" not in self:
                if desc := self.get("description", ""):
                    self["summary"] = self["description"].partition("\n")[0]

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
                if k in self:
                    if isinstance(self[k], list):
                        it = self[k]

                    elif isinstance(self[k], dict):
                        it = self[k].values()

                    else:
                        it = [self[k]]

                    for v in it:
                        if isinstance(v, OpenABC):
                            v.validate()

                else:
                    if field["required"]:
                        raise KeyError(
                            f"{self.__class__.__name__}[{k}]"
                        )


class Contact(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#contact-object
    """
    pass


class License(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#license-object
    """
    pass


class ServerVariable(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-variable-object
    """
    pass


class Reference(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#reference-object
    """
    pass


class Link(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#link-object
    """
    pass


class Header(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#header-object
    """
    pass


class Example(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#example-object
    """
    pass


class Callback(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#callback-object
    """
    pass


class OAuthFlows(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#oauth-flows-object
    """
    pass


class Tag(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#tag-object
    """
    pass


class ExternalDocumentation(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#external-documentation-object
    """
    pass


class Info(OpenABC):
    """Represents an OpenAPI info object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#info-object
    """
    _title = Field(str, required=True, default="Endpoints API")

    _version = Field(str, required=True, default="0.1.0")

    _description = Field(str)

    _summary = Field(str)

    _termsOfService = Field(str)

    _contact = Field(Contact)

    _license = Field(License)

    def init_instance(self, application, **kwargs):
        self.application = application


class Server(OpenABC):
    """Represents an OpenAPI server object

    From the docs:
        the default value would be a Server Object with a url value of /

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-object
    """
    _url = Field(str, default="/", required=True)

    _description = Field(str)

    _variables = Field(dict[str, ServerVariable])


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
    # this is set in the root OpenAPI document
    _schema = Field(
        str,
        name="$schema",
        #default="https://json-schema.org/draft/2020-12/schema"
    )

    DIALECT = "https://json-schema.org/draft/2020-12/schema"

    def add_param(self, reflect_param):
        """Add a param to this object schema"""
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
        """Set this schema as this param"""
        self.reflect_param = reflect_param
        self.update(self.get_param_fields(reflect_param))

    def set_type(self, reflect_type):
        """Set this schema as this type"""
        self.reflect_type = reflect_type
        self.update(self.get_type_fields(reflect_type))

    def get_param_fields(self, reflect_param):
        ret = {}
        param = reflect_param.target

        reflect_type = reflect_param.reflect_type()
        ret.update(self.get_type_fields(reflect_type))

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

    def get_type_fields(self, reflect_type):
        """Convert a python type t to a JSON Schema type

        https://json-schema.org/understanding-json-schema/reference/type
        """
        ret = {}
        rt = reflect_type

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

    def add_param(self, reflect_param):
        if "schema" not in self:
            self["schema"] = self.create_schema_instance(type="object")

        self["schema"].add_param(reflect_param)

    def set_type(self, reflect_type):
        schema = self.create_schema_instance()
        schema.set_type(reflect_type)
        self["schema"] = schema


class RequestBody(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#request-body-object
    """
    _description = Field(str)

    _content = Field(dict[str, MediaType], required=True)

    _required = Field(bool)

    def init_instance(self, reflect_method, **kwargs):
        self.reflect_method = reflect_method

    def add_param(self, reflect_param):
        for media_type in self["content"].values():
            media_type.add_param(reflect_param)

    def set_keys(self, **kwargs):
        super().set_keys(**kwargs)

        for reflect_param in self.reflect_method.reflect_body_params():
            self.add_param(reflect_param)

    def get_content_value(self, **kwargs):
        return {
            "*/*": self.create_instance("media_type_class", **kwargs)
        }


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


class Response(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#response-object
    """
    _description = Field(str, required=True)

    _headers = Field(dict[str, Header|Reference])

    _content = Field(dict[str, MediaType])

    _links = Field(dict[str, Link|Reference])

    def init_instance(self, reflect_method, code, **kwargs):
        self.reflect_method = reflect_method
        self.code = str(code)

    def set_type(self, reflect_type):
        for media_type in self["content"].values():
            media_type.set_type(reflect_type)

    def set_returns(self, returns):
        pass

    def get_description_value(self, **kwargs):
        return f"A {self.code} response"

    def get_content_value(self, **kwargs):
        #rc = self.reflect_method.reflect_class()
        # support Accept header response:
        # https://stackoverflow.com/a/62593737
        # https://github.com/OAI/OpenAPI-Specification/discussions/2777
        content_type = environ.RESPONSE_CONTENT_TYPE
        for rd in self.reflect_method.reflect_ast_decorators():
            if rd.name == "version":
                dargs, dkwargs = rd.get_parameters()
                version = dargs[0]
                content_type += f"; version={version}"
                break

        return {
            content_type: self.create_instance("media_type_class")
        }


class SecurityRequirement(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#security-requirement-object
    """
    def init_instance(self, reflect_method, **kwargs):
        self.reflect_method = reflect_method

    def set_keys(self, **kwargs):
        super().set_keys(**kwargs)

        for rd in self.reflect_method.reflect_ast_decorators():
            if rd.name.startswith("auth_"):
                self[rd.name] = []


class SecurityScheme(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#security-scheme-object
    """
    _type = Field(str, required=True)

    _description = Field(str)

    _name = Field(str)

    _in = Field(str)

    _scheme = Field(str)

    _bearerFormat = Field(str)

    _flows = Field(OAuthFlows)

    _openIdConnectUrl = Field(str)


class Operation(OpenABC):
    """Represents an OpenAPI operation object

    An operation is an HTTP scheme handler (eg GET, POST)

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#operation-object
    """
    _tags = Field(list[str])

    _summary = Field(str)

    _description = Field(str)

    _externalDocs = Field(ExternalDocumentation)

    _operationId = Field(str)

    _parameters = Field(list[Parameter|Reference])

    _requestBody = Field(RequestBody|Reference)

    _responses = Field(dict[str, Response|Reference])
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#responses-object
    """

    _callbacks = Field(dict[str, Callback])

    _deprecated = Field(bool)

    _security = Field(list[SecurityRequirement])

    _servers = Field(list[Server])

    def init_instance(self, reflect_method, **kwargs):
        self.reflect_method = reflect_method

    def get_request_body_value(self, **kwargs):
        if self.reflect_method.has_body():
            return self.create_instance(
                "request_body_class",
                self.reflect_method,
                **kwargs
            )

    def get_parameters_value(self, **kwargs):
        parameters = []

        # this is a positional argument (part of path) or query param
        # (after the ? in the url)
        for reflect_param in self.reflect_method.reflect_url_params():
            parameter = self.create_instance("parameter_class")
            parameter.set_param(reflect_param)
            parameters.append(parameter)

        return parameters

    def get_security_value(self, **kwargs):
        sreqs = []
        sr = self.create_instance(
            "security_requirement_class",
            self.reflect_method,
            **kwargs
        )
        if sr:
            sreqs = [sr]

        return sreqs

    def get_success_responses_value(self):
        responses = {}
        if rt := self.reflect_method.reflect_return_type():
            response = self.create_response_instance("200")
            response.set_type(rt)
            responses[response.code] = response

        elif returns := list(self.reflect_method.reflect_ast_returns()):
                response = self.create_response_instance("200")
                response.set_returns(returns)
                responses[response.code] = response

        else:
            response = self.create_response_instance("204")
            responses[response.code] = response

        return responses

    def get_error_responses_value(self):
        responses = {}
        for rx in self.reflect_method.reflect_ast_raises():
            if rx.name == "CallError" or rx.name == "CallStop":
                errargs, errkwargs = rx.get_parameters()
                response = self.create_response_instance(
                    errargs[0],
                    description=errargs[1]
                )
                responses[response.code] = response

            elif rc.name == "ValueError":
                errargs, errkwargs = rx.get_parameters()
                response = self.create_response_instance(
                    "400",
                    description="Missing value"
                )
                responses[response.code] = response


        for rp in self.reflect_method.reflect_params():
            if rp.is_required():
                response = self.create_response_instance(
                    "400",
                    description=f"Invalid params"
                )
                responses[response.code] = response
                break

        for rd in self.reflect_method.reflect_ast_decorators():
            if rd.name.startswith("auth"):
                response = self.create_response_instance(
                    "401",
                    description="Unauthorized request"
                )
                responses[response.code] = response
                break

        return responses

    def get_responses_value(self, **kwargs):
        responses = self.get_success_responses_value()
        responses.update(self.get_error_responses_value())
        return responses

    def create_response_instance(self, code, **kwargs):
        return self.create_instance(
            "response_class",
            self.reflect_method,
            code,
            **kwargs
        )


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

    def add_method(self, reflect_method, **kwargs):
        op = self.create_instance(
            "operation_class",
            reflect_method,
            **kwargs
        )

        for http_verb in reflect_method.get_http_verbs():
            field_name = http_verb.lower()
            if field_name in self:
                raise ValueError(
                    f"PathItem has multiple {field_name} keys"
                )

            else:
                self[field_name] = op


class Paths(OpenABC):
    def add_controller(self, reflect_controller, **kwargs):
        for reflect_method in reflect_controller.reflect_http_methods():
            path = reflect_method.get_url_path()
            if path not in self:
                self[path] = self.create_instance(
                    "path_item_class",
                    **kwargs
                )

            self[path].add_method(reflect_method, **kwargs)


class Components(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#components-object
    """
    _schemas = Field(dict[str, Schema])

    _responses = Field(dict[str, Response|Reference])

    _parameters = Field(dict[str, Parameter|Reference])

    _examples = Field(dict[str, Example|Reference])

    _requestBodies = Field(dict[str, RequestBody|Reference])

    _headers = Field(dict[str, Header|Reference])

    _securitySchemes = Field(dict[str, SecurityScheme|Reference])

    _links = Field(dict[str, Link|Reference])

    _callbacks = Field(dict[str, Callback|Reference])

    _pathItems = Field(dict[str, PathItem|Reference])

    def get_security_schemes_value(self, **kwargs):
        schemas = {}
        class_key = "security_scheme_class"

        schema = self.create_instance(class_key, **kwargs)
        schema["type"] = "http"
        schema["scheme"] = "basic"
        schemas["auth_basic"] = schema

        schema = self.create_instance(class_key, **kwargs)
        schema["type"] = "http"
        schema["scheme"] = "bearer"
        schemas["auth_bearer"] = schema

        return schemas


class OpenAPI(OpenABC):
    """Represents an OpenAPI 3.1.0 document

    This is the primary class for creating an OpenAPI document. See the
    OpenABC docblock for examples

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md
    https://github.com/OpenAPITools/openapi-generator
    https://github.com/OAI/OpenAPI-Specification

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#openapi-object
    """
    _openapi = Field(str, default="3.1.0", required=True)

    _info = Field(Info, required=True)

    _servers = Field(list[Server])

    _paths = Field(dict[str, PathItem])
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object
    """

    _components = Field(Components)

    _security = Field(list[SecurityRequirement])

    _tags = Field(Tag)

    _externalDocs = Field(ExternalDocumentation)

    _jsonSchemaDialect = Field(str, default=Schema.DIALECT)

    def __init__(self, application, **kwargs):
        """
        NOTE -- this has to override __init__ because it takes the application
        as the first argument, something none of the other OpenABC children
        do"""
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

        :param directory: str, the directory path
        :returns: str, the path to the openapi.json file
        """
        self.validate()

        dp = Dirpath(directory)
        fp = dp.get_file("openapi.json")
        # https://docs.python.org/3/library/json.html#encoders-and-decoders
        data = json.dumps(self, cls=OpenEncoder)
        fp.write_text(data)
        return fp

    def get_info_value(self, **kwargs):
        return self.create_instance("info_class", self.application, **kwargs)

    def get_paths_value(self, **kwargs):
        """Represents a Pseudo OpenApi paths object

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object

        The keys are the path (starting with /) and the value are a Path Item
        object

        :returns: dict[str, PathItem]
        """
        paths = {}
        for reflect_controller in self.reflect_controllers():
            for reflect_method in reflect_controller.reflect_http_methods():
                path = reflect_method.get_url_path()
                if path not in paths:
                    paths[path] = self.create_instance(
                        "path_item_class",
                        **kwargs
                    )

                paths[path].add_method(reflect_method, **kwargs)

        return paths

    def get_components_value(self, **kwargs):
        return self.create_instance("components_class", **kwargs)

    def reflect_controllers(self):
        """Reflect all the controllers of this application"""
        pathfinder = self.application.router.pathfinder
        for keys, value in pathfinder.get_class_items():
            yield self.create_reflect_controller_instance(
                keys,
                value
            )

    def create_reflect_controller_instance(self, keys, value, **kwargs):
        return kwargs.get("reflect_controller_class", ReflectController)(
            keys,
            value
        )

