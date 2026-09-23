class ApplicationError(Exception):
    problem_type = "internal-error"
    title = "Internal server error"
    status = 500
    detail = "An unexpected error occurred."


class AuthenticationError(ApplicationError):
    problem_type = "unauthorized"
    title = "Unauthorized"
    status = 401
    detail = "Authentication is required."
