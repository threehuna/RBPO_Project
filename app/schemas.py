from pydantic import BaseModel, ConfigDict, Field


class CatalogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2**63 - 1)


class PublicMaterial(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
