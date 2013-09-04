from endpoints import Controller

class Default(Controller):
    def GET(self, *args, **kwargs):
        return "GET /foo -> {}.foo.Default.GET".format(self.call.controller_prefix)

