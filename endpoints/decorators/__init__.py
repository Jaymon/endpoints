# -*- coding: utf-8 -*-

from .auth import (
    AuthBackend,
    AuthDecorator,
    auth_basic,
    auth_client,
    auth_token,
)

from .limit import (
    RateLimitBackend,
    RateLimitDecorator,
    ratelimit_ip,
    ratelimit_access_token,
    ratelimit_param,
    ratelimit_param_ip,
)

from .base import (
    TargetDecorator,
    BackendDecorator,
    ControllerDecorator,
)

from .call import (
    route,
    route_path,
    route_param,
    version
)

from .utils import (
    httpcache,
    nohttpcache,
    code_error,
    param,
    param_query,
    param_body,
)

