from endpoints import Controller


class Default(Controller):
    def GET(self, *args, **kwargs) -> str:
        mon = self.request.controller_info["module_name"]
        cln = self.request.controller_info["class_name"]
        men = self.request.controller_info["http_method_name"]
        return "GET / -> {}:{}.{}\n".format(mon, cln, men)

