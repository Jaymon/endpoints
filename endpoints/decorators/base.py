from __future__ import absolute_import
import logging

from decorators import FuncDecorator

from ..exception import CallError


logger = logging.getLogger(__name__)


class TargetDecorator(FuncDecorator):
    def normalize_target_params(self, request, *args, **kwargs):
        param_args = [request] + list(args)
        return param_args, kwargs

    def handle_error(self, e):
        raise e

    def handle_target(self, request, *args, **kwargs):
        try:
            param_args, param_kwargs = self.normalize_target_params(request, *args, **kwargs)
            ret = self.target(*param_args, **param_kwargs)
            if not ret:
                raise ValueError("{} check failed".format(self.__class__.__name__))

        except CallError:
            raise

        except (AttributeError, TypeError) as e:
            logger.debug(e, exc_info=True)
            raise NotImplementedError(e.message)

#         except ValueError as e:
# 
#             exc_info = sys.exc_info()
#             logger.warning(str(e), exc_info=exc_info)
# 
#             self.handle_error(e)
#             logger.debug(e, exc_info=True)
#             raise
# 
        except Exception as e:
#             exc_info = sys.exc_info()
#             logger.debug(e, exc_info=exc_info)
            logger.debug(e, exc_info=True)
            self.handle_error(e)

    def decorate(self, func, target, *anoop, **kwnoop):
        if target:
            self.target = target

        def decorated(decorated_self, *args, **kwargs):
            self.handle_target(decorated_self.request, *args, **kwargs)
            return func(decorated_self, *args, **kwargs)

        return decorated

