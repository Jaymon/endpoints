from endpoints import Controller


class Default(Controller):
    """This will work to test preflighted cors requests from javascript"""
    def GET(self, *args, **kwargs) -> str:
        mon = self.request.controller_info["module_name"]
        cln = self.request.controller_info["class_name"]
        men = self.request.controller_info["http_method_name"]
        return "GET /cors -> {}:{}.{}\n".format(mon, cln, men)

    def POST(self, *args, **kwargs) -> str:
        return "Cors request worked!\n"

