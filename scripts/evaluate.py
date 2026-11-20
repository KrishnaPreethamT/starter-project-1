import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE_URL = os.getenv("STARTER_PROJECT_API_URL", "http://127.0.0.1:8000")


def run_email(path: Path) -> dict:
    payload = json.dumps({"email": path.read_text(encoding="utf-8")}).encode("utf-8")
    request = Request(
        f"{BASE_URL.rstrip('/')}/orders",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def normalized(value):
    return value.strip().casefold() if isinstance(value, str) else value


def score_case(actual: dict, expected: dict) -> tuple[int, list[str]]:
    misses = []
    for field in ("status", "customer", "delivery_city", "deadline"):
        if field not in actual or field not in expected:
            misses.append(field)
            continue
        actual_value = actual.get(field)
        expected_value = expected.get(field)
        if field in ("customer", "delivery_city"):
            matches = normalized(actual_value) == normalized(expected_value)
        else:
            matches = actual_value == expected_value
        if not matches:
            misses.append(field)

    actual_items = {(item.get("product_code"), item.get("requested")) for item in actual.get("items", [])}
    expected_items = {(item.get("product_code"), item.get("requested")) for item in expected.get("items", [])}
    if "items" not in actual or "items" not in expected or actual_items != expected_items:
        misses.append("items")
    return 5 - len(misses), misses


def main() -> int:
    answer_key_path = DATA / "answer_key.json"
    labelled_dir = DATA / "emails" / "labelled"
    practice_dir = DATA / "emails" / "practice"
    if not answer_key_path.is_file():
        print(f"Evaluation unavailable: missing {answer_key_path}")
        return 2
    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))
    labelled_files = sorted(labelled_dir.glob("email_*.txt"))
    if len(labelled_files) != 10:
        print(f"Evaluation unavailable: expected 10 labelled emails in {labelled_dir}, found {len(labelled_files)}")
        return 2

    total_points = 0
    completed_cases = 0
    failed_cases = 0
    possible_points = len(labelled_files) * 5
    for email_path in labelled_files:
        key = email_path.stem
        try:
            actual = run_email(email_path)
            points, misses = score_case(actual, answer_key[key])
            total_points += points
            completed_cases += 1
            suffix = f" misses={','.join(misses)}" if misses else ""
            print(f"{key}: {points}/5{suffix}")
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            failed_cases += 1
            print(f"{key}: ERROR {type(exc).__name__}: {exc}")

    if completed_cases == len(labelled_files):
        print(f"Total: {total_points}/{possible_points} ({total_points / possible_points:.0%})")
    else:
        completed_points = completed_cases * 5
        percentage = total_points / completed_points if completed_points else 0
        print(f"Partial total: {total_points}/{completed_points} completed points ({percentage:.0%}); {failed_cases} case(s) failed to run.")
    print("\nPractice emails (not scored):")
    for email_path in sorted(practice_dir.glob("email_*.txt")):
        try:
            print(f"{email_path.stem}: {json.dumps(run_email(email_path), ensure_ascii=False)}")
        except (HTTPError, URLError, TimeoutError) as exc:
            print(f"{email_path.stem}: ERROR {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
