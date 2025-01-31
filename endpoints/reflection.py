# -*- coding: utf-8 -*-
import re
import itertools
from collections import defaultdict
import inspect
import uuid
from typing import (
    Any, # https://docs.python.org/3/library/typing.html#the-any-type
)
import json
import datetime
import logging
from string import Template

from datatypes import (
    ReflectClass,
    ReflectCallable,
    ReflectType,
    classproperty,
    cachedproperty,
    Dirpath,
    NamingConvention,
    ClassFinder,
    HTTPClient,
)
from datatypes.reflection import ReflectObject

# for `OpenAPI.write_yaml` support
try:
    import yaml
except ImportError:
    yaml = None

# For `Schema.validate` support
try:
    import jsonschema
    from jsonschema.validators import validator_for
    from referencing import Registry
    import referencing.retrieval

except ImportError:
    jsonschema = None

from .compat import *
from .utils import Url, JSONEncoder, Status
from .config import environ


logger = logging.getLogger(__name__)


class ReflectController(ReflectClass):
    def __init__(self, keys, value):
        """
        :param keys: list[str], the Controller path keys used in Pathfinder
        :param value: dict[str, Any], the Controller information in Pathfinder
        """
        super().__init__(value["class"])
        self.keys = keys
        self.value = value

    def reflect_url_modules(self):
        """Reflect the controller modules for this controller

        Controller modules are modules that can be part of a request path

        :returns: generator[ReflectModule], this returns the reflected module
            for each iteration
        """
        if mks := self.value.get("module_keys", []):
            for i, mk in enumerate(mks):
                rm = self.create_reflect_module(self.value["modules"][i])
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
                yield self.create_reflect_http_method_instance(
                    method_http_verb,
                    method_name
                )

    def create_reflect_http_method_instance(
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

    def get_url_path(self):
        """Get the root url path for this controller

        This will not include any url path params. Since methods can define
        url path params you want to call this same method on ReflectMethod
        instances to get the full url path for a given http verb
        """
        return "/" + "/".join(self.keys)

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

    def get_http_method_names(self):
        """An HTTP method (eg GET or POST) needs to be handled by a controller
        class. So a controller can have a method named GET and that will be
        called when GET <PATH-TO-CONTROLLER> is called. But wait, there's more,
        there can actually be multiple methods defined that all start with
        <HTTP-METHOD> (eg, GET_1, GET_2, etc)

        Although you can define any http methods (a method is valid if it is
        all uppercase), here is a list of rfc approved http request methods:

            http://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol#Request_methods

        :returns: dict[str, list[str]], the keys are the HTTP method and the
            values are all the method names that satisfy that HTTP method.
            these method names will be in alphabetical order to make it so they
            can always be checked in the same order
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

    def reflect_query_params(self):
        """This will reflect params that need to be in the query part of the
        url"""
        for rp in self.reflect_params():
            if rp.target.is_kwarg and not self.has_body():
                yield rp

    def reflect_path_params(self):
        """This will reflect params that need to be in the url path"""
        rps = []
        for rp in self.reflect_params():
            if not rp.target.is_kwarg:
                rps.append(rp)

        # now they need to be sorted to make sure they are in order: 0 -> N
        return sorted(rps, key=lambda rp: rp.get_target().index)

    def create_reflect_param_instance(self, param, **kwargs):
        kwargs["reflect_method"] = self
        return kwargs.pop("reflect_param_class", ReflectParam)(
            param,
            **kwargs
        )

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

    def get_method_info(self):
        reflect_class = self.reflect_class()
        mns = reflect_class.value["http_method_names"]
        for method_info in mns.get(self.http_verb, mns.get("ANY", {})):
            if method_info["method_name"] == self.name:
                return method_info

    def create_reflect_http_method_instance(self, http_verb, **kwargs):
        """Basically clone this instance but for the specific http_verb

        This is mainly for things like ANY

        :param http_verb: str, the http verb (eg, GET or POST)
        :returns: ReflectMethod, it will have the same target as
            self.get_target() but, most likely, a different http_verb
        """
        return self.reflect_class().create_reflect_http_method_instance(
            http_verb,
            self.name,
            **kwargs
        )

    def has_body(self):
        """Returns True if http_verb accepts a body in the request"""
        return self.http_verb_has_body(self.http_verb)


class ReflectParam(ReflectObject):
    """Reflects a Param instance

    Reflected params only apply to http methods on controllers
    """
    def __init__(self, target, reflect_method, **kwargs):
        self._reflect_method = reflect_method
        super().__init__(target)

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
        """Reflect the param's type argument if present"""
        flags = self.get_target().flags
        list_actions = set([
            "store_list",
            "append",
            "append_list",
            "extend",
        ])
        if flags["action"] in list_actions:
            t = list

        else:
            t = flags.get("type", str)
            if t is None:
                t = str

        return self.create_reflect_type(t)


class Field(dict):
    """Represents a field on an OpenABC instance

    By default, fields should be defined on OpenABC children prefixed with
    an underscore, this is because many field names would conflict with python
    keywords (like `in`), this underscore will be stripped for the
    OpenABC.fields dict that maps field names to their Field instances
    """
    def __init__(self, field_type, **kwargs):
        """
        :param field_type: Any, the type information for this field
        :keyword name: Optional[str], the name of the field, this is usually
            passed in if the field needs to be different than the field's
            name with prefixed underscores stripped (eg, "$foo")
        :keyword required: Optional[bool], defaults to False
        :keyword todict_empty_value: Optional[Any], this value will be
            returned in `OpenABC.todict_value` if the field's value is empty
        """
        self.name = kwargs.pop("name", "")
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

    def find_class(self, class_key):
        return self.root.class_keys[class_key]


class OpenABC(dict):
    """The base type for all the OpenAPI objects

    Children classes have a few ways to customize functionality:

        * define `init_instance`, this allows a child class to require 
            arguments when being created, and also allows instance
            customization
        * override `set_fields`, this allows children to customize/normalize
            the keys/values after all the introspection stuff has ran. Any
            child that overrides this method *should* call super
        * define `get_<FIELDNAME>_value(**kwargs)`, this method should always
            take `**kwargs` and it should return whatever the value the
            child wants for that key in the instance. The majority of
            customizations will probably be in these methods

    Fields for the given children class should use the `Field` instance and
    they should start with an underscore (eg, `_<FIELD-NAME>`). The order the
    field are defined is important, the order the fields are defined in is the
    order they will be checked and populated on the instance and this is
    recursive, so if have `foo` field after `bar` field, and `bar` creates
    other `OpenABC` instances that want to retrieve the `foo` value from a
    parent instance then `foo` should be changed to go before `bar`

    You should always create OpenABC instances internally using:

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
    """Holds all the fields defined for the child instance, this is populated
    on the class in the Field.__init__ method. This is set to `None` instead
    of `dict` because if it is a class property `dict` then it will inherit
    all other class's values also"""

    parent = None
    """Holds the OpenABC class that created this instance"""

    root = None
    """Holds the absolute root of the OpenApi document, this will
    be an OpenAPI instance"""

    classfinder = OpenFinder()
    """This is used for children to easily get the absolute child class and
    is used in .create_instance"""

    @property
    def path_str(self):
        return " -> ".join(
            (p.__class__.__name__ for p in self.get_traversal_path())
        )

    def __init__(self, parent, *args, **kwargs):
        if parent is None:
            self.root = self

        else:
            self.parent = parent
            self.root = parent.root

        super().__init__()

        if parent is None:
            logger.debug(f"Creating class: {self.__class__.__name__}")

        else:
            logger.debug(f"Created child: {self.path_str}")

        self.init_instance(*args, **kwargs)
        self.set_fields(**kwargs)

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
            value.validate_fields()

        super().__setitem__(key, value)

    def get_traversal_path(self):
        """Returns the OpenABC classes/node starting from the root class/node
        to get to this class/node of the document

        This basically traverses the .parent property

        :returns: list[OpenABC]
        """
        path = []
        p = self.parent
        while p is not None:
            path.insert(0, p)
            p = p.parent

        path.append(self)

        return path

    def init_instance(self, *args, **kwargs):
        """This is here for children to set arguments the class needs to
        successfully get setup"""
        pass

    def set_fields(self, **kwargs):
        if self.fields:
            for k, field in self.fields.items():
                if k in kwargs:
                    if kwargs[k]:
                        self[k] = kwargs[k]

                else:
                    if m := self.get_value_method(k, field):
                        logger.debug(
                            f"Calling {self.path_str}.{m.__name__}"
                            f" to set \"{k}\" key"
                        )
                        if v := m(**kwargs):
                            self[k] = v

                if k not in kwargs and k not in self:
                    if "default" in field:
                        self[k] = field["default"]

    def set_docblock(self, docblock, **kwargs):
        if docblock and "description" in self.fields:
            self["description"] = docblock

            # let's set the summary using the docblock also
            if "summary" in self.fields:
                if not self.get("summary", ""):
                    self["summary"] = docblock.partition("\n")[0]

    def get_value_method(self, field_name, field):
        """Each instance can define a get_<FIELD_NAME>_value method that can
        be used to set the value for that field, this method checks the
        instance for that method

        :param field_name: str, the field name
        :param field: Field, the field instance
        :returns: Callable[[...], Any]
        """
        name = NamingConvention(field_name)
        method_name = f"get_{name.varname()}_value"
        return getattr(self, method_name, None)

    def create_instance(self, class_key, *args, **kwargs):
        """
        NOTE -- these create_* methods can't be class methods because they
        pass self in as the first argument to any new instance to make the
        tree traversable
        """
        if class_key in kwargs:
            open_class = kwargs[class_key]

        else:
            open_class = self.classfinder.find_class(class_key)

        return open_class(self, *args, **kwargs)

    def create_schema_instance(self, **kwargs):
        return self.create_instance("schema_class", **kwargs)

    def create_object_schema_instance(self):
        schema = self.create_schema_instance()

        if "type" not in schema:
            schema["type"] = "object"

        else:
            if schema["type"] != "object":
                raise ValueError(
                    f"Attempted to set type {schema['type']} schema as object"
                )

        schema["properties"] = {}
        schema["required"] = []

        return schema

    def create_array_schema_instance(self):
        """
        https://json-schema.org/understanding-json-schema/reference/array
        """
        schema = self.create_schema_instance()

        if "type" in schema:
            if schema["type"] != "array":
                raise ValueError(
                    f"Attempted to set type {schema['type']} schema as array"
                )

        else:
            schema["type"] = "array"

        schema["items"] = self.create_schema_instance()

        return schema

    def validate_fields(self):
        """Validate self and all children to make sure they are valid"""
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
                            v.validate_fields()

                else:
                    if field["required"]:
                        raise KeyError(
                            f"Class {self.path_str} missing {k} key"
                        )

    def todict_value(self, k, v):
        """Internal method. Called from `.todict` to generate the dict value
        for `v`

        By default, this will check the field found at k's empty_todict value
        and if it is False it will return None if v is considered empty

        :param v: Any
        :returns: Optional[dict]
        """
        fields = self.fields or {}

        if not v and "todict_empty_value" in fields.get(k, {}):
            v = self.fields[k]["todict_empty_value"]

        elif m := getattr(v, "todict", None):
            v = m()

        elif isinstance(v, dict):
            v = {vk: self.todict_value(vk, vv) for vk, vv in v.items()}

        elif isinstance(v, list):
            v = [self.todict_value(None, vv) for vv in v]

        return v

    def todict_items(self):
        """Similar to `.todict_value` this allows child classes to customize
        the .todict output

        :returns: generator[tuple[str, Any]]
        """
        yield from self.items()

    def todict(self):
        """Normalize self and all children as builtin python values (eg dict,
        list)

        This internally calls `.todict_value` and will ignore any None values
        returned from that method, this way child classes can customize their
        output by overriding `.todict_value`

        :returns: dict
        """
        d = {}
        for k, v in self.todict_items():
            v = self.todict_value(k, v)
            if v is not None:
                d[k] = v

        return d


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


class ExternalDocumentation(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#external-documentation-object
    """
    pass


class Server(OpenABC):
    """Represents an OpenAPI server object

    From the docs:
        the default value would be a Server Object with a url value of /

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#server-object
    """
    _url = Field(str, default="/", required=True)

    _description = Field(str)

    _variables = Field(dict[str, ServerVariable])


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


class SecurityRequirement(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#security-requirement-object
    """
    def init_instance(self, reflect_method, **kwargs):
        self.reflect_method = reflect_method

    def set_fields(self, **kwargs):
        super().set_fields(**kwargs)

        for rd in self.reflect_method.reflect_ast_decorators():
            name = rd.name
            if name.startswith("auth_"):
                security_schemes = self.root.components.securitySchemes
                for scheme_name in security_schemes.keys():
                    if scheme_name.startswith(name):
                        self[name] = []


class Tag(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#tag-object
    """
    _name = Field(str, required=True)

    _description = Field(str)

    _externalDocs = Field(ExternalDocumentation)

    def init_instance(self, reflect_module, **kwargs):
        self.reflect_module = reflect_module

    def get_name_value(self):
        return self.reflect_module.module_key

    def get_description_value(self):
        return self.reflect_module.get_docblock()


class Schema(OpenABC):
    """Represents a JSON Schema

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#schema-object

    Getting started:
        https://json-schema.org/learn/getting-started-step-by-step

    All the keywords:
        https://json-schema.org/understanding-json-schema/keywords

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
    _properties = Field(dict[str, dict], todict_empty_value=None)
    _patternProperties = Field(dict[str, dict])
    _additionalProperties = Field(bool|dict)
    _unevaluatedProperties = Field(bool)
    _required = Field(list[str], todict_empty_value=None)
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

    # https://json-schema.org/understanding-json-schema/reference/comments
    _comment = Field(str, name="$comment")

    # https://json-schema.org/understanding-json-schema/reference/schema
    # this is set in the root OpenAPI document
    _schema = Field(str, name="$schema")

    # This is currently not used but I'm keeping this in here for the future
    # https://json-schema.org/understanding-json-schema/basics#declaring-a-unique-identifier
    # https://json-schema.org/understanding-json-schema/structuring#id
    _id = Field(str, name="$id")

    # https://json-schema.org/understanding-json-schema/structuring#dollarref
    # https://json-schema.org/draft/2020-12/json-schema-core#ref
    # https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.1.md#reference-object
    #
    # https://datatracker.ietf.org/doc/html/draft-pbryan-zyp-json-ref-03#section-3
    #   Any members other than "$ref" in a JSON Reference object SHALL be
    #   ignored.
    _ref = Field(str, name="$ref")

    # Swagger warns that the jsonschema spec needs to be the OpenAPI version
    # the default JSON Schema dialect is:
    #    https://json-schema.org/draft/2020-12/schema
    DIALECT = "https://spec.openapis.org/oas/3.1/dialect/base"

    def is_type(self, typename):
        """Helper method that returns True if self's type is typename"""
        return typename and self.get("type", "") == typename

    def is_object(self):
        """Helper method that returns True if self is an object schema"""
        return self.is_type("object")

    def is_array(self):
        """Helper method that returns True if self is an array schema"""
        return self.is_type("array")

    def is_ref(self):
        """Returns True if self is a reference to another schema"""
        return "$ref" in self

    def is_empty(self):
        ret = False
        if self.is_object():
            if self.get("properties", ""):
                ret = True

        elif self.is_array():
            if items := self.get("items", ""):
                ret = True
                if "anyOf" in items:
                    ret = True if items["anyOf"] else False

        else:
            if self:
                ret = True

        return ret

    def set_param(self, reflect_param):
        """Set this schema as this param"""
        self.reflect_param = reflect_param
        self.update(self.get_param_fields(reflect_param))

    def set_request_method(self, reflect_method):
        """This is called from RequestBody and is the main hook into
        customizing and extending the request schema for child projects"""
        self.reflect_method = reflect_method

        for reflect_param in reflect_method.reflect_body_params():
            self.set_object_keys()
            self.add_param(reflect_param)

        for reflect_param in reflect_method.reflect_url_params():
            self.set_object_keys()
            self.add_param(reflect_param)

    def set_response_method(self, reflect_method):
        """Called from Response and is the main hook into customizing and
        extending the response schema for child projects"""
        self.reflect_method = reflect_method
        if rt := self.reflect_method.reflect_return_type():
            self.set_type(rt)

    def set_error_method(self, reflect_method):
        self.reflect_method = reflect_method

    def set_type(self, reflect_type):
        """Set this schema as this type"""
        self.reflect_type = reflect_type
        self.update(self.get_type_fields(reflect_type))

    def add_param(self, reflect_param):
        """Internal method. Children might override .add_param for custom
        functionality but will still need to add a param to a sub-schema

        :param schema: Schema, usually a sub object schema of self that
            reflect_param is going be added to
        :param reflect_param: ReflectParam
        :returns: Schema
        """
        param_schema = self.create_schema_instance()
        param_schema.set_param(reflect_param)
        param_schema.pop("$schema", None)

        self.add_property_schema(
            reflect_param.name,
            param_schema,
            reflect_param.is_required()
        )

    def get_param_fields(self, reflect_param):
        """Internal method. Returns the schema fields for a param"""
        ret = {}
        param = reflect_param.get_target()

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
        """Internal method. Returns the size fields for schema_type

        :param schema_type: str, corresponds to `._type` field choice values
        :param min_size: int
        :param max_size: int
        :returns: dict[str, int], the key names will vary according to the
            `schema_type`
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
        """Internal method. Convert a python type to a JSON Schema type

        https://json-schema.org/understanding-json-schema/reference/type

        The exanded OpenAPI spec extends type formats:
            https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#data-types

        The json schema type formats:
            https://datatracker.ietf.org/doc/html/draft-bhutton-json-schema-validation-00#section-7.3
        """
        ret = {}
        rt = reflect_type

        if rt.is_stringish():
            ret["type"] = "string"

        elif rt.is_bool():
            ret["type"] = "boolean"

        elif rt.is_int():
            ret["type"] = "integer"
            ret["format"] = "int64" # expanded OpenAPI spec

        elif rt.is_numberish():
            ret["type"] = "number"
            ret["format"] = "float" # expanded OpenAPI spec

        elif rt.is_dictish():
            ret["type"] = "object"

            values = []
            for vt in rt.reflect_value_types():
                s = self.create_schema_instance()
                s.set_type(vt)
                values.append(s)

            if values:
                if len(values) > 1:
                    ret["additionalProperties"] = {"anyOf": values}

                else:
                    ret["additionalProperties"] = values[0]

        elif rt.is_listish():
            ret["type"] = "array"

            items = []
            for vt in rt.reflect_value_types():
                s = self.create_schema_instance()
                s.set_type(vt)
                items.append(s)

            if items:
                if rt.is_tuple():
                    # https://json-schema.org/understanding-json-schema/reference/array#tupleValidation
                    ret["prefixItems"] = items

                else:
                    if len(items) > 1:
                        # https://stackoverflow.com/a/70863145
                        ret["items"] = {"anyOf": items}

                    else:
                        ret["items"] = items[0]

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

    def set_object_keys(self):
        """Internal method. Children need to create sub-schemas of type object
        and this makes that possible

        :returns: Schema
        """
        if "type" not in self:
            self["type"] = "object"

        else:
            if self["type"] != "object":
                raise ValueError(
                    f"Attempted to set type {self['type']} schema as object"
                )

        self.setdefault("properties", {})
        self.setdefault("required", [])

    def add_property_schema(self, name, schema, required=False, **kwargs):
        """Set a property in object schema's "properties" key

        :param name: str, the property name
        :param schema: Schema, the property's json schema
        :param required: bool
        """
        self["properties"][name] = schema

        if required:
            self["required"].append(name)

    def get_property_schema(self, name, factory=None):
        """Internal method. Get or create the schema using factory at name
        and return it

        :param name: str, the schema name
        :param factory: Callable[[], Schema], the callable used to create the
            schema, if name doesn't exist, defaults to creating an
            object schema
        :returns: Schema, returns the newly added schema
        """
        d = self["properties"]

        if not factory:
            factory = self.create_object_schema_instance

        if name in d:
            schema = d[name]

        else:
            schema = factory()
            d[name] = schema

        return schema

    def get_components(self):
        """Get the components document from `.root`"""
        if self.root:
            return self.root.get("components", None)

    def get_components_schema(self, name_or_ref):
        """Wrapper around Component.get_schema"""
        if components := self.get_components():
            return components.get_schema(name_or_ref)

    def add_components_schema(self, name, schema):
        """Wrapper around Component.add_schema"""
        components = self.get_components()
        if components is None:
            raise ValueError(
                "A components document in a root document does not exist"
            )

        return components.add_schema(name, schema)

    def get_ref_schema(self):
        """If this schema is a ref then get the referenced schema"""
        if self.is_ref():
            if self["$ref"].startswith("#"):
                return self.get_components_schema(self["$ref"])

            else:
                raise ValueError("Unsupported $ref: {}".format(self["$ref"]))

    def validate(self, data):
        """Validate data against self (this schema)

        :param data: Mapping, the data to validate
        :returns: bool
        :raises: Exception, any validation problems will raise an exception
        """
        if not jsonschema:
            raise ValueError("Missing jsonschema dependency")

        dialect = self.get("$schema", self.DIALECT)

        # https://referencing.readthedocs.io/en/stable/intro/#caching
        @referencing.retrieval.to_cached_resource()
        def cached_retrieve(uri):
            return HTTPClient().get(uri).content

        registry = Registry(retrieve=cached_retrieve)
        lookup = registry.resolver().lookup(dialect)
        dialect_schema = lookup.resolver._registry.get(dialect).contents

        components_schemas = {}
        if components := self.get_components():
            components_schemas.update({
                "components": {
                    "schemas": components.get("schemas", {})
                }
            })

        validator_class = validator_for(dialect_schema)
        validator_class.META_SCHEMA = dialect_schema
        validator = validator_class({**self, **components_schemas})
        validator.validate(data)
        return True


class MediaType(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#media-type-object

    TODO -- file uploads:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#considerations-for-file-uploads
    """
    _schema = Field(Schema)

    _examples = Field(dict[str, Example|Reference])

    # this one has some strange requirements so I'm ignoring it right now
    #_encoding = Field(dict[str, Encoding])

    def set_request_method(self, reflect_method):
        """Called from RequestBody"""
        self.reflect_method = reflect_method
        schema = self.create_schema_instance()
        schema.set_request_method(reflect_method)
        if schema:
            self["schema"] = schema

    def set_response_method(self, reflect_method):
        """Called from Response"""
        self.reflect_method = reflect_method
        schema = self.create_schema_instance()
        schema.set_response_method(reflect_method)
        if schema:
            self["schema"] = schema

    def set_error_method(self, reflect_method):
        """Called from Response"""
        self.reflect_method = reflect_method
        schema = self.create_schema_instance()
        schema.set_error_method(reflect_method)
        if schema:
            self["schema"] = schema


class RequestBody(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#request-body-object
    """
    _description = Field(str)

    _content = Field(dict[str, MediaType], required=True)

    _required = Field(bool)

    def set_method(self, reflect_method):
        self.reflect_method = reflect_method

        content = {}

        for media_range in self.get_content_media_ranges(reflect_method):
            content[media_range] = self.create_instance("media_type_class")
            content[media_range].set_request_method(reflect_method)

        self["content"] = content

    def get_content_media_ranges(self, reflect_method):
        """Get all the media types/ranges this should support

        The media-range and media-type abnfs:
            media-range = ( "*/*" / ( type "/*" ) / ( type "/" subtype ) )
                *( OWS ";" OWS parameter )
            media-type = type "/" subtype *( OWS ";" OWS parameter )

        So media-range is a superset of media-type, and the key values for
        the content keys can be media-ranges, that's why this is using
        `*_media_ranges` instead of `*_media_types`

        https://en.wikipedia.org/wiki/Media_type

        :returns: list[str]
        """
        return ["*/*"]


class Response(OpenABC):
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#response-object

    This has a similar lifecycle to PathItem, it will try and call
    `.set_<CODE>_code`, if that method doesn't exist then it will just call
    `.set_<CODE-TYPE>_code`. This allows child classes to customize the output
    on a per code or code type basis

    Code types:
        * information - 1xx informational response – the request was received,
            continuing process
        * success - 2xx successful – the request was successfully received,
            understood, and accepted
        * redirect - 3xx redirection – further action needs to be taken in
            order to complete the request
        * error - 4xx client error – the request contains bad syntax or cannot
            be fulfilled
        * error - 5xx server error – the server failed to fulfil an apparently
            valid request

    https://en.wikipedia.org/wiki/List_of_HTTP_status_codes

    .. Example:
        # customize 401
        class CustomResponse(Response):
            def set_404_code(self):
                # custom stuff

    The merging behavior is similar to the status code behavior. You can add
    a .merge_<FIELD-NAME>_key method to customize the merging, it falls back
    to .merge_key

    .. Example:
        # customize merging the content key
        class CustomResponse(Response):
            def merge_content_key(self, key, content):
                # custom stuff
    """
    _description = Field(str, required=True)

    _headers = Field(dict[str, Header|Reference])

    _content = Field(dict[str, MediaType])

    _links = Field(dict[str, Link|Reference])

    def init_instance(self, code, reflect_method, **kwargs):
        self.code = str(code)
        self.reflect_method = reflect_method

    def get_content_value(self, **kwargs):
        m = self.get_set_code_method()
        content = m()

        if content:
            self["content"] = content

    def set_information_code(self):
        pass

    def set_redirect_code(self):
        pass

    def set_success_code(self):
        pass

    def set_200_code(self):
        content = {}

        for media_range in self.get_content_media_ranges():
            media_type = self.create_instance("media_type_class")
            media_type.set_response_method(self.reflect_method)
            if media_type:
                content[media_range] = media_type

        return content

    def set_error_code(self):
        content = {}

        for media_range in self.get_content_media_ranges():
            media_type = self.create_instance("media_type_class")
            media_type.set_error_method(self.reflect_method)
            if media_type:
                content[media_range] = media_type

        return content

    def get_set_code_method(self):
        """Get the set operation for this method

        This will try and find a valid .set_<HTTP_VERB>_method method and
        fallback to .set_http_verb_method

        :param reflect_method: ReflectMethod
        :returns: Callable[[ReflectMethod], None]
        """
        method_name = f"set_{self.code}_code"

        if self.code.startswith("1"):
            default_method = self.set_information_code

        elif self.code.startswith("2"):
            default_method = self.set_success_code

        elif self.code.startswith("3"):
            default_method = self.set_redirect_code

        else:
            default_method = self.set_error_code

        return getattr(self, method_name, default_method)

    def get_description_value(self, **kwargs):
        return str(Status(int(self.code), default=f"A {self.code} response"))

    def get_content_media_ranges(self):
        """See RequestBody.get_content_media_ranges"""
        reflect_method = self.reflect_method

        method_info = reflect_method.get_method_info()
        media_type = method_info.get(
            "response_media_type",
            environ.RESPONSE_MEDIA_TYPE
        )

        # support Accept header response:
        # https://stackoverflow.com/a/62593737
        # https://github.com/OAI/OpenAPI-Specification/discussions/2777
        if version := reflect_method.get_version():
            media_type += f"; version={version}"
        return [media_type]

    def merge(self, other):
        """Merges self with other

        :param other: Response
        """
        for key in self.fields.keys():
            if other_value := other.get(key, None):
                m = self.get_merge_key_method(key)
                m(key, other_value)

    def get_merge_key_method(self, key):
        """Internal method. Returns the method that will be used to merge
        the key's value into self

        :returns: Callable[[str, Any], None]
        """
        method_name = f"merge_{key}_key"
        return getattr(self, f"merge_{key}_key", self.merge_key)

    def merge_description_key(self, key, description):
        descs = []
        if d := self.get("description", ""):
            descs.append(d)

        descs.append(description)
        self["description"] = "\n".join(descs)

    def merge_content_key(self, key, content):
        # the first content key wins, all others are ignored. This is because
        # my current implementation basically produces the same error schema
        # for everything so there is no need to really distinguish
        if key not in self:
            self[key] = content

    def merge_key(self, key, value):
        """Internal method. The fallback/default method for
        .get_merge_key_method"""
        if key not in self:
            self[key] = value

        else:
            raise ValueError(f"Not sure how to merge key: {k}")


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

    #_example = Field(Any)

    _examples = Field(dict[str, Example|Reference])

    def set_param(self, reflect_param):
        self.reflect_param = reflect_param
        self.update(self.get_param_fields(reflect_param))

    def get_param_fields(self, reflect_param):
        ret = {}
        param = self.reflect_param.target

        if param.is_kwarg:
            ret["name"] = param.name
            ret["in"] = "query"
            ret["required"] = param.flags.get("required", False)
            ret["allowEmptyValue"] = param.flags.get("allow_empty", False)

        else:
            ret["name"] = reflect_param.name
            ret["in"] = "path"

            # spec: "If the parameter location is "path", this property is
            # REQUIRED and its value MUST be true"
            ret["required"] = True

        if desc := param.flags.get("help", ""):
            ret["description"] = desc

        schema = self.create_schema_instance()
        schema.set_param(reflect_param)
        ret["schema"] = schema

        return ret


class Operation(OpenABC):
    """Represents an OpenAPI operation object

    An operation is an HTTP scheme verb handler (eg GET, POST)

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#operation-object
    """
    _tags = Field(list[str])

    _summary = Field(str)

    _description = Field(str)

    _externalDocs = Field(ExternalDocumentation)

    _operationId = Field(str)

    _parameters = Field(list[Parameter|Reference], todict_empty_value=None)

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
        """Sets the required params when creating a new instance of this class

        :param reflect_method: ReflectMethod, this instance should have a
            PathItem supported http_verb which means instances for ANY or
            things like that should already have been handled
        """
        self.reflect_method = reflect_method
        self.set_docblock(reflect_method.get_docblock())

    def get_parameters_value(self, **kwargs):
        # if this operation has a body then we put the url params in the body
        # instead
        if not self.reflect_method.has_body():
            parameters = []

            # this is a positional argument (part of path) or query param
            # (after the ? in the url)
            for reflect_param in self.reflect_method.reflect_query_params():
                parameter = self.create_instance("parameter_class")
                parameter.set_param(reflect_param)
                parameters.append(parameter)

            return parameters

    def get_tags_value(self, **kwargs):
        tags = list(self.reflect_method.reflect_class().value["module_keys"])
        if not tags and self.root:
            for tag in self.root.get("tags", []):
                if tag.reflect_module is None:
                    tags.append(tag["name"])
                    break

        return tags

    def get_operation_id_value(self, **kwargs):
        """Return the globally unique operation id for this operation

        operationId is an optional unique string used to identify the
        operation. The operation id must be unique among all operations
        in the API

        The operation id is in the lower camelcase form:

            <HTTP-VERB><PATH>

        Any extension will also be camelcase, so `GET /foo.bar` would become
        `getFooBar`

        :returns: str, the globally unique operation id
        """
        parts = []
        rc = self.reflect_method.reflect_class()
        parts.append(self.reflect_method.http_verb.lower())
        for k in rc.value["module_keys"]:
            parts.append(NamingConvention(k).upper_camelcase())

        for k in rc.value["class_keys"]:
            parts.append(NamingConvention(k).upper_camelcase())

        # sometimes the http verb method has a suffix, this adds that suffix
        # to make sure the op ids are globally unique
        suffix = self.reflect_method.name.split("_", maxsplit=1)
        if len(suffix) > 1:
            parts.append(NamingConvention(suffix[1]).upper_camelcase())

        return "".join(parts)

    def get_request_body_value(self, **kwargs):
        if self.reflect_method.has_body():
            rb = self.create_instance(
                "request_body_class",
                **kwargs
            )
            rb.set_method(self.reflect_method)
            return rb

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

    def get_responses_success_value(self):
        """Generates a dict of success status codes and response objects

        This is where all the success responses are populated so custom
        implementations should override this method

        :returns: dict[str, Response]
        """
        responses = {}
        code = "200"

        if rt := self.reflect_method.reflect_return_type():
            if rt.is_none():
                code = "204"

        elif not list(self.reflect_method.reflect_ast_returns()):
            code = "204"

        response = self.create_response_instance(code)
        responses[response.code] = self.create_response_instance(code)
        return responses

    def get_responses_error_value(self):
        """Generates a dict of error status codes and response objects

        This is where all the error responses are populated so custom
        implementations should override this method for error handling

        :returns: dict[str, Response]
        """
        responses = {}

        def append(responses, response):
            if response.code in responses:
                responses[response.code].merge(response)

            else:
                responses[response.code] = response

        for rx in self.reflect_method.reflect_ast_raises():
            if rx.name == "CallError" or rx.name == "CallStop":
                errargs, errkwargs = rx.get_parameters()
                res_kwargs = {}

                if len(errargs) > 1:
                    res_kwargs["code"] = errargs[0]
                    if errargs[1]:
                        res_kwargs["description"] = errargs[1]

                    else:
                        res_kwargs["description"] = (
                            "Call error with unparsed description"
                        )

                elif len(errargs) > 0:
                    res_kwargs["code"] = errargs[0]
                    res_kwargs["description"] = "Call error raised"

                else:
                    res_kwargs["code"] = 500
                    res_kwargs["description"] = (
                        "Call error raised with unknown code"
                    )

                response = self.create_response_instance(**res_kwargs)
                append(responses, response)

            elif rx.name == "ValueError":
                response = self.create_response_instance(
                    "400",
                    description="Missing value"
                )
                append(responses, response)

        for rp in self.reflect_method.reflect_params():
            if rp.is_required():
                response = self.create_response_instance(
                    "400",
                    description="Invalid params"
                )
                append(responses, response)
                break

        for rd in self.reflect_method.reflect_ast_decorators():
            if rd.name.startswith("auth"):
                response = self.create_response_instance(
                    "401",
                    description="Unauthorized request"
                )
                append(responses, response)
                break

        response = self.create_response_instance(
            "500",
            description="Unidentified server error"
        )
        append(responses, response)

        return responses

    def get_responses_value(self, **kwargs):
        responses = self.get_responses_success_value()
        responses.update(self.get_responses_error_value())
        return responses

    def create_response_instance(self, code, **kwargs):
        return self.create_instance(
            "response_class",
            code,
            self.reflect_method,
            **kwargs
        )


class PathItem(OpenABC):
    """Represents an OpenAPI path item object

    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#path-item-object

    This has a little bit different lifecycle than other OpenABC children,
    when `.add_method` is called then this will try and call:
    `.set_<HTTP-VERB>_operation` with the created operation instance, if it
    doesn't exist then it will just call `.set_operation`. This allows child
    classes to customize the output on a per operation basis

    .. Example:
        # customize put
        class CustomPathItem(PathItem):
            def set_put_operation(self, operation):
                # custom stuff
    """
    _ref = Field(str, name="$ref")
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.1.md#reference-object
    """

    _summary = Field(str)

    _description = Field(str)

    _parameters = Field(list[Parameter|Reference], todict_empty_value=None)

    _get = Field(Operation)

    _put = Field(Operation)

    _post = Field(Operation)

    _delete = Field(Operation)

    _options = Field(Operation)

    _head = Field(Operation)

    _patch = Field(Operation)

    _trace = Field(Operation)

    _servers = Field(list[Server])

    def add_method(self, reflect_method, **kwargs):
        """Add the method to this path

        This is the external method called by OpenAPI when populating the
        `paths` key

        :param reflect_method: ReflectMethod
        """
        m = self.get_set_http_verb_method(reflect_method)
        m(reflect_method)
        self.add_parameters(reflect_method)

        if "description" not in self:
            self.set_docblock(reflect_method.reflect_class().get_docblock())

    def add_parameters(self, reflect_method):
        parameters = self.get("parameters", [])

        # this is a positional argument (part of path) or query param
        # (after the ? in the url)
        for reflect_param in reflect_method.reflect_path_params():
            parameter = self.create_instance("parameter_class")
            parameter.set_param(reflect_param)
            parameters.append(parameter)

        self["parameters"] = parameters

    def get_set_http_verb_method(self, reflect_method):
        """Get the set operation for this method

        This will try and find a valid .set_<HTTP_VERB>_operation method and
        fallback to .set_http_verb_operation

        :param reflect_method: ReflectMethod
        :returns: Callable[[ReflectMethod], None]
        """
        method_name = f"set_{reflect_method.http_verb.lower()}_operation"
        return getattr(self, method_name, self.set_http_verb_operation)

    def set_http_verb_operation(self, reflect_method):
        """internal method. Used by .add_method as a fallback if .add_method
        doesn't call a more specific .set_<HTTP_VERB>_method"""
        operation = self.create_operation_instance(reflect_method)
        self.set_operation(reflect_method.http_verb, operation)

    def set_operation(self, http_verb, operation):
        """Internal method. This sets operation into http_verb keys and does
        error checking around that. It's just here to make child class's
        lives a bit easier

        :param http_verb: str, the http verb for operation
        :param operation: Operation
        """
        http_verb = http_verb.lower()
        if http_verb in self:
            raise ValueError(
                f"PathItem has multiple {http_verb} operations"
            )

        else:
            self[http_verb] = operation

    def set_options_operation(self, reflect_method):
        """Customize options to get rid of the 405 error if CORS support is
        enabled"""
        operation = self.create_operation_instance(reflect_method)

        if reflect_method.reflect_class().get_target().cors:
            # 405 is raised when OPTION isn't supported but cors support is
            # turned on for this controller
            operation["responses"].pop("405", None)
            self.set_operation(reflect_method.http_verb, operation)

    def set_any_operation(self, reflect_method, **kwargs):
        """Controllers support an ANY catch-all http verb method, this doesn't
        work for things like OpenAPI so this converts ANY to GET and POST
        """
        http_verbs = kwargs.get("http_verbs", ["GET", "POST"])

        for http_verb in http_verbs:
            verb_rmethod = reflect_method.create_reflect_http_method_instance(
                http_verb
            )

            operation = self.create_operation_instance(
                verb_rmethod,
            )
            self.set_operation(http_verb, operation)

    def create_operation_instance(self, reflect_method, **kwargs):
        return self.create_instance(
            "operation_class",
            reflect_method,
            **kwargs
        )


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
        schemes = {}
        class_key = "security_scheme_class"

        scheme = self.create_instance(class_key, **kwargs)
        scheme["type"] = "http"
        scheme["scheme"] = "basic"
        schemes["auth_basic"] = scheme

        scheme = self.create_instance(class_key, **kwargs)
        scheme["type"] = "http"
        scheme["scheme"] = "bearer"
        schemes["auth_bearer"] = scheme

        return schemes

    def add_schema(self, name, schema):
        """Add schema intp the `schemas` key under `name` and return a schema
        with a ref to the added schema. If the schema at `name` already exists
        then this will return a ref to that schema"""
        schemas = self.get("schemas", {})

        if name not in schemas:
            schemas[name] = schema

        self["schemas"] = schemas

        return self.create_ref_schema_instance(name)

    def create_ref_schema_instance(self, name_or_ref):
        """Create a reference schema object

        https://datatracker.ietf.org/doc/html/draft-pbryan-zyp-json-ref-03#section-3
            Any members other than "$ref" in a JSON Reference object SHALL be
            ignored.

        :param name_or_ref: str, either the name (eg, "foo") or the full 
            reference path (eg, "#/components/schema/foo")
        :returns: Schema, a reference schema
        """
        rs = self.create_schema_instance()
        rs["$ref"] = self.get_schema_ref(name_or_ref)
        return rs

    def get_schema(self, name_or_ref):
        """Returns the full schema matching name

        :param name_or_ref: str, can either be name (eg, "foo") or the ref
            (eg "#/components/schemas/foo")
        :returns: Schema|None
        """
        schemas = self.get("schemas", {})
        name_or_ref = self.get_schema_name(name_or_ref)
        return schemas[name_or_ref] if name_or_ref in schemas else None

    def get_schema_ref(self, name_or_ref):
        """Get the schema ref/path for the given name"""
        if not name_or_ref.startswith("#"):
            name_or_ref = f"#/components/schemas/{name_or_ref}"

        return name_or_ref

    def get_schema_name(self, name_or_ref):
        """Get the schema name for the given ref"""
        if name_or_ref.startswith("#"):
            name_or_ref = name_or_ref.rsplit("/", 1)[-1]

        return name_or_ref


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

        # There are multiple endpoints Application classes and we don't want to
        # use those docblocks, so we will only do it if the Application is from
        # a non-endpoints project. This is the best way I've thought of to
        # test for non-endpoints-ness
        if "endpoints" not in application.__class__.__module__:
            rc = ReflectClass(application)
            self.set_docblock(rc.get_docblock())

            if version := rc.get("version", ""):
                self["version"] = version

            if summary := self.get("summary", ""):
                self["title"] = summary


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

    _jsonSchemaDialect = Field(str, default=Schema.DIALECT)

    _info = Field(Info, required=True)

    _tags = Field(list[Tag])

    _servers = Field(list[Server])

    _components = Field(Components)
    """This needs to come before paths because paths can depend on this
    existing if a path is setting/getting common schemas, etc"""

    _paths = Field(dict[str, PathItem])
    """
    https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object
    """

    _security = Field(list[SecurityRequirement])

    _externalDocs = Field(ExternalDocumentation)

    def __init__(self, application, **kwargs):
        """
        NOTE -- this has to override __init__ because it takes the application
        as the first argument, something none of the other OpenABC children
        do

        :param application: Application, the application to build an OpenAPI
            document for
        """
        self.application = application
        super().__init__(None, **kwargs)

    def get_yaml_kwargs(self, **kwargs):
        """Internal method. This returns the arguments to be passed to the
        yaml dumper, the reason this is a separate method is in order to get
        lists indented a custom Dumper class needs to be used. I have no
        idea why the default is the way it is (the yaml spec says the dash
        should be considered as part of the indentation?), see:

            * https://web.archive.org/web/20170903201521/https://pyyaml.org/ticket/64#comment:5
            * https://stackoverflow.com/a/39681672
            * The spec: https://yaml.org/spec/1.2-old/spec.html#id2777534
            * https://github.com/yaml/pyyaml/issues/234#issuecomment-498026245

        """
        if not yaml:
            raise ValueError("Missing yaml dependency")

        class IndentListDumper(yaml.Dumper):
            def increase_indent(self, flow=False, indentless=False):
                return super().increase_indent(flow, False)

        # The documentation isn't very useful but here it is
        # https://pyyaml.org/wiki/PyYAMLDocumentation
        return {
            **dict(
                Dumper=IndentListDumper,
                sort_keys=False,
                default_flow_style=False,
            ),
            **kwargs
        }

    def get_yaml(self):
        """Return this OpenAPI document as a yaml string"""
        return yaml.dump(
            self.todict(),
            **self.get_yaml_kwargs(),
        )

    def write_yaml(self, directory):
        """Writes openapi.yaml file to directory

        Depends on `pyyaml` dependency to be installed

            https://pyyaml.org/

        :param directory: str, the directory path
        :returns: str, the path to the openapi.json file
        """
        kwargs = self.get_yaml_kwargs()
        dp = Dirpath(directory)
        fp = dp.get_file("openapi.yaml")

        with fp.open("w+") as stream:
            data = yaml.dump(
                self.todict(),
                stream,
                **kwargs
            )
            logger.debug(f"YAML written to: {fp}")

        return fp

    def get_json(self):
        """Return this OpenAPI document as a json string"""
        return json.dumps(self, cls=JSONEncoder)

    def write_json(self, directory):
        """Writes openapi.json file to directory

        :param directory: str, the directory path
        :returns: str, the path to the openapi.json file
        """
        dp = Dirpath(directory)
        fp = dp.get_file("openapi.json")

        # Specific json settings to make it easier to read and edit manually
        # https://docs.python.org/3/library/json.html#encoders-and-decoders
        class OpenEncoder(JSONEncoder):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                self.item_separator = ": "
                self.indent = 2
                self.sort_keys = False

        with fp.open("w+") as stream:
            json.dump(self, stream, cls=OpenEncoder)
            logger.debug(f"JSON written to: {fp}")

        return fp

    def get_html(self, **kwargs):
        """Generate the api as html

        This generates Swagger UI docs, you should be able to absolutely
        load this html into a browser and it should load the api docs

        HTML comes from here:
            https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/#unpkg

        :keyword cdn_base_url: Optional[str], should probably never be messed
            with
        :keyword swagger_version: Optional[str]
        :keyword title: Optional[str], the api title, defaults to
            OpenAPI.info.title
        :keyword description: Optional[str], the api description, defaults to
            OpenAPI.info.title
        :keyword url: Optional[str], if this is passed in then it will be
            used to fetch the openapi.yaml or openapi.json file and spec will
            be ignored
        :keyword spec: Optional[str], this defaults to `.get_json` and
            should almost never be messed with
        :returns: str, the html to render Swagger UI docs
        """
        # I got the CSS to get rid of OPTIONS here:
        # https://github.com/swagger-api/swagger-ui/issues/2819

        # SwaggerUIBundle configuration:
        # https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/

        # This is just a simple template
        # https://docs.python.org/3/library/string.html#string.Template

        kwargs.setdefault("cdn_base_url", "https://unpkg.com/swagger-ui-dist")

        # https://github.com/swagger-api/swagger-ui/releases/latest
        kwargs.setdefault("swagger_version", "5.17.14")

        kwargs.setdefault("title", self["info"]["title"])
        kwargs.setdefault("description", self["info"]["description"])

        if "url" in kwargs:
            kwargs["spec"] = "{}"

        else:
            kwargs.setdefault("url", "")
            if "spec" not in kwargs:
                kwargs["spec"] = self.get_json()

        return Template("""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <meta name="description" content="$description" />
                <title>$title</title>
                <link rel="stylesheet" href="$cdn_base_url@$swagger_version/swagger-ui.css" />
                <style>
                    /* get rid of the header */
                    .swagger-ui .topbar { display: none; }
                    /* get rid of OPTIONS requests */
                    .opblock-options { display: none; }
                </style>
            </head>
            <body>
                <div id="swagger-ui"></div>
                <script src="$cdn_base_url@$swagger_version/swagger-ui-bundle.js" crossorigin></script>
                <script>
                    window.onload = function() {
                        configuration = {
                            dom_id: "#swagger-ui",
                            docExpansion: "list",
                        }

                        url = "$url"
                        if (url) {
                            configuration["url"] = url

                        } else {
                            configuration["spec"] = $spec
                        }
                        window.ui = SwaggerUIBundle(configuration)

                        /* window.ui = SwaggerUIBundle({
                            url: "$url",
                            spec: $spec,
                            dom_id: "#swagger-ui",
                            docExpansion: "list",
                        }) */
                    }
                </script>
            </body>
            </html>
        """).substitute(
            **kwargs
        )

    def get_info_value(self, **kwargs):
        return self.create_instance("info_class", self.application, **kwargs)

    def get_paths_value(self, **kwargs):
        """Represents a Pseudo OpenApi paths object

        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#paths-object

        The keys are the path (starting with /) and the value is a PathItem
        instance

        :returns: dict[str, PathItem]
        """
        paths = {}
        for reflect_controller in self.reflect_controllers():
            logger.debug(
                f"Adding Controller: {reflect_controller.classpath}"
            )

            url_paths = reflect_controller.reflect_url_paths()
            for url_path, reflect_methods in url_paths.items(): 
                if url_path not in paths:
                    logger.debug(f"Creating {url_path} path item")
                    paths[url_path] = self.create_instance(
                        "path_item_class",
                        **kwargs
                    )

                for reflect_method in reflect_methods:
                    logger.debug(
                        f"Adding {reflect_method.http_verb} {url_path}"
                    )
                    paths[url_path].add_method(reflect_method, **kwargs)

        return paths

    def get_tags_value(self, **kwargs):
        tags = []
        seen = set()
        for reflect_controller in self.reflect_controllers():
            for reflect_module in reflect_controller.reflect_url_modules():
                mk = reflect_module.module_key
                if mk not in seen:
                    logger.debug(f"Adding tag: \"{mk}\"")
                    tags.append(self.create_instance(
                        "tag_class",
                        reflect_module,
                        **kwargs
                    ))

                    seen.add(mk)

        # instead of using Swagger's "Default" key for everything that doesn't
        # have a tag, operations without a tag will go into root
        tags.append(self.create_instance(
            "tag_class",
            None,
            name=kwargs.get("default_tag_name", "root"),
            description=""
        ))

        return tags

    def get_components_value(self, **kwargs):
        return self.create_instance("components_class", **kwargs)

    def reflect_controllers(self):
        """Reflect all the controllers of this application"""
        pathfinder = self.application.router.pathfinder
        for keys, value in pathfinder.get_class_items():
            reflect_controller = self.create_reflect_controller_instance(
                keys,
                value
            )

            yield reflect_controller

    def create_reflect_controller_instance(self, keys, value, **kwargs):
        return kwargs.get("reflect_controller_class", ReflectController)(
            keys,
            value
        )

