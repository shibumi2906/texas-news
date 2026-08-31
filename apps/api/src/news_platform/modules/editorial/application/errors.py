class EditorialError(Exception):
    status_code = 409
    code = "EDITORIAL_CONFLICT"


class ContentNotFoundError(EditorialError):
    status_code = 404
    code = "CONTENT_NOT_FOUND"


class PublicationBlockedError(EditorialError):
    code = "PUBLICATION_BLOCKED"


class EditorialValidationError(EditorialError):
    status_code = 422
    code = "EDITORIAL_VALIDATION_FAILED"
