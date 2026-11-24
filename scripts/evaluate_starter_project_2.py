"""Score Starter Project 2 labelled emails against the supplied answer key."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate import run_email, normalized

DATA = ROOT / "data/starter-project-2"


def score(actual: dict, expected: dict) -> tuple[int, list[str]]:
    misses = []
    for field in ("status", "customer", "delivery_city", "deadline"):
        a, e = actual.get(field), expected.get(field)
        ok = normalized(a) == normalized(e) if field in ("customer", "delivery_city") else a == e
        if not ok:
            misses.append(field)
    a_items = {(i.get("product_code"), i.get("requested")) for i in actual.get("items", [])}
    e_items = {(i.get("product_code"), i.get("requested")) for i in expected.get("items", [])}
    if a_items != e_items:
        misses.append("items")
    a_quote, e_quote = actual.get("quote"), expected.get("quote")
    quote_matches = (a_quote is None) == (e_quote is None)
    if quote_matches and a_quote is not None:
        def lines(quote):
            return {(x.get("product_code"), x.get("quantity"), x.get("discount_percent"), round(float(x.get("line_total_inr", 0)), 2)) for x in quote.get("lines", [])}
        quote_matches = lines(a_quote) == lines(e_quote)
        for field in ("subtotal_inr", "delivery_inr", "total_inr"):
            quote_matches = quote_matches and round(float(a_quote[field]), 2) == round(float(e_quote[field]), 2)
        quote_matches = quote_matches and a_quote.get("valid_until") == e_quote.get("valid_until")
    if not quote_matches:
        misses.append("quote")
    return 6 - len(misses), misses


def main() -> int:
    answer = json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))
    files = sorted((DATA / "emails/labelled").glob("email_*.txt"))
    points = 0
    for path in files:
        actual = run_email(path)
        score_value, misses = score(actual, answer[path.stem])
        points += score_value
        print(f"{path.stem}: {score_value}/6" + (f" misses={','.join(misses)}" if misses else ""))
    print(f"Total: {points}/{len(files) * 6} ({points / (len(files) * 6):.0%})")
    print("Practice emails (not scored):")
    for path in sorted((DATA / "emails/practice").glob("email_*.txt")):
        print(f"{path.stem}: {json.dumps(run_email(path), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
