from collections.abc import Callable
from uuid import UUID

from hibi.auth.principal import Principal

ResourceLookup = Callable[[UUID], str]


def get_owned_resource(*, principal: Principal, repository_lookup: ResourceLookup) -> str:
    """Load a resource through an owner-scoped repository contract."""
    return repository_lookup(principal.user_id)
