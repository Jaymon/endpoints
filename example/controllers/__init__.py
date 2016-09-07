
from endpoints import Controller

class Default(Controller):
    def GET(self, *args, **kwargs):
        return "GET / -> {}.Default.GET\n".format(self.call.controller_prefix)

