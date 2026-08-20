"""Citation-preserving Markdown, PDF, and JSON artifact export."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import RunArtifact, SourceDecision


def _safe_pdf_text(text: str) -> str:
    """Never pass untrusted raw bytes to ReportLab's built-in fonts."""
    return "".join(
        character for character in text if character.isprintable() or character in "\n\t"
    )


def render_markdown(artifact: RunArtifact) -> str:
    import logging
    logger = logging.getLogger("deeplens.writer")
    
    kept = []
    kept_ids = set()
    for source in artifact.sources:
        if source.quality and source.quality.decision == SourceDecision.KEEP:
            kept.append(source)
            kept_ids.add(source.id)
            
    used_source_ids = {item.source_id for item in artifact.evidence}
    used_source_ids.update({item.source_a for item in artifact.contradictions})
    used_source_ids.update({item.source_b for item in artifact.contradictions})
    
    for source in artifact.sources:
        if source.id in used_source_ids and source.id not in kept_ids:
            logger.warning(f"Citation Warning: Evidence references source {source.id} not marked KEEP. Including in index.")
            kept.append(source)
            kept_ids.add(source.id)
            
    index = {source.id: i + 1 for i, source in enumerate(kept)}
    
    def safe_cite(sid: str) -> str:
        if sid not in index:
            logger.warning(f"Citation Mapping Error: Source {sid} not found in artifact.sources. Handling safely.")
            return "?"
        return str(index[sid])
    lines = [
        "# DeepLens Research Report",
        "",
        f"**Question:** {artifact.query}",
        "",
    ]
    if artifact.executive_summary:
        lines += [
            "## Executive Summary",
            "",
            artifact.executive_summary,
            ""
        ]
    lines += ["## Key Findings", ""]
    for packet in artifact.packets:
        lines.append(f"### {packet.perspective}")
        for evidence_id in packet.evidence_ids[:3]:
            evidence = next(item for item in artifact.evidence if item.id == evidence_id)
            lines.append(f"- {evidence.claim} [{safe_cite(evidence.source_id)}]")
    lines += ["", "## Detailed Analysis", ""]
    for packet in artifact.packets:
        lines.append(
            f"**{packet.perspective}.** "
            + (" ".join(packet.findings[:2]) or "No verified evidence was found for this perspective.")
        )
    lines += [
        "",
        "## Areas of Agreement",
        "",
        "Findings are grouped by perspective; corroboration is indicated through source citations.",
        "",
        "## Conflicting Evidence",
        "",
    ]
    lines += [
        f"- {item.explanation}: {item.claim_a} [{safe_cite(item.source_a)}] vs. {item.claim_b} [{safe_cite(item.source_b)}]."
        for item in artifact.contradictions
    ] or ["No material factual contradictions were detected by the rule-based pass."]
    lines += ["", "## Research Gaps / Uncertainty", ""]
    lines += [f"- {gap.question} — {gap.reason}" for gap in artifact.gaps] or [
        "No automated gaps were identified; this is not proof of completeness."
    ]
    
    if artifact.conclusion:
        lines += [
            "",
            "## Conclusion",
            "",
            artifact.conclusion,
        ]
        
    lines += [
        "",
        "## Sources",
        "",
    ]
    lines += [f"[{i}] {source.title}. {source.url}" for i, source in enumerate(kept, 1)]
    return "\n".join(lines) + "\n"


