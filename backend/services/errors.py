class ServiceError(Exception):
    """Base class for errors the API translates into HTTP responses."""


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


class InvalidStateError(ServiceError):
    pass


class BadRequestError(ServiceError):
    pass


class LimitReachedError(ServiceError):
    """A usage cap (e.g. chat turns per report) was hit. 429."""


class UpstreamBusyError(ServiceError):
    """The model provider is overloaded or out of quota; try again shortly. 503."""
