from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import os
import sys
import socket
import logging

#logging.basicConfig()
# configure root logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_handler = logging.StreamHandler(stream=sys.stderr)
log_formatter = logging.Formatter('[%(levelname)s] %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)
logger = logging.getLogger("example")


#sys.path.append(os.path.join("..", "endpoints"))
sys.path.append("..")
sys.path.append(os.path.join("..", ".."))


from endpoints import Call, Request, Response

class SimpleHandler(BaseHTTPRequestHandler):

    def handle_one_request(self):
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if not self.raw_requestline:
                self.close_connection = 1
                return

            if not self.parse_request():
                # An error code has been sent, just exit
                return

            if '?' in self.path:
                path, query = self.path.split('?', 1)
            else:
                path = self.path
                query = ""

            req = Request()
            req.path = path
            req.query = query
            req.method = self.command
            req.headers = self.headers.dict

            c = Call("controllers")
            c.request = req
            c.response = Response()
            res = c.handle()

            self.send_response(res.code)
            for h, hv in res.headers.iteritems():
                self.send_header(h, hv)

            self.send_header('Connection', 'close')
            self.end_headers()

            body = res.body
            if body:
                self.wfile.write(res.body)
                self.wfile.flush()

        except socket.timeout, e:
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return

if __name__ == "__main__":

    port = 8000
    logger.info("Listening on port {}".format(port))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHandler)
    httpd.serve_forever()
    #httpd.handle_request()

