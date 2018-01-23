from endpoints.decorators.auth import AuthDecorator
from endpoints import Controller


def get_user(request):
    class User(object):
        def __init__(self, *perms):
            self.perms = perms

    mapping = {
        ("alice", "1234"): User("bar"),
        ("bob", "1234"): User("che")
    }

    return mapping[request.get_auth_basic()]


class PermAuth(AuthDecorator):

    def decorate(self, func, *perms):
        self.perms = perms
        return super(PermAuth, self).decorate(func)

    def normalize_target_params(self, request, controller_args, controller_kwargs):
        user = get_user(request)
        return [], {
            'user_perms': set(user.perms),
            'valid_perms': set(self.perms),
        }

    def target(self, user_perms, valid_perms):
        return len(user_perms.intersection(valid_perms)) > 0


class Default(Controller):
    @PermAuth("bar", "che") # bar and che can access GET
    def GET(self):
        return "user can GET"

    @PermAuth("bar") # you must have bar perms to POST
    def POST(self, **kwargs):
        return "user can POST"

