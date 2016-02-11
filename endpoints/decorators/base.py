from __future__ import absolute_import
import logging

from decorators import FuncDecorator

from ..exception import CallError


logger = logging.getLogger(__name__)


class TargetDecorator(FuncDecorator):
    def normalize_target_params(self, request, controller_args, controller_kwargs):
        return [], dict(
            request=request,
            controller_args=controller_args, 
            controller_kwargs=controller_kwargs
        )

    def handle_error(self, e):
        raise e

    def handle_target(self, request, controller_args, controller_kwargs):
        try:
            param_args, param_kwargs = self.normalize_target_params(
                request=request,
                controller_args=controller_args,
                controller_kwargs=controller_kwargs
            )
            ret = self.target(*param_args, **param_kwargs)
            if not ret:
                raise ValueError("{} check failed".format(self.__class__.__name__))

        except CallError:
            raise

        except (AttributeError, TypeError) as e:
            logger.debug(e, exc_info=True)
            raise NotImplementedError(e.message)

        except Exception as e:
            logger.debug(e, exc_info=True)
            self.handle_error(e)

    def decorate(self, func, target, *anoop, **kwnoop):
        if target:
            self.target = target

        def decorated(decorated_self, *args, **kwargs):
            self.handle_target(
                request=decorated_self.request,
                controller_args=args,
                controller_kwargs=kwargs
            )
            return func(decorated_self, *args, **kwargs)

        return decorated

