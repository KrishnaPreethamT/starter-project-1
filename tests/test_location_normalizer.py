import pytest

from app.services.location_normalizer import normalize_delivery_city


@pytest.mark.parametrize(
    ("model_city", "body", "customer", "expected"),
    [
        (
            "Kakkanad, Kochi",
            "Please quote, delivered to Coastline Telecom, Kakkanad, Kochi by 15 December.",
            "Coastline Telecom",
            "Kochi",
        ),
        (
            "Salt Lake, Kolkata",
            "We need delivery to Eventora, Salt Lake, Kolkata by 9 December.",
            "Eventora",
            "Kolkata",
        ),
        (
            "Panjim",
            "Please deliver to Brightline Design, Panjim, Goa by 12 December.",
            "Brightline Design",
            "Goa",
        ),
        (
            "Indiranagar, Bengaluru, Karnataka",
            "Ship to Indiranagar, Bengaluru, Karnataka, India before 1 May.",
            None,
            "Bengaluru",
        ),
        (
            "Gachibowli, Hyderabad, Telangana, India",
            "Deliver to Gachibowli, Hyderabad, Telangana, India by 1 May.",
            None,
            "Hyderabad",
        ),
        (
            "Andheri West, Mumbai, Maharashtra",
            "Delivery to Andheri West, Mumbai, Maharashtra by 1 May.",
            None,
            "Mumbai",
        ),
        (
            "Whitefield, Bengaluru, KA",
            "Ship to Whitefield, Bengaluru, KA by 1 May.",
            None,
            "Bengaluru",
        ),
    ],
)
def test_normalizes_locality_city_state_addresses(model_city, body, customer, expected):
    assert normalize_delivery_city(model_city, body, customer) == expected


def test_keeps_simple_city_when_address_phrase_is_missing():
    assert normalize_delivery_city("Pune", "Order requested for Pune") == "Pune"
