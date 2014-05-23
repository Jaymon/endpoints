
class BaseServer(object):
    """all servers should extend this and implemented the NotImplemented methods,
    this ensures a similar interface among all the different servers"""

    interface_class = None
    """the interface that should be used to translate between the supported server"""

    server_class = None
    """the supported server's interface"""

    def __init__(self, interface_class=None, server_class=None, *args, **kwargs):

        if interface_class:
            self.interface_class = interface_class

        if server_class:
            self.server_class = server_class

        self.interface = self.create_interface(*args, **kwargs)
        self.server = self.create_server(*args, **kwargs)

    def create_interface(self, *args, **kwargs):
        return self.interface_class(*args, **kwargs)

    def create_server(self, *args, **kwargs):
        return self.server_class(*args, **kwargs)

    def handle_request(self):
        raise NotImplemented()

    def serve_forever(self):
        while True: self.handle_request()

    def serve_count(self, count):
        handle_count = 0
        while handle_count < count:
            self.handle_request()
            handle_count += 1

