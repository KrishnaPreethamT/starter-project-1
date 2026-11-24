from typing import Literal
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1)


class ExtractedItem(BaseModel):
    product_name: str | None = None
    quantity: str | int | None = None
    is_description: bool = False
    product_code: str | None = None
    resolution_candidates: list[str] = Field(default_factory=list)


class ExtractedOrder(BaseModel):
    customer: str | None = None
    delivery_city: str | None = None
    deadline: str | None = None
    items: list[ExtractedItem] = Field(default_factory=list)
    repeat_order: bool = False


class OrderItemResult(BaseModel):
    product_name: str | None
    product_code: str | None
    requested: int | None
    available: int | None


class QuoteLine(BaseModel):
    product_code: str
    quantity: int
    unit_price_inr: Decimal
    discount_percent: int
    line_total_inr: Decimal


class Quote(BaseModel):
    lines: list[QuoteLine]
    subtotal_inr: Decimal
    delivery_inr: Decimal
    total_inr: Decimal
    valid_until: str


class ProductResolution(BaseModel):
    product_code: str | None = None
    ambiguous: bool = False
    matching_product_codes: list[str] = Field(default_factory=list)


class OrderResult(BaseModel):
    customer: str | None
    delivery_city: str | None
    deadline: str | None
    items: list[OrderItemResult]
    status: Literal["Ready", "Partial", "Need info"]
    issues: list[str]
    reply: str
    quote: Quote | None = None