def export_run(artifact: RunArtifact, output_dir: Path) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", artifact.query.lower()).strip("-")[:60] or "research"
    path = output_dir / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}"
    path.mkdir(parents=True, exist_ok=False)
    markdown = render_markdown(artifact)
    (path / "report.md").write_text(markdown, encoding="utf-8")
    (path / "sources.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in artifact.sources], indent=2),
        encoding="utf-8",
    )
    (path / "evidence.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in artifact.evidence], indent=2),
        encoding="utf-8",
    )
    (path / "run.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    _pdf(artifact, path / "report.pdf")
    return path


def _pdf(artifact: RunArtifact, target: Path) -> None:
    """Make a readable, colored briefing—not a mechanically rendered Markdown file."""
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "lens-title", parent=styles["Title"], textColor=colors.HexColor("#103C55"), spaceAfter=8
    )
    heading = ParagraphStyle(
        "lens-heading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#007D8A"),
        spaceBefore=16,
        spaceAfter=6,
    )
    body = ParagraphStyle("lens-body", parent=styles["BodyText"], leading=15, spaceAfter=7)
    story = [
        Paragraph("DEEPLENS <font color='#00A6A6'>/ RESEARCH BRIEF</font>", title),
        Paragraph(f"<b>Question</b>  {_safe_pdf_text(artifact.query)}", body),
    ]
    summary_text = artifact.executive_summary or "Evidence-grounded synthesis"
    story.append(
        Table(
            [[Paragraph(_safe_pdf_text(summary_text), body)]],
            colWidths=[6.7 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E2F5F3")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#82D5CF")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        )
    )
    story += [Spacer(1, 10), Paragraph("Key findings", heading)]
    
    import logging
    logger = logging.getLogger("deeplens.writer")
    
    kept = []
    kept_ids = set()
    for source in artifact.sources:
        if source.quality and source.quality.decision == SourceDecision.KEEP:
            kept.append(source)
            kept_ids.add(source.id)
            
    used_source_ids = {item.source_id for item in artifact.evidence}
    used_source_ids.update({item.source_a for item in artifact.contradictions})
    used_source_ids.update({item.source_b for item in artifact.contradictions})
    
    for source in artifact.sources:
        if source.id in used_source_ids and source.id not in kept_ids:
            logger.warning(f"Citation Warning: Evidence references source {source.id} not marked KEEP. Including in index.")
            kept.append(source)
            kept_ids.add(source.id)
            
    numbers = {source.id: i + 1 for i, source in enumerate(kept)}
    
    def safe_cite(sid: str) -> str:
        if sid not in numbers:
            logger.warning(f"Citation Mapping Error: Source {sid} not found in artifact.sources. Handling safely.")
            return "?"
        return str(numbers[sid])
    for packet in artifact.packets:
        findings = [Paragraph(f"<b>{_safe_pdf_text(packet.perspective)}</b>", body)]
        for evidence_id in packet.evidence_ids[:3]:
            evidence = next(item for item in artifact.evidence if item.id == evidence_id)
            findings.append(
                Paragraph(
                    f"• {_safe_pdf_text(evidence.claim)} <font color='#007D8A'>[{safe_cite(evidence.source_id)}]</font>",
                    body,
                )
            )
        if len(findings) == 1:
            findings.append(Paragraph("No verified evidence was found for this perspective.", body))
        story.append(KeepTogether(findings))
    story += [Paragraph("Conflicting evidence", heading)]
    if artifact.contradictions:
        story += [
            Paragraph(
                f"• <b>{_safe_pdf_text(item.explanation)}:</b><br/>"
                f"<i>Claim A:</i> {_safe_pdf_text(item.claim_a)} <font color='#007D8A'>[{safe_cite(item.source_a)}]</font><br/>"
                f"<i>vs</i><br/>"
                f"<i>Claim B:</i> {_safe_pdf_text(item.claim_b)} <font color='#007D8A'>[{safe_cite(item.source_b)}]</font>",
                body
            )
            for item in artifact.contradictions
        ]
    else:
        story.append(Paragraph("No direct factual contradiction was detected.", body))
    story += [Paragraph("Research gaps & uncertainty", heading)]
    story += [
        Paragraph(f"• <b>{_safe_pdf_text(gap.question)}</b><br/>{_safe_pdf_text(gap.reason)}", body)
        for gap in artifact.gaps
    ] or [Paragraph("No automated gaps were identified; this does not prove completeness.", body)]
    
    if artifact.conclusion:
        story += [Paragraph("Conclusion", heading)]
        story += [Paragraph(_safe_pdf_text(artifact.conclusion), body)]

    story += [Paragraph("Sources", heading)]
    story += [
        Paragraph(
            f"<font color='#007D8A'>[{i}]</font> {_safe_pdf_text(source.title)}<br/><font size='8'>{source.url}</font>",
            body,
        )
        for i, source in enumerate(kept, 1)
    ]
    document = SimpleDocTemplate(
        str(target), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=45
    )
    document.build(story)
