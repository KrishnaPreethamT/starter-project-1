from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1)


class ExtractedItem(BaseModel):
    product_name: str | None = None
    quantity: str | int | None = None


class ExtractedOrder(BaseModel):
    customer: str | None = None
    delivery_city: str | None = None
    deadline: str | None = None
    items: list[ExtractedItem] = Field(default_factory=list)


class OrderItemResult(BaseModel):
    product_name: str | None
    product_code: str | None
    requested: int | None
    available: int | None


class OrderResult(BaseModel):
    customer: str | None
    delivery_city: str | None
    deadline: str | None
    items: list[OrderItemResult]
    status: Literal["Ready", "Partial", "Need info"]
    issues: list[str]
    reply: str
