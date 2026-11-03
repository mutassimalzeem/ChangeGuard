"""Paginated PDF exports; user content is escaped before paragraph rendering."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def render_pdf(details, evidence):
    stream = BytesIO()
    styles = getSampleStyleSheet()

    def paragraph(value, style="BodyText"):
        return Paragraph(escape(str(value if value is not None else "Unknown")), styles[style])

    story = [
        paragraph("Change order " + details["reference"], "Title"),
        paragraph(details["title"], "Heading2"),
    ]
    for label, value in (
        ("Status", details["status"]),
        ("Description", details["description"]),
        (
            "Final calculated cost",
            f"{details['currency']} {details['amount']}" if details["amount"] is not None else None,
        ),
        ("Schedule impact (days)", details["time_impact_days"]),
    ):
        story.append(paragraph(f"{label}: {value if value is not None else 'Unknown'}"))
    story.append(paragraph("Cost items (human inputs)", "Heading2"))
    for item in details["cost_items"]:
        story.append(
            paragraph(
                f"{item['description']}: quantity {item['quantity']}, unit rate {item['unit_rate']}"
            )
        )
    story.append(paragraph("Draft narrative and citations", "Heading2"))
    draft = details["draft"] or {}
    for item in draft.get("paragraphs", []):
        story.append(paragraph(item["text"] + " " + " ".join(f"[{c}]" for c in item["citations"])))
    story.append(paragraph("Evidence table", "Heading2"))
    rows = [
        [
            paragraph("Citation / evidence ID"),
            paragraph("Source / page"),
            paragraph("Source quotation"),
        ]
    ]
    labels = {value["evidence_link_id"]: label for label, value in draft.get("sources", {}).items()}
    for link in evidence:
        label = labels.get(str(link.id), "Supporting evidence")
        rows.append(
            [
                paragraph(f"{label}: {link.id}"),
                paragraph(
                    f"{link.source_type}: {link.source_id}; page {link.source_page or 'unknown'}"
                ),
                paragraph(link.source_text_snippet or "Original source; no text quotation"),
            ]
        )
    table = LongTable(
        rows,
        colWidths=[1.7 * inch, 1.8 * inch, 3.0 * inch],
        repeatRows=1,
        splitInRow=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ]
        )
    )
    story.extend([table, Spacer(1, 12), paragraph("Approval history", "Heading2")])
    for decision in details["approval_history"]:
        story.append(
            paragraph(
                f"{decision['status']} | actor {decision['decided_by_id']} | "
                f"date {decision['decided_at']} | reason: {decision['reason']}"
            )
        )
    if not details["approval_history"]:
        story.append(paragraph("No approval decisions recorded."))
    SimpleDocTemplate(
        stream, title="Change order " + details["reference"], leftMargin=36, rightMargin=36
    ).build(story)
    return stream.getvalue()
