from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.config import Settings
from app.email_parser import ParsedEmail
from app.models.orders import ExtractedItem, ExtractedOrder, ProductResolution
from app.repositories.products import HistoricalItem, ProductStock
from app.services.order_workflow import OrderWorkflow


def make_settings(**overrides):
    values = dict(
        azure_openai_endpoint="", azure_openai_deployment="", azure_openai_api_version="",
        azure_openai_api_key="", database_url="unused", lead_time_days=3,
        discount_tiers="9:0,49:5,199:8,*:12",
        free_delivery_threshold_inr=Decimal("50000"), delivery_charge_inr=Decimal("1500"),
        quote_validity_days=7,
    )
    values.update(overrides)
    return Settings(**values)


class FakeRepository:
    def __init__(self, history=None):
        self.products = {
            "TAB-08": ProductStock("TAB-08", "Nimbus Tab 8 Lite", 60, Decimal("9499")),
            "EAR-01": ProductStock("EAR-01", "Pebble Buds", 350, Decimal("1299")),
            "EAR-02": ProductStock("EAR-02", "Pebble Buds Pro", 80, Decimal("3499")),
            "HDS-10": ProductStock("HDS-10", "Quietline Headset", 45, Decimal("2299")),
            "PHN-X9": ProductStock("PHN-X9", "Astra X9", 6, Decimal("34999")),
        }
        self.history = history or []

    def find_product(self, name):
        return next((p for p in self.products.values() if p.product_name.casefold() == name.casefold()), None)

    def find_product_by_code(self, code):
        return self.products.get(code)

    def latest_order(self, customer):
        return self.history


class FakeLLM:
    def __init__(self, order):
        self.order = order

    def extract_order(self, raw_email, email_date):
        return self.order

    def draft_reply(self, customer, result):
        return "Draft reply"

    def embed_texts(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def resolve_product_description(self, description, candidates):
        return ProductResolution(product_code=candidates[0]["product_code"])


class FakeDocuments:
    def __init__(self, *matches):
        self.matches = matches

    def search(self, embedding, limit=5):
        return list(self.matches[:limit])


class Match:
    def __init__(self, source, content):
        self.source = source
        self.heading = "Overview"
        self.content = content
        self.distance = 0.1


def parsed(date="2026-11-20", body="Order"):
    return ParsedEmail(
        message=None,
        raw_text=body,
        body=body,
        sent_at=datetime.fromisoformat(date).replace(tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("quantity,discount", [(9, 0), (10, 5), (49, 5), (50, 8), (199, 8), (200, 12)])
def test_discount_tier_boundaries(quantity, discount):
    settings = make_settings()
    assert settings.discount_percent(quantity) == discount


def test_quote_uses_stock_cap_decimal_math_free_delivery_and_email_date():
    order = ExtractedOrder(
        customer="Sunbeam International School", delivery_city="Pune", deadline="2026-12-11",
        items=[ExtractedItem(product_name="Nimbus Tab 8 Lite", quantity=60)],
    )
    workflow = OrderWorkflow(FakeLLM(order), FakeRepository(), make_settings())
    result = workflow.process(parsed())
    assert result.status == "Ready"
    assert result.quote is not None
    assert result.quote.lines[0].quantity == 60
    assert result.quote.lines[0].discount_percent == 8
    assert result.quote.lines[0].line_total_inr == Decimal("524344.80")
    assert result.quote.delivery_inr == Decimal("0")
    assert result.quote.valid_until == "2026-11-27"


def test_partial_quote_uses_available_units_and_delivery_charge():
    repo = FakeRepository()
    repo.products["HDS-10"] = ProductStock("HDS-10", "Quietline Headset", 4, Decimal("2299"))
    order = ExtractedOrder(customer="Callpoint Services", delivery_city="Thiruvananthapuram", deadline="2026-12-07",
                           items=[ExtractedItem(product_name="Quietline Headset", quantity=8)])
    result = OrderWorkflow(FakeLLM(order), repo, make_settings()).process(parsed())
    assert result.status == "Partial"
    assert result.quote.lines[0].quantity == 4
    assert result.quote.delivery_inr == Decimal("1500")
    assert result.quote.total_inr == Decimal("10696.00")


def test_repeat_order_uses_latest_history_rows():
    repo = FakeRepository([HistoricalItem("TAB-08", "Nimbus Tab 8 Lite", 25)])
    order = ExtractedOrder(customer="Brightpath Coaching Centre", delivery_city="Nagpur", deadline="2026-12-01", repeat_order=True)
    result = OrderWorkflow(FakeLLM(order), repo, make_settings()).process(parsed())
    assert result.status == "Ready"
    assert [(item.product_code, item.requested) for item in result.items] == [("TAB-08", 25)]


def test_repeat_order_without_history_needs_information_and_has_no_quote():
    order = ExtractedOrder(customer="Kaveri Hospitals", delivery_city="Bengaluru", deadline="2026-12-10", repeat_order=True)
    result = OrderWorkflow(FakeLLM(order), FakeRepository(), make_settings()).process(parsed())
    assert result.status == "Need info"
    assert result.quote is None
    assert result.issues == ["Refers to a previous order, but there is no order history for Kaveri Hospitals"]


def test_rag_resolves_description_only_from_retrieved_catalogue_candidates():
    order = ExtractedOrder(customer="Lotus Mobiles", delivery_city="Coimbatore", deadline="2026-12-04",
                           items=[ExtractedItem(product_name="black 128 GB 5G phone", quantity=5, is_description=True)])
    docs = FakeDocuments(Match("brochures/PHN-X9.md", "Astra X9 black 128 GB 5G phone"))
    result = OrderWorkflow(FakeLLM(order), FakeRepository(), make_settings(), docs).process(parsed())
    assert result.status == "Ready"
    assert result.items[0].product_code == "PHN-X9"
    assert result.items[0].product_name == "black 128 GB 5G phone"


def test_rag_ambiguous_description_requires_customer_clarification():
    class AmbiguousLLM(FakeLLM):
        def resolve_product_description(self, description, candidates):
            return ProductResolution(ambiguous=True, matching_product_codes=["EAR-01", "EAR-02"])

    order = ExtractedOrder(customer="Eventora", delivery_city="Kolkata", deadline="2026-12-09",
                           items=[ExtractedItem(product_name="wireless earbuds", quantity=20, is_description=True)])
    docs = FakeDocuments(Match("brochures/EAR-01.md", "Pebble Buds wireless earbuds"),
                         Match("brochures/EAR-02.md", "Pebble Buds Pro wireless earbuds"))
    result = OrderWorkflow(AmbiguousLLM(order), FakeRepository(), make_settings(), docs).process(parsed())
    assert result.status == "Need info"
    assert result.items[0].product_code is None
    assert result.issues == ["Ambiguous product: wireless earbuds (could be Pebble Buds or Pebble Buds Pro)"]
    assert result.quote is None
