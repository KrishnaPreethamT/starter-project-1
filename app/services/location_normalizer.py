"""Normalize delivery-address components to the destination city label."""
import re


_INDIAN_STATES_AND_UTS = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "andaman and nicobar islands", "chandigarh", "dadra and nagar haveli and daman and diu",
    "delhi", "jammu and kashmir", "ladakh", "lakshadweep", "puducherry",
    "ap", "ar", "as", "br", "cg", "ga", "gj", "hr", "hp", "jh", "ka",
    "kl", "mp", "mh", "mn", "ml", "mz", "nl", "od", "pb", "rj", "sk",
    "tn", "ts", "tr", "up", "uk", "wb",
}
_COUNTRIES = {"india", "bharat"}
_DELIVERY_ADDRESS = re.compile(
    r"\b(?:delivery|deliver(?:ed)?|ship(?:ped)?)\s+to\s+(.+?)"
    r"(?=\s+by\s+|\s+before\s+|\s+no\s+later\s+than\s+|[.!?\n]|$)",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())


def _destination_from_components(value: str, customer: str | None) -> str | None:
    components = [part.strip(" \t\r\n.;") for part in value.split(",")]
    components = [part for part in components if part]
    if customer and components and _normalize_text(components[0]) == _normalize_text(customer):
        components.pop(0)
    while len(components) > 1 and _normalize_text(components[-1]) in _COUNTRIES:
        components.pop()
    if not components:
        return None

    # For locality, city, state addresses, the component immediately before
    # the recognized state/UT is the city. Two-part locality/destination forms
    # use the final component, matching common delivery-address wording.
    if len(components) >= 3 and _normalize_text(components[-1]) in _INDIAN_STATES_AND_UTS:
        return components[-2]
    return components[-1]


def normalize_delivery_city(
    extracted_city: str | None,
    email_text: str = "",
    customer: str | None = None,
) -> str | None:
    """Prefer the city in the original delivery phrase, falling back to model output."""
    if email_text:
        match = _DELIVERY_ADDRESS.search(email_text)
        if match:
            city = _destination_from_components(match.group(1), customer)
            if city:
                return city

    if extracted_city:
        return _destination_from_components(extracted_city, customer) or extracted_city.strip() or None
    return None
