# -*- coding: utf-8 -*-

from datatypes.config import (
    Environ,
)


class Environ(Environ):
    def __init__(self, *args, **kwargs):
        super().__init__(namespace="ENDPOINTS_", **kwargs)

        # Default encoding
        self.setdefault("ENCODING", "UTF-8")

        # the response content type a controller will set
        self.setdefault("RESPONSE_CONTENT_TYPE", "application/json")

        # The host string, usually just domain or domain:port, this is used by
        # the server classes and also the tests
        self.setdefault("HOST", "")

        # this scheme will be used if scheme can't be inferred
        self.setdefault("SCHEME", "http")

        # the name of the autodiscover module name
        self.setdefault("AUTODISCOVER_NAME", "controllers")

    def set_host(self, host):
        self.set("HOST", host)

    def set_controller_prefixes(self, prefixes, env_name='ENDPOINTS_PREFIX'):
        """set the controller_prefixes found in env_name to prefixes, this will
        remove any existing found controller prefixes 

        :param prefixes: list, the new prefixes that will replace any old
            prefixes
        :param env_name: string, the name of the environment variables
        """
        self.nset(env_name, prefixes)

    def get_prefix_names(self, env_name):
        """This returns the actual environment variable names from * -> *_N

        :param env_name: string, the name of the environment variables
        :returns: generator, the found environment names
        """
        for k in self.nkeys(env_name):
            yield k

    def get_controller_prefixes(self, env_name='ENDPOINTS_PREFIX'):
        """this will look for ENDPOINTS_PREFIX, and ENDPOINTS_PREFIX_N (where
        N is 1 to infinity) in the environment, if it finds them, it will
        assume they are python module paths where endpoints can find Controller
        subclasses

        The num checks (eg ENDPOINTS_PREFIX_1, ENDPOINTS_PREFIX_2) go in order,
        so you can't do ENDPOINTS_PREFIX_1, ENDPOINTS_PREFIX_3, because it will
        fail on _2 and move on, so make sure your num dsns are in order (eg, 1,
        2, 3, ...)

        :Example:
            export ENDPOINTS_PREFIX_1=foo.controllers
            export ENDPOINTS_PREFIX_2=bar.che
            $ python
            >>> from endpoints import environ
            >>> environ.get_controller_prefixes
            ['foo.controller', 'bar.che']

        :param env_name: string, the name of the environment variables
        :returns: list, the found module paths
        """
        return list(self.paths(env_name))


environ = Environ()

