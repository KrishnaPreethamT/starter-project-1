from dataclasses import dataclass
from datetime import datetime
from email import message_from_string
from email.message import Message
from email.utils import parsedate_to_datetime


class EmailInputError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedEmail:
    message: Message
    raw_text: str
    body: str
    sent_at: datetime | None


def parse_email(raw_text: str) -> ParsedEmail:
    if not raw_text.strip():
        raise EmailInputError("Email must not be empty")
    message = message_from_string(raw_text)
    body = message.get_payload(decode=False)
    if not isinstance(body, str):
        body = ""
    body = body.strip()
    if not message.keys() or not body:
        raise EmailInputError("Email must include headers and a non-empty body")
    date_header = message.get("Date")
    sent_at = None
    if date_header:
        try:
            sent_at = parsedate_to_datetime(date_header)
        except (TypeError, ValueError, OverflowError):
            sent_at = None
    return ParsedEmail(message=message, raw_text=raw_text, body=body, sent_at=sent_at)
