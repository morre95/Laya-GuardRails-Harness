from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Canonical frozen schema type. Extra fields are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
