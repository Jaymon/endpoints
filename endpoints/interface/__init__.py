# -*- coding: utf-8 -*-

# from .asgi import Application as ASGIApplication
# from .wsgi import Application as WSGIApplication
# 
# 
# class Application(object):
# 
# 	asgi_class = ASGIApplication
# 
# 	wsgi_class = WSGIApplication
# 
#     def __init__(self, controller_prefixes=None, **kwargs):
#         if controller_prefixes:
#             if isinstance(controller_prefixes, str):
#                 controller_prefixes = environ.split_value(controller_prefixes)
# 
#             self.controller_prefixes = controller_prefixes
# 
#         else:
#             if "controller_prefix" in kwargs:
#                 self.controller_prefixes = [kwargs["controller_prefix"]]
# 
#             else:
#                 self.controller_prefixes = environ.get_controller_prefixes()
# 
#         for k, v in kwargs.items():
#             if k.endswith("_class"):
#                 setattr(self, k, v)
#     def test_wsgi_headers(self):
#         """make sure request url gets controller_path correctly"""
#         server = self.create_server(contents=[
#             "class Default(Controller):",
#             "    def GET(self):",
#             "        return 1",
#             "",
#         ])
# 
#         c = self.create_client()
#         r = c.get("/")
#         pout.v(r.body)
# 
#         # 'GATEWAY_INTERFACE': str (7)
#         # 28040: ܁   ܁   ܁   "
#         # 28040: ܁   ܁   ܁   ܁   CGI/1.1
#         # 28040: ܁   ܁   'SERVER_SOFTWARE': str (14)
#         # 28040: ܁   ܁   ܁   "
#         # 28040: ܁   ܁   ܁   ܁   WSGIServer/0.2
#         # 28128: ܁   ܁   'wsgi.version': tuple (2)
#         # 28128: ܁   ܁   ܁   (
#         # 28128: ܁   ܁   ܁   ܁   0: 1,
#         # 28128: ܁   ܁   ܁   ܁   1: 0
#         # 28128: ܁   ܁   ܁   ),
