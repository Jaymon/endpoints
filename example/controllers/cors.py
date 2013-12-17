from endpoints import Controller, CorsMixin

class Default(Controller, CorsMixin):
    """This will work to test preflighted cors requests from javascript"""
    def GET(self, *args, **kwargs):
        return "GET /cors -> {}.cors.Default.GET".format(self.call.controller_prefix)

    def POST(self, *args, **kwargs):
        return "Yay! Cors request worked"


