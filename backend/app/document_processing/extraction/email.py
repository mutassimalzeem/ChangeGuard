"""MIME-aware email messages, including attached RFC822 thread messages."""

import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO

from app.document_processing.extraction.types import ExtractionResult, TextBlock


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "tr", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"p", "div", "tr", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def email_date(value):
    try:
        return parsedate_to_datetime(value).date() if value else None
    except (ValueError, TypeError, OverflowError):
        return None


class EmailExtractor:
    def extract(self, content: bytes) -> ExtractionResult:
        blocks = []

        def visit(message, path="0", depth=0):
            if depth > 20:
                raise ValueError("Email nesting limit exceeded")
            body = message.get_body(preferencelist=("plain", "html"))
            if body is not None:
                text = body.get_content()
                if body.get_content_type() == "text/html":
                    parser = HTMLText()
                    parser.feed(text)
                    text = "".join(parser.parts)
                # Conventional quoted replies are distinct messages; do not duplicate attachments.
                parts = re.split(
                    r"(?m)(?=^On .+wrote:\s*$|^-{2,}\s*Original Message\s*-{2,}\s*$)", text
                )
                for index, part in enumerate(parts):
                    if not part.strip():
                        continue
                    blocks.append(
                        TextBlock(
                            text=part.strip(),
                            kind="email_message",
                            section=str(message.get("Subject", "Email message")),
                            author=str(message.get("From"))
                            if index == 0 and message.get("From")
                            else None,
                            date=email_date(message.get("Date")) if index == 0 else None,
                            language=str(message.get("Content-Language", "und"))
                            .split(",")[0]
                            .strip(),
                            location={
                                "source": "email",
                                "mime_path": path,
                                "thread_index": index,
                                "message_id": str(message.get("Message-ID", "")),
                                "quoted": index > 0,
                            },
                        )
                    )
            if message.is_multipart():
                for index, part in enumerate(message.iter_parts()):
                    if part.get_content_type() == "message/rfc822":
                        for number, nested in enumerate(part.get_payload()):
                            visit(nested, f"{path}.{index}.{number}", depth + 1)
                    elif part.is_multipart():
                        # Inspect nested MIME containers for forwarded messages, but do
                        # not extract alternative bodies again.
                        visit_attachments(part, f"{path}.{index}", depth + 1)

        def visit_attachments(message, path, depth):
            if depth > 20:
                raise ValueError("Email nesting limit exceeded")
            for index, part in enumerate(message.iter_parts()):
                if part.get_content_type() == "message/rfc822":
                    for number, nested in enumerate(part.get_payload()):
                        visit(nested, f"{path}.{index}.{number}", depth + 1)
                elif part.is_multipart():
                    visit_attachments(part, f"{path}.{index}", depth + 1)

        visit(BytesParser(policy=policy.default).parsebytes(content))
        return ExtractionResult(blocks=blocks)


class OutlookExtractor:
    def extract(self, content: bytes) -> ExtractionResult:
        import olefile

        with olefile.OleFileIO(BytesIO(content)) as message:

            def prop(code):
                for suffix, encoding in (("001F", "utf-16-le"), ("001E", "cp1252")):
                    stream = f"__substg1.0_{code}{suffix}"
                    if message.exists(stream):
                        return message.openstream(stream).read().decode(encoding).rstrip("\x00")
                return None

            text = prop("1000")
            if not text:
                raise ValueError("MSG has no supported plain-text body")
            return ExtractionResult(
                blocks=[
                    TextBlock(
                        text=text,
                        kind="email_message",
                        section=prop("0037") or "Email message",
                        author=prop("0C1A"),
                        location={"source": "msg", "property": "1000"},
                    )
                ]
            )
