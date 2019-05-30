# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os


def get(key, default=None, namespace="ENDPOINTS_"):
    if namespace and not key.startswith(namespace):
        key = namespace + key

    r = os.environ.get(key, default)
    return r


ENCODING = get("ENCODING", "UTF-8")
"""Default encoding"""

HOST = get("HOST", "localhost:8383")
"""The host string, usually just domain or domain:port, this is used by the server
classes and also the tests"""


def get_prefixes(env_name):
    """this will look for env_name, and env_name_N (where
    N is 1 to infinity) in the environment, if it finds them, it will assume they
    are python module paths

    The num checks (eg *_1, *_2) go in order, so you can't do *_1, *_3, because it
    will fail on missing *_2 and move on, so make sure your num dsns are in order 
    (eg, 1, 2, 3, ...)

    :param env_name: string, the name of the environment variables
    :returns: list, the found module paths
    """
    ret = []
    prefixsep = os.pathsep

    if env_name in os.environ:
        ret.extend(os.environ[env_name].split(prefixsep))
        #ret.append(os.environ[env_name])

    # now try importing _1 -> _N prefixes
    increment_name = lambda name, num: '{name}_{num}'.format(name=name, num=num)
    num = 0 if increment_name(env_name, 0) in os.environ else 1
    env_num_name = increment_name(env_name, num)
    while env_num_name in os.environ:
        #ret.append(os.environ[env_num_name])
        ret.extend(os.environ[env_num_name].split(prefixsep))
        num += 1
        env_num_name = increment_name(env_name, num)

    return ret


def get_controller_prefixes(env_name='ENDPOINTS_PREFIX'):
    """this will look for ENDPOINTS_PREFIX, and ENDPOINTS_PREFIX_N (where
    N is 1 to infinity) in the environment, if it finds them, it will assume they
    are python module paths where endpoints can find Controller subclasses

    The num checks (eg ENDPOINTS_PREFIX_1, ENDPOINTS_PREFIX_2) go in order, so you
    can't do ENDPOINTS_PREFIX_1, ENDPOINTS_PREFIX_3, because it will fail on _2
    and move on, so make sure your num dsns are in order (eg, 1, 2, 3, ...)

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
    return get_prefixes(env_name)

