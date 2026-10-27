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
