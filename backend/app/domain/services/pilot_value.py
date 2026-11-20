"""One presentation of the scoped measurements for screen and both exports."""

import csv
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def report_rows(report):
    rows = []

    def row(label, value):
        rows.append({"label": label, "value": str(value)})

    row("Project", report.project_id)
    row(
        "Report period (UTC)",
        f"{report.start or 'Project inception'} through {report.end.isoformat()}",
    )
    for metric, data in report.metrics.model_dump().items():
        label = metric.replace("_", " ").capitalize()
        if not isinstance(data, dict):
            row(label, data)
        elif "denominator" in data:
            result = "Unmeasured" if data["value"] is None else f"{data['value']:.1%}"
            row(label, f"{result} ({data['numerator']}/{data['denominator']})")
        elif "known_cost_calls" in data:
            mean = f"USD {data['value']}" if data["value"] is not None else "Unmeasured"
            row(
                label,
                f"{mean} per resource. {data['resources']} resources, {data['known_cost_calls']}/{data['calls']} calls priced; known subtotal USD {data['known_subtotal']}.",
            )
        elif data.get("unit") == "seconds":
            mean = "Unmeasured" if data["value"] is None else f"{data['value']:.1f} seconds"
            row(label, f"{mean} ({data['samples']} observations)")
        elif metric == "missing_document_types":
            row(
                "Outstanding document types",
                ", ".join(k.replace("_", " ") for k, v in data.items() if v) or "None",
            )
        else:
            for key, value in sorted(data.items()):
                row(
                    f"{label} / {key.replace('_', ' ')}",
                    value if value is not None else "Unmeasured",
                )
            if not data:
                row(label, "No observations")
    for action in report.next_actions:
        row("Recommended next action", action)
    for note in report.limitations:
        row("Measurement note", note)
    return rows


def export_report(rows, format):
    if format == "csv":
        stream = StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["Measure", "Observation"])
        for row in rows:
            writer.writerow(
                [
                    ("'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell)
                    for cell in row.values()
                ]
            )
        return stream.getvalue().encode("utf-8")
    output = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph("Pilot readiness and value", styles["Title"])]
    for row in rows:
        story.extend(
            [
                Paragraph(
                    f"<b>{escape(row['label'])}</b> · {escape(row['value'])}", styles["BodyText"]
                ),
                Spacer(1, 4),
            ]
        )
    SimpleDocTemplate(output).build(story)
    return output.getvalue()
