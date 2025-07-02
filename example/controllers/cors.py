from endpoints import Controller


class Default(Controller):
    """This will work to test preflighted cors requests from javascript"""
    def GET(self, *args, **kwargs) -> str:
        rm = self.request.controller_info["reflect_method"]
        return f"GET /cors -> {rm.callpath}\n"

    def POST(self, *args, **kwargs) -> str:
        return "Cors request worked!\n"

