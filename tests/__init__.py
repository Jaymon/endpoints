from unittest import TestCase as BaseTestCase, skipIf, SkipTest
import os
import sys
import logging


os.environ.setdefault("ENDPOINTS_HOST", "localhost:8080")


#logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
log_handler = logging.StreamHandler(stream=sys.stderr)
log_formatter = logging.Formatter('[%(levelname)s] %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)


class TestCase(BaseTestCase):
    def get_host(self):
        return os.environ.get("ENDPOINTS_HOST")

