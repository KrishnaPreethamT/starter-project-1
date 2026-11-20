from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.email_parser import ParsedEmail, parse_email
from app.models.orders import ExtractedItem, ExtractedOrder
from app.repositories.products import ProductStock
from app.services.order_workflow import OrderWorkflow, build_order_result, compare_stock


class FakeRepository:
    def __init__(self, products=None):
        self.products = products or {}

    def find_product(self, product_name):
        return self.products.get(" ".join(product_name.split()).casefold())


def make_settings():
    return Settings("", "", "", "", "unused", lead_time_days=3)


def repository():
    return FakeRepository(
        {
            "corelink book 14": ProductStock("LAP-14", "Corelink Book 14", 12),
            "nimbus tab 10": ProductStock("TAB-10", "Nimbus Tab 10", 25),
            "volt 65w charger": ProductStock("CHG-65", "Volt 65W Charger", 200),
        }
    )


def test_required_fields_are_reported():
    result = build_order_result(ExtractedOrder(), "2026-11-17", make_settings(), repository())
    assert result.status == "Need info"
    assert "Missing customer organisation name" in result.issues
    assert "Missing delivery city" in result.issues
    assert "No items listed" in result.issues


@pytest.mark.parametrize("quantity", [None, "a few", "0", 0, "-2", "1.5"])
def test_invalid_quantities_are_null_and_reported(quantity):
    extracted = ExtractedOrder(
        customer="Lakeview Hospital",
        delivery_city="Bhopal",
        items=[ExtractedItem(product_name="Corelink Book 14", quantity=quantity)],
    )
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.status == "Need info"
    assert result.items[0].requested is None
    assert any(issue.startswith("Invalid quantity") for issue in result.issues)


def test_valid_quantity_string_becomes_integer():
    extracted = ExtractedOrder(
        customer="Lakeview Hospital",
        delivery_city="Bhopal",
        items=[ExtractedItem(product_name="Corelink Book 14", quantity="8")],
    )
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.items[0].requested == 8


def test_valid_and_invalid_deadlines():
    extracted = ExtractedOrder(
        customer="Lakeview Hospital",
        delivery_city="Bhopal",
        deadline="2026-11-20",
        items=[ExtractedItem(product_name="Corelink Book 14", quantity=1)],
    )
    ready = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    invalid = build_order_result(extracted.model_copy(update={"deadline": "2026-11-19"}), "2026-11-17", make_settings(), repository())
    assert ready.status == "Ready"
    assert invalid.status == "Need info"
    assert invalid.issues[0].startswith("Deadline 2026-11-19")


def test_invalid_date_format_is_need_info_and_null():
    extracted = ExtractedOrder(customer="Lakeview Hospital", delivery_city="Bhopal", deadline="next Tuesday", items=[ExtractedItem(product_name="Corelink Book 14", quantity=1)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.deadline is None
    assert result.status == "Need info"


def test_ready_status_and_empty_issues():
    extracted = ExtractedOrder(customer="Lakeview Hospital", delivery_city="Bhopal", items=[ExtractedItem(product_name="Corelink Book 14", quantity=8)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.status == "Ready"
    assert result.issues == []


def test_partial_status_for_insufficient_stock():
    extracted = ExtractedOrder(customer="Greenfield Public School", delivery_city="Nagpur", items=[ExtractedItem(product_name="Nimbus Tab 10", quantity=40)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.status == "Partial"
    assert result.issues == ["Nimbus Tab 10: requested 40, only 25 in stock"]


def test_need_info_takes_priority_over_partial():
    extracted = ExtractedOrder(customer="Greenfield Public School", delivery_city=None, items=[ExtractedItem(product_name="Nimbus Tab 10", quantity=40)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.status == "Need info"
    assert any("only 25 in stock" in issue for issue in result.issues)
    assert "Missing delivery city" in result.issues


def test_unknown_product_fields_are_null():
    extracted = ExtractedOrder(customer="Lakeview Hospital", delivery_city="Bhopal", items=[ExtractedItem(product_name="Nimbus Tab 12", quantity=30)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.status == "Need info"
    assert result.items[0].product_code is None
    assert result.items[0].available is None
    assert result.items[0].requested == 30


def test_previous_order_reference_forces_need_info():
    class FakeLLM:
        def extract_order(self, raw_email, email_date):
            return ExtractedOrder(customer="Orbit Retail", delivery_city="Chennai")

        def draft_reply(self, customer, result):
            return "Please provide the order details."

    parsed = ParsedEmail(
        message=None,
        raw_text="From: customer@example.com\nDate: Tue, 17 Nov 2026 09:00:00 +0000\n\nSame as last time.",
        body="Same as last time.",
        sent_at=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
    )
    result = OrderWorkflow(FakeLLM(), repository(), make_settings()).process(parsed)
    assert result.status == "Need info"
    assert "Refers to a previous order" in result.issues
    assert "No items listed" in result.issues


def test_stock_comparison_is_independent_of_database():
    assert compare_stock(4, 4)
    assert not compare_stock(5, 4)
    assert not compare_stock(None, 4)


def test_product_match_ignores_case_and_extra_spaces():
    extracted = ExtractedOrder(customer="Lakeview Hospital", delivery_city="Bhopal", items=[ExtractedItem(product_name="  CORELINK   Book 14 ", quantity=1)])
    result = build_order_result(extracted, "2026-11-17", make_settings(), repository())
    assert result.items[0].product_code == "LAP-14"


def test_email_uses_email_parser_and_reads_date_header():
    parsed = parse_email("From: sales@example.com\nDate: Tue, 17 Nov 2026 09:00:00 +0000\nSubject: Order\n\nPlease send one item.")
    assert parsed.sent_at.date().isoformat() == "2026-11-17"
