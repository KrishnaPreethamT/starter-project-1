import logging
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from app.config import Settings
from app.email_parser import ParsedEmail
from app.models.orders import ExtractedItem, ExtractedOrder, OrderItemResult, OrderResult, Quote, QuoteLine
from app.repositories.products import ProductStock
from app.repositories.documents import DocumentRepository
from app.services.location_normalizer import normalize_delivery_city

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def extract_order(self, raw_email: str, email_date: str | None) -> ExtractedOrder: ...

    def draft_reply(self, customer: str | None, result: dict) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def resolve_product_description(self, description: str, candidates: list[dict]): ...


class ProductLookup(Protocol):
    def find_product(self, product_name: str) -> ProductStock | None: ...

    def find_product_by_code(self, product_code: str) -> ProductStock | None: ...

    def latest_order(self, customer: str): ...


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


def _question_sentences(body: str) -> list[str]:
    """Keep explicit customer questions available to the reply and RAG steps."""
    questions: list[str] = []
    for line in body.splitlines():
        questions.extend(
            question.strip()
            for question in re.findall(r"[^?\n]*\?", line)
            if question.strip()
        )
    return questions


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
        if extracted_item.product_code and hasattr(repository, "find_product_by_code"):
            product = repository.find_product_by_code(extracted_item.product_code)
        if product is None:
            logger.info("Stock lookup: product=%s found=false", name)
            if extracted_item.resolution_candidates:
                choices = " or ".join(extracted_item.resolution_candidates)
                issues.append(f"Ambiguous product: {name} (could be {choices})")
            else:
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
    if previous_order_reference and not extracted.items:
        issues.insert(0, "Refers to a previous order")

    need_info_prefixes = (
        "Invalid",
        "Unknown",
        "Ambiguous",
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
    def __init__(self, llm_client: LLMClient, repository: ProductLookup, settings: Settings, documents: DocumentRepository | None = None):
        self.llm_client = llm_client
        self.repository = repository
        self.settings = settings
        self.documents = documents

    @staticmethod
    def _log_retrieved_chunks(purpose: str, chunks) -> None:
        for chunk in chunks:
            similarity = 1.0 - chunk.distance if chunk.distance is not None else None
            logger.info(
                "RAG retrieval purpose=%s source=%s heading=%s cosine_similarity=%s chunk_preview=%r",
                purpose,
                chunk.source,
                chunk.heading,
                f"{similarity:.4f}" if similarity is not None else "unavailable",
                chunk.content[:160],
            )

    def _resolve_descriptions(self, order: ExtractedOrder) -> ExtractedOrder:
        if not self.documents:
            return order
        for item in order.items:
            name = _clean(item.product_name)
            if not name:
                continue

            # Resolve canonical names and controlled category aliases before
            # asking the semantic resolver. Repository lookup returns a match
            # only when the alias identifies exactly one catalogue row.
            direct_match = self.repository.find_product(name)
            if direct_match:
                item.product_code = direct_match.product_code
                item.resolution_candidates = []
                continue

            item.product_code = None
            item.resolution_candidates = []
            vector = self.llm_client.embed_texts([name])[0]
            # Search enough chunks that several chunks from one brochure do
            # not crowd a second matching product out of the candidate set.
            matches = self.documents.search(vector, limit=15)
            self._log_retrieved_chunks("product_resolution", matches)
            candidates = []
            seen = set()
            for match in matches:
                if not match.source.startswith("brochures/"):
                    continue
                code = match.source.split("/")[-1].removesuffix(".md")
                if code not in seen:
                    seen.add(code)
                    product = self.repository.find_product_by_code(code)
                    if product:
                        candidates.append({"product_code": code, "product_name": product.product_name, "evidence": match.content[:1000]})
            if candidates:
                normalized_description = " ".join(re.sub(r"[^\w\s]", " ", name.casefold()).split())
                literal_codes = [
                    candidate["product_code"]
                    for candidate in candidates
                    if normalized_description
                    and normalized_description
                    in " ".join(re.sub(r"[^\w\s]", " ", candidate["evidence"].casefold()).split())
                ]
                literal_codes = list(dict.fromkeys(literal_codes))
                if len(literal_codes) > 1:
                    matching = set(literal_codes)
                    item.resolution_candidates = [
                        candidate["product_name"] for candidate in candidates
                        if candidate["product_code"] in matching
                    ]
                    continue

                resolution = self.llm_client.resolve_product_description(name, candidates)
                candidate_codes = {candidate["product_code"] for candidate in candidates}
                matching_codes = list(dict.fromkeys(
                    code for code in resolution.matching_product_codes if code in candidate_codes
                ))
                all_matching_codes = list(dict.fromkeys(matching_codes + literal_codes))
                if len(all_matching_codes) == 1 and resolution.product_code in (None, all_matching_codes[0]):
                    # The validated match list is authoritative when the LLM's
                    # boolean ambiguity flag contradicts a single candidate.
                    item.product_code = all_matching_codes[0]
                elif len(all_matching_codes) > 1 or (resolution.ambiguous and len(candidates) > 1):
                    item.product_code = None
                    matching = set(all_matching_codes)
                    item.resolution_candidates = [
                        candidate["product_name"] for candidate in candidates
                        if not matching or candidate["product_code"] in matching
                    ]
        return order

    def _reference_context(
        self,
        order: ExtractedOrder,
        customer_questions: list[str] | None = None,
    ) -> list[str]:
        if not self.documents:
            return []
        queries = ["pricing discounts delivery charges quote validity payment warranty returns"]
        queries.extend(item.product_name for item in order.items if item.product_name)
        question_queries = customer_questions or []
        queries.extend(question_queries)
        context: list[str] = []
        seen: set[tuple[str, str]] = set()
        for query in queries:
            vector = self.llm_client.embed_texts([query])[0]
            chunks = self.documents.search(vector, limit=5 if query in question_queries else 3)
            self._log_retrieved_chunks("reply_context", chunks)
            for chunk in chunks:
                key = (chunk.source, chunk.heading)
                if key not in seen:
                    seen.add(key)
                    context.append(f"Source: {chunk.source} — {chunk.heading}\n{chunk.content[:1200]}")
        return context

    def _quote(self, result: OrderResult, email_date: str | None) -> None:
        if result.status == "Need info" or not email_date:
            result.quote = None
            return
        quote_lines: list[QuoteLine] = []
        subtotal = Decimal("0")
        for item_result in result.items:
            if not item_result.product_code or not item_result.requested or not item_result.available:
                continue
            product = self.repository.find_product_by_code(item_result.product_code)
            if not product:
                continue
            quantity = min(item_result.requested, item_result.available)
            if quantity <= 0:
                continue
            discount = self.settings.discount_percent(quantity)
            amount = (product.unit_price_inr * quantity * (Decimal(100 - discount) / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            subtotal += amount
            quote_lines.append(
                QuoteLine(
                    product_code=product.product_code,
                    quantity=quantity,
                    unit_price_inr=product.unit_price_inr,
                    discount_percent=discount,
                    line_total_inr=amount,
                )
            )
        if not quote_lines:
            result.quote = None
            return
        delivery = Decimal("0") if subtotal >= self.settings.free_delivery_threshold_inr else self.settings.delivery_charge_inr
        valid_until = date.fromisoformat(email_date) + timedelta(days=self.settings.quote_validity_days)
        result.quote = Quote(
            lines=quote_lines,
            subtotal_inr=subtotal,
            delivery_inr=delivery,
            total_inr=subtotal + delivery,
            valid_until=valid_until.isoformat(),
        )

    def process(self, parsed_email: ParsedEmail) -> OrderResult:
        email_date = parsed_email.sent_at.date().isoformat() if parsed_email.sent_at else None
        customer_questions = _question_sentences(parsed_email.body)
        logger.info("Workflow started")
        extracted = self.llm_client.extract_order(parsed_email.raw_text, email_date)
        logger.info("Extraction successful")
        extracted.delivery_city = normalize_delivery_city(
            extracted.delivery_city,
            parsed_email.body,
            extracted.customer,
        )
        context = self._reference_context(extracted, customer_questions)
        extracted = self._resolve_descriptions(extracted)
        previous_order_reference = bool(
            re.search(
                r"\b(same as last time|same as (?:my|our) previous order|repeat (?:my|our) last order)\b",
                parsed_email.raw_text,
                re.IGNORECASE,
            )
        )
        previous_order_reference = previous_order_reference or extracted.repeat_order
        customer = _clean(extracted.customer)
        if previous_order_reference and hasattr(self.repository, "latest_order"):
            # For repeat requests, the database order is authoritative even if
            # the model extracted products or quantities from the email text.
            extracted.items = []
            history = self.repository.latest_order(customer) if customer else []
            if history:
                extracted.items = [
                    ExtractedItem(product_name=row.product_name, product_code=row.product_code, quantity=row.quantity)
                    for row in history
                ]
            elif customer:
                result = build_order_result(extracted, email_date, self.settings, self.repository)
                result.issues = [issue for issue in result.issues if issue != "No items listed"]
                result.issues.insert(0, f"Refers to a previous order, but there is no order history for {customer}")
                result.status = "Need info"
                payload = result.model_dump(exclude={"reply"})
                payload["reference_context"] = context
                payload["customer_questions"] = customer_questions
                result.reply = self.llm_client.draft_reply(result.customer, payload)
                return result
        result = build_order_result(
            extracted,
            email_date,
            self.settings,
            self.repository,
            previous_order_reference=previous_order_reference and not hasattr(self.repository, "latest_order"),
        )
        self._quote(result, email_date)
        payload = result.model_dump(exclude={"reply"})
        payload["reference_context"] = context
        payload["customer_questions"] = customer_questions
        result.reply = self.llm_client.draft_reply(result.customer, payload)
        logger.info("Workflow completed with status=%s", result.status)
        return result
