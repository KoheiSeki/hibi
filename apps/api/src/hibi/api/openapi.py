from typing import Any

from fastapi import FastAPI

from hibi.api.problem_details import ProblemDetails

_DESCRIPTIONS = {
    400: "Bad request.",
    401: "Authentication failed.",
    404: "The requested resource was not found.",
    409: "Conflict.",
    422: "Request validation failed.",
    500: "An unexpected server error occurred.",
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {
        status: {
            "description": _DESCRIPTIONS[status],
            "model": ProblemDetails,
        }
        for status in statuses
    }


class ProblemDetailsFastAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        schema = super().openapi()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for status, response in operation.get("responses", {}).items():
                    if int(status) < 400:
                        continue
                    content = response.get("content", {})
                    json_schema = content.get("application/json")
                    if json_schema == {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}:
                        response["content"] = {"application/problem+json": json_schema}
        return schema
