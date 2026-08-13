"""PDF Reporter — Phase 3 Production Feature.

Generates structured PDF reports from ReasoningResult objects using reportlab.
Falls back to a text-based report if reportlab is not installed.

Report Sections:
1. Cover Page — Drug, Disease, Recommendation, Date
2. Executive Summary
3. Three-Dimensional Scores (SS, MS, RS)
4. Mechanistic Chain Visualization
5. Contradiction Registry
6. Evidence Summary
7. Scientific Audit Trail

Reference: Phase 3 — Export to PDF reports
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from backend.core.domain.reasoning_result import ReasoningResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Recommendation Colors
# ─────────────────────────────────────────────

_RECOMMENDATION_COLORS: dict[str, tuple[float, float, float]] = {
    "PROMISING": (0.06, 0.73, 0.51),       # green
    "UNCERTAIN": (0.96, 0.62, 0.04),        # amber
    "NOT_RECOMMENDED": (0.93, 0.27, 0.27),  # red
    "INSUFFICIENT_DATA": (0.45, 0.55, 0.65),# grey
}

_SCORE_COLORS: dict[str, tuple[float, float, float]] = {
    "HIGH": (0.06, 0.73, 0.51),
    "MEDIUM": (0.96, 0.62, 0.04),
    "LOW": (0.93, 0.27, 0.27),
    "NONE": (0.45, 0.55, 0.65),
}


class PDFReporter:
    """Generates PDF reports from ReasoningResult objects.

    Uses reportlab if available. Falls back to a plain-text bytes report
    if reportlab is not installed, ensuring the endpoint always works.

    Args:
        drug_name: Drug name for the report header.
        disease_name: Disease name for the report header.
    """

    def __init__(self, drug_name: str, disease_name: str) -> None:
        self._drug = drug_name
        self._disease = disease_name

    def generate(self, result: ReasoningResult) -> bytes:
        """Generate a PDF report from a ReasoningResult.

        Args:
            result: The completed ReasoningResult to report.

        Returns:
            PDF bytes (or UTF-8 text bytes if reportlab unavailable).
        """
        try:
            return self._generate_pdf(result)
        except ImportError:
            logger.warning(
                "reportlab_not_installed",
                extra={"fallback": "text_report"},
            )
            return self._generate_text_report(result)
        except Exception as exc:
            logger.error("pdf_generation_error", extra={"error": str(exc)})
            return self._generate_text_report(result)

    def _generate_pdf(self, result: ReasoningResult) -> bytes:
        """Generate a full PDF report using reportlab."""
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        # Custom styles
        title_style = ParagraphStyle(
            "CyntheraTitle",
            parent=styles["Title"],
            fontSize=22,
            spaceAfter=6,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=12,
            spaceAfter=4,
            textColor=colors.HexColor("#64748b"),
        )
        section_style = ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontSize=14,
            spaceBefore=16,
            spaceAfter=6,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=6,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
        )
        mono_style = ParagraphStyle(
            "Mono",
            parent=styles["Code"],
            fontSize=9,
            spaceAfter=4,
            leading=12,
            textColor=colors.HexColor("#374151"),
            backColor=colors.HexColor("#f8fafc"),
        )

        # Recommendation color
        rec_value = result.recommendation_status.value
        rec_rgb = _RECOMMENDATION_COLORS.get(rec_value, (0.45, 0.55, 0.65))
        rec_color = colors.Color(*rec_rgb)

        story: list[Any] = []

        # ── Cover ──────────────────────────────────────
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph("CYNTHERA", title_style))
        story.append(Paragraph("Drug Repurposing AI Report", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#6366f1")))
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph(f"<b>Drug:</b> {self._drug}", body_style))
        story.append(Paragraph(f"<b>Disease:</b> {self._disease}", body_style))
        story.append(Paragraph(
            f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            body_style,
        ))
        story.append(Spacer(1, 0.5 * cm))

        # Recommendation badge
        rec_table = Table(
            [[f"Recommendation: {rec_value}"]],
            colWidths=[12 * cm],
        )
        rec_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), rec_color),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 14),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [8]),
        ]))
        story.append(rec_table)
        story.append(Spacer(1, 0.5 * cm))

        # ── Executive Summary ──────────────────────────
        story.append(Paragraph("Executive Summary", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
        story.append(Paragraph(result.audit_report.summary, body_style))

        # ── Three-Dimensional Scores ───────────────────
        story.append(Paragraph("Three-Dimensional Score Assessment", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))

        sa = result.support_assessment
        ma = result.mechanistic_assessment
        ra = result.risk_assessment

        score_data = [
            ["Dimension", "Score", "Level", "Details"],
            [
                "Support Score (SS)",
                f"{sa.score:.3f}",
                sa.level,
                f"{sa.evidence_count} evidence records",
            ],
            [
                "Mechanistic Score (MS)",
                f"{ma.score:.3f}",
                ma.level,
                f"{ma.pathway_count} pathways",
            ],
            [
                "Risk Score (RS)",
                f"{ra.score:.3f}",
                ra.level,
                f"{ra.failed_trial_count} failed trials, {ra.contradiction_count} contradictions",
            ],
        ]
        score_table = Table(score_data, colWidths=[5 * cm, 3 * cm, 3 * cm, 6 * cm])
        score_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 0.3 * cm))

        # ── Scientific Context (dimensional prior knowledge) ────────────
        sc = getattr(result.audit_report, "scientific_context", {}) or {}
        if sc:
            story.append(Paragraph("Scientific Context — Prior Knowledge", section_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            context_data = [["Dimension", "Status", "Confidence", "Evidence"]]
            for dim_key in ("regulatory", "repurposing", "mechanistic", "clinical", "knowledge_maturity"):
                dim = sc.get(dim_key) or {}
                if not dim:
                    continue
                context_data.append([
                    str(dim.get("dimension", dim_key)).replace("_", " ").title(),
                    str(dim.get("status", "—")),
                    f"{float(dim.get('confidence', 0.0)):.0%}",
                    "; ".join(dim.get("evidence", [])[:2])[:120],
                ])
            if len(context_data) > 1:
                context_table = Table(context_data, colWidths=[3.5 * cm, 3.5 * cm, 2.5 * cm, 7.5 * cm])
                context_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0fdfa"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(context_table)
                related = sc.get("related_pairs", []) or []
                if related:
                    rel_text = ", ".join(
                        f"{p.get('drug')} → {p.get('disease')} ({p.get('similarity', 0):.2f})"
                        for p in related[:3]
                    )
                    story.append(Paragraph(f"<b>Related prior-knowledge pairs:</b> {rel_text}", body_style))
                story.append(Spacer(1, 0.2 * cm))

        # ── Mechanistic Chain ──────────────────────────
        if ma.mechanistic_chain:
            story.append(Paragraph("Mechanistic Chain", section_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            chain_text = " → ".join(ma.mechanistic_chain)
            story.append(Paragraph(chain_text, mono_style))
            story.append(Paragraph(ma.rationale, body_style))

        # ── Contradictions ─────────────────────────────
        if result.contradictions:
            story.append(Paragraph("Contradiction Registry", section_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            con_data = [["Shared Subject", "Score", "Conflict Type", "Explanation"]]
            for con in result.contradictions[:10]:
                con_data.append([
                    con.shared_subject[:30],
                    f"{con.contradiction_score:.3f}",
                    con.conflict_type,
                    con.explanation[:80] + "..." if len(con.explanation) > 80 else con.explanation,
                ])
            con_table = Table(con_data, colWidths=[4 * cm, 2.5 * cm, 3 * cm, 7.5 * cm])
            con_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fdf4ff"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(con_table)

        # ── Recommendation Rules ───────────────────────
        story.append(Paragraph("Recommendation Rule Engine Output", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
        for reason in result.recommendation_reasons:
            story.append(Paragraph(f"• {reason}", body_style))

        # ── Data Gaps ──────────────────────────────────
        if result.audit_report.data_gaps:
            story.append(Paragraph("Data Gaps Identified", section_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            for gap in result.audit_report.data_gaps:
                story.append(Paragraph(f"• {gap}", body_style))

        # ── Confidence Narrative ───────────────────────
        story.append(Paragraph("Confidence Narrative", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
        story.append(Paragraph(result.audit_report.confidence_narrative, body_style))

        # ── Footer ─────────────────────────────────────
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
        story.append(Paragraph(
            f"Generated by CYNTHERA v1.0 | Rule Set: {result.rule_set_version} | "
            f"Duration: {result.reasoning_duration_ms:.0f}ms",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER),
        ))

        doc.build(story)
        return buffer.getvalue()

    def _generate_text_report(self, result: ReasoningResult) -> bytes:
        """Generate a plain-text fallback report."""
        sa = result.support_assessment
        ma = result.mechanistic_assessment
        ra = result.risk_assessment

        lines = [
            "=" * 70,
            "CYNTHERA DRUG REPURPOSING REPORT",
            "=" * 70,
            f"Drug: {self._drug}",
            f"Disease: {self._disease}",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Recommendation: {result.recommendation_status.value}",
            "",
            "─" * 70,
            "EXECUTIVE SUMMARY",
            "─" * 70,
            result.audit_report.summary,
            "",
            "─" * 70,
            "THREE-DIMENSIONAL SCORES",
            "─" * 70,
            f"Support Score (SS):     {sa.score:.3f}  [{sa.level}]",
            f"  {sa.rationale}",
            f"Mechanistic Score (MS): {ma.score:.3f}  [{ma.level}]",
            f"  {ma.rationale}",
            f"Risk Score (RS):        {ra.score:.3f}  [{ra.level}]",
            f"  {ra.rationale}",
            "",
        ]

        if ma.mechanistic_chain:
            lines += [
                "─" * 70,
                "MECHANISTIC CHAIN",
                "─" * 70,
                " → ".join(ma.mechanistic_chain),
                "",
            ]

        sc = getattr(result.audit_report, "scientific_context", {}) or {}
        if sc:
            lines += [
                "─" * 70,
                "SCIENTIFIC CONTEXT — PRIOR KNOWLEDGE",
                "─" * 70,
            ]
            for dim_key in ("regulatory", "repurposing", "mechanistic", "clinical", "knowledge_maturity"):
                dim = sc.get(dim_key) or {}
                if not dim:
                    continue
                label = str(dim.get("dimension", dim_key)).replace("_", " ").title()
                lines.append(
                    f"  {label:<22} {dim.get('status', '—'):<15} "
                    f"({float(dim.get('confidence', 0.0)):.0%})"
                )
                for evidence in dim.get("evidence", [])[:2]:
                    lines.append(f"      - {evidence}")
            related = sc.get("related_pairs", []) or []
            if related:
                lines.append("  Related prior-knowledge pairs:")
                for p in related[:3]:
                    lines.append(
                        f"      - {p.get('drug')} → {p.get('disease')} "
                        f"({p.get('similarity', 0):.2f})"
                    )
            lines.append("")

        if result.contradictions:
            lines += ["─" * 70, "CONTRADICTIONS", "─" * 70]
            for con in result.contradictions[:10]:
                lines.append(f"  • {con.explanation}")
            lines.append("")

        lines += [
            "─" * 70,
            "RECOMMENDATION RATIONALE",
            "─" * 70,
        ]
        for reason in result.recommendation_reasons:
            lines.append(f"  • {reason}")

        if result.audit_report.data_gaps:
            lines += ["", "─" * 70, "DATA GAPS", "─" * 70]
            for gap in result.audit_report.data_gaps:
                lines.append(f"  • {gap}")

        lines += [
            "",
            "=" * 70,
            f"CYNTHERA v1.0 | Rule Set: {result.rule_set_version} | "
            f"Duration: {result.reasoning_duration_ms:.0f}ms",
            "=" * 70,
        ]

        return "\n".join(lines).encode("utf-8")
