import logging
import re
from datetime import date
from typing import Protocol

from app.config import Settings
from app.email_parser import ParsedEmail
from app.models.orders import ExtractedOrder, OrderItemResult, OrderResult
from app.repositories.products import ProductStock

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def extract_order(self, raw_email: str, email_date: str | None) -> ExtractedOrder: ...

    def draft_reply(self, customer: str | None, result: dict) -> str: ...


class ProductLookup(Protocol):
    def find_product(self, product_name: str) -> ProductStock | None: ...


def normalize_product_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def compare_stock(requested: int | None, available: int) -> bool:
    return requested is not None and requested <= available


def _valid_quantity(value: str | int | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = value.strip()
    if not re.fullmatch(r"[0-9]+", text):
        return None
    quantity = int(text)
    return quantity if quantity > 0 else None


def _clean(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    return cleaned or None


def _date_from_header(email_date: str | None) -> date | None:
    if not email_date:
        return None
    try:
        return date.fromisoformat(email_date[:10])
    except ValueError:
        return None


def build_order_result(
    extracted: ExtractedOrder,
    email_date: str | None,
    settings: Settings,
    repository: ProductLookup,
    previous_order_reference: bool = False,
) -> OrderResult:
    customer = _clean(extracted.customer)
    city = _clean(extracted.delivery_city)
    issues: list[str] = []
    if not customer:
        issues.append("Missing customer organisation name")
    if not city:
        issues.append("Missing delivery city")
    if not extracted.items:
        issues.append("No items listed")

    deadline_value: str | None = None
    if extracted.deadline:
        try:
            deadline_date = date.fromisoformat(extracted.deadline.strip())
            deadline_value = deadline_date.isoformat()
            header_date = _date_from_header(email_date)
            if header_date is None:
                issues.append("Cannot validate deadline because the email Date header is missing or invalid")
            elif (deadline_date - header_date).days < settings.lead_time_days:
                issues.append(
                    f"Deadline {deadline_value} is less than {settings.lead_time_days} days after the email date {header_date.isoformat()}"
                )
        except ValueError:
            issues.append(f"Invalid deadline: '{extracted.deadline}'")

    items: list[OrderItemResult] = []
    insufficient_stock: list[str] = []
    for extracted_item in extracted.items:
        name = _clean(extracted_item.product_name)
        requested = _valid_quantity(extracted_item.quantity)
        if not name:
            issues.append("Missing product name")
            items.append(OrderItemResult(product_name=None, product_code=None, requested=requested, available=None))
            continue
        if requested is None:
            issues.append(f"Invalid quantity for {name}: '{extracted_item.quantity}'")
        product = repository.find_product(name)
        if product is None:
            logger.info("Stock lookup: product=%s found=false", name)
            issues.append(f"Unknown product: {name}")
            items.append(OrderItemResult(product_name=name, product_code=None, requested=requested, available=None))
            continue
        logger.info(
            "Stock lookup: product=%s product_code=%s available=%d",
            name,
            product.product_code,
            product.available,
        )
        items.append(
            OrderItemResult(
                product_name=name,
                product_code=product.product_code,
                requested=requested,
                available=product.available,
            )
        )
        if requested is not None and not compare_stock(requested, product.available):
            insufficient_stock.append(f"{name}: requested {requested}, only {product.available} in stock")
    issues.extend(insufficient_stock)
    if previous_order_reference:
        issues.insert(0, "Refers to a previous order")

    need_info_prefixes = (
        "Invalid",
        "Unknown",
        "Missing",
        "No items",
        "Deadline",
        "Cannot validate",
        "Refers",
    )
    has_need_info = any(issue.startswith(need_info_prefixes) for issue in issues)
    status = "Need info" if has_need_info else "Partial" if insufficient_stock else "Ready"
    if status == "Ready":
        issues = []
    logger.info("Status decision: %s; issues=%s", status, issues)
    return OrderResult(
        customer=customer,
        delivery_city=city,
        deadline=deadline_value,
        items=items,
        status=status,
        issues=issues,
        reply="",
    )


class OrderWorkflow:
    def __init__(self, llm_client: LLMClient, repository: ProductLookup, settings: Settings):
        self.llm_client = llm_client
        self.repository = repository
        self.settings = settings

    def process(self, parsed_email: ParsedEmail) -> OrderResult:
        email_date = parsed_email.sent_at.date().isoformat() if parsed_email.sent_at else None
        logger.info("Workflow started")
        extracted = self.llm_client.extract_order(parsed_email.raw_text, email_date)
        logger.info("Extraction successful")
        previous_order_reference = bool(
            re.search(
                r"\b(same as last time|same as (?:my|our) previous order|repeat (?:my|our) last order)\b",
                parsed_email.raw_text,
                re.IGNORECASE,
            )
        )
        result = build_order_result(
            extracted,
            email_date,
            self.settings,
            self.repository,
            previous_order_reference=previous_order_reference,
        )
        result.reply = self.llm_client.draft_reply(result.customer, result.model_dump(exclude={"reply"}))
        logger.info("Workflow completed with status=%s", result.status)
        return result
