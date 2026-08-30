class IngestionError(Exception):
    status_code = 400
    code = "INGESTION_ERROR"


class AuthenticationError(IngestionError):
    status_code = 401
    code = "INGESTION_AUTHENTICATION_FAILED"


class UnsupportedSchemaError(IngestionError):
    status_code = 422
    code = "UNSUPPORTED_SCHEMA_VERSION"


class PayloadValidationError(IngestionError):
    status_code = 422
    code = "INVALID_CANONICAL_PACKAGE"


class ImmutableConflictError(IngestionError):
    status_code = 409
    code = "IMMUTABLE_PACKAGE_CONFLICT"


class RateLimitError(IngestionError):
    status_code = 429
    code = "INGESTION_RATE_LIMITED"


class RateLimitUnavailableError(IngestionError):
    status_code = 503
    code = "INGESTION_RATE_LIMIT_UNAVAILABLE"
