"""
orbitval/reporting/pdf_report.py

Produces the human-readable ORF PDF report.
Suitable for mission readiness reviews, launch provider
documentation, and insurance underwriting.

This is the companion to the JSON report — authored for
humans, not machines.
"""

from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable
)
from orbitval.logging import get_logger
log = get_logger("report")


def generate_pdf_report(report: dict, output_path: str | Path) -> None:
    """
    Generate a human-readable PDF from an ORF report dict.

    Args:
        report: ORF report dict (output of generate_json_report)
        output_path: where to write the PDF
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # ── Header ──────────────────────────────────────────────
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#1a1a2e"),
        spaceBefore=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
    )
    mono_style = ParagraphStyle(
        "Mono",
        parent=styles["Code"],
        fontSize=7,
        leading=10,
        textColor=colors.HexColor("#333333"),
    )

    elements.append(Paragraph("OrbitVal Autonomy Stress Test Report", title_style))
    elements.append(Paragraph("OrbitVal Report Format (ORF) v1.0", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 0.3*cm))

    # ── Result banner ────────────────────────────────────────
    result = report.get("overall_result", "UNKNOWN")
    result_color = colors.HexColor("#2d6a4f") if result == "PASS" else colors.HexColor("#c1121f")
    cert = report.get("certification_eligible", False)

    result_style = ParagraphStyle(
        "Result",
        parent=styles["Normal"],
        fontSize=14,
        textColor=result_color,
        spaceAfter=4,
    )
    elements.append(Paragraph(f"Overall Result: {result}", result_style))
    elements.append(Paragraph(
        f"Certification Eligible: {'Yes' if cert else 'No'}",
        body_style
    ))
    elements.append(Spacer(1, 0.3*cm))

    # ── Report metadata ──────────────────────────────────────
    elements.append(Paragraph("Report Metadata", section_style))
    meta = [
        ["Report ID", report.get("report_id", "—")],
        ["Generated At", report.get("generated_at", "—")],
        ["OrbitVal Version", report.get("orbitval_version", "—")],
        ["ORF Spec Version", report.get("orf_spec_version", "—")],
        ["Integrity Hash", report.get("test_integrity_hash", "—")[:32] + "..."],
    ]
    elements.append(_table(meta))

    # ── Satellite ────────────────────────────────────────────
    elements.append(Paragraph("Satellite Under Test", section_style))
    sat = report.get("satellite", {})
    sat_data = [
        ["Name", sat.get("name", "—")],
        ["Form Factor", report.get("form_factor", "—")],
        ["Mass", f"{sat.get('mass_kg', '—')} kg"],
        ["Sensors", ", ".join(s["type"] for s in sat.get("sensors", []))],
        ["Actuators", ", ".join(a["type"] for a in sat.get("actuators", []))],
        ["Battery", f"{sat.get('power', {}).get('battery_capacity_wh', '—')} Wh"],
        ["Solar Panel Area",
         f"{sat.get('power', {}).get('solar_panel_area_m2', '—')} m²"],
    ]
    elements.append(_table(sat_data))

    # ── Simulation parameters ─────────────────────────────────
    elements.append(Paragraph("Simulation Parameters", section_style))
    sim = report.get("simulation", {})
    sim_data = [
        ["Orbit Epoch", sim.get("orbit_epoch", "—")],
        ["Duration", f"{sim.get('duration_s', '—')} seconds"],
        ["Seed", str(sim.get("seed", "—"))],
    ]
    elements.append(_table(sim_data))

    # ── Scenario results ──────────────────────────────────────
    elements.append(Paragraph("Fault Scenario Results", section_style))
    scenario_rows = [["Scenario", "Result", "Duration (s)"]]
    for s in report.get("scenarios_run", []):
        r = s.get("result", "—")
        color_text = f'<font color="{"green" if r == "PASS" else "red"}">{r}</font>'
        scenario_rows.append([
            s.get("name", "—"),
            Paragraph(color_text, body_style),
            str(s.get("duration_s", "—")),
        ])
    elements.append(_table(scenario_rows, header=True))

    # ── Injection trace summary ───────────────────────────────
    elements.append(Paragraph("Injection Trace Summary", section_style))
    trace = report.get("injection_trace", [])
    elements.append(Paragraph(
        f"{len(trace)} injection events recorded across all scenarios.",
        body_style
    ))
    elements.append(Spacer(1, 0.2*cm))

    trace_rows = [["Time (s)", "Fault", "Fields Modified"]]
    for event in trace[:20]:  # show first 20
        trace_rows.append([
            str(event["t"]),
            event["fault_name"],
            ", ".join(event["fields_modified"]),
        ])
    if len(trace) > 20:
        trace_rows.append(["...", f"({len(trace) - 20} more events)", ""])
    elements.append(_table(trace_rows, header=True))

    # ── Integrity notice ──────────────────────────────────────
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 0.2*cm))
    notice_style = ParagraphStyle(
        "Notice",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.HexColor("#888888"),
        leading=10,
    )
    elements.append(Paragraph(
        f"This report was generated by OrbitVal v{report.get('orbitval_version', '0.1.0')}. "
        f"The test_integrity_hash field contains a SHA-256 hash of all inputs and outputs, "
        f"making this report cryptographically verifiable. Any modification to this report "
        f"after generation will invalidate the hash. "
        f"Full hash: {report.get('test_integrity_hash', '—')}",
        notice_style
    ))

    doc.build(elements)
    log.info("PDF report written: %s", output)


def _table(data: list, header: bool = False) -> Table:
    """Build a styled table."""
    t = Table(data, colWidths=None, hAlign="LEFT")
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.HexColor("#f8f8f8"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    else:
        style += [
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a1a2e")),
        ]
    t.setStyle(TableStyle(style))
    return t