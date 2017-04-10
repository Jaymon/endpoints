from endpoints import Controller

class Default(Controller):
    """This will work to test preflighted cors requests from javascript"""
    def GET(self, *args, **kwargs):
        return "GET /cors -> {}.cors.Default.GET\n".format(self.call.controller_prefix)

    def POST(self, *args, **kwargs):
        return "Yay! Cors request worked\n"


