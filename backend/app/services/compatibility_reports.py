"""Bounded, self-contained downloads from historical snapshots, never live targets."""

import html
import json
from fastapi import HTTPException
from app.core.redaction import Redactor
from app.schemas.compatibility import FindingPage, RunOut
from app.services import compatibility_service as service

MAX_REPORT_FINDINGS = 500
MAX_REPORT_BYTES = 2_000_000
LIMITATIONS = [
    "This assessment covers only the recorded requests and saved replay responses, under the displayed policy and comparison rules.",
    "Unexecuted endpoints and unrecorded inputs were not tested. This is not a universal compatibility guarantee.",
    "Confirmed breaking means a supplied contract was violated; it does not prove a particular consumer failed. A pre-existing violation is identified separately.",
    "Potentially breaking findings are risk indicators, not confirmed consumer failures. Informational additions can still affect strict consumers without a supplied contract.",
    "Unassessed, missing, redacted, ignored, omitted or bounded evidence prevents a complete conclusion. Severity is rule-based impact; confidence is evidence strength, not probability.",
    "Additional-field prohibition compares object properties to this recorded baseline; it is not a complete JSON Schema. Dynamic paths permit values only, not removal or type changes.",
    "Policy and engine snapshots are immutable. Reanalysis with changed policies creates or reuses a distinct historical result. No AI model is used.",
]


def report_data(db, row):
    data = RunOut.model_validate(service.run_view(db, row)).model_dump(mode="json")
    # These flags are live UI conveniences, not part of a reproducible historical report.
    data.pop("is_current")
    for analysis in data["analyses"]:
        analysis.pop("is_current")
    findings = FindingPage.model_validate(
        service.findings_page(
            db, [i.analysis_id for i in row.items], MAX_REPORT_FINDINGS, 0
        )
    ).model_dump(mode="json")
    data.update(
        report_format_version="1",
        methodology=LIMITATIONS,
        findings=findings["items"],
        included_findings=len(findings["items"]),
        omitted_findings=findings["total"] - len(findings["items"]),
    )
    return Redactor().clean(data)


def render_report(db, row, format):
    data = report_data(db, row)
    encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if len(encoded.encode()) > MAX_REPORT_BYTES:
        raise HTTPException(
            413,
            "Report exceeds the 2 MB export limit. Use paginated finding endpoints or a smaller replay session.",
        )
    if format == "json":
        return encoded, "application/json"
    def e(value):
        return html.escape(str(value), quote=True)

    meta = data["metadata_snapshot"]
    summary = "".join(
        f"<tr><th>{e(k.replace('_', ' '))}</th><td>{v}</td></tr>"
        for k, v in data["summary"].items()
    )
    cards = []
    for f in data["findings"]:
        evidence = f["evidence"]
        cards.append(
            f"<article><h3>{e(f['title'])}</h3><p><strong>{e(f['request_method'])} {e(f['endpoint_path'])}</strong> · {e(f['path'] or '(root)')}</p>"
            f"<p>{e(f['classification'])} · Severity: {e(f['severity'] or 'not rated')} · Confidence: {e(f['confidence'])}</p>"
            f"<p>{e(f['explanation'])}</p><p><strong>Action:</strong> {e(f['recommended_action'])}</p>"
            f'<div class="values"><section><h4>Recorded</h4><pre>{e(evidence.get("old_preview", "Not available"))}</pre></section><section><h4>Replayed</h4><pre>{e(evidence.get("new_preview", "Not available"))}</pre></section></div>'
            f"<p>Rule: {e(f['rule_id'])} · Comparison: {e(f['comparison_id'])} · Difference: {e(f['difference_id'] or 'Contract / coverage check')}</p>"
            f"<details><summary>Evidence and requirement</summary><pre>{e(json.dumps(evidence, ensure_ascii=False, indent=2))}</pre></details></article>"
        )
    policies = "".join(
        f"<details><summary>{e(a['request_method'])} {e(a['endpoint_path'])}</summary><pre>{e(json.dumps({'policy': a['effective_policy'], 'comparison_rules': a['effective_comparison_rules'], 'policy_hash': a['policy_hash'], 'comparison_algorithm': a['comparison_algorithm_version']}, ensure_ascii=False, indent=2))}</pre></details>"
        for a in data["analyses"]
    )
    content = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>API TimeMachine compatibility report</title><style>body{{font:15px/1.6 system-ui,sans-serif;color:#172321;background:#f4f6f2;margin:0}}main{{max-width:1050px;margin:auto;padding:40px 24px}}h1{{font-size:36px;line-height:1.15}}article,details,table{{background:white;border:1px solid #cad4ca;border-radius:8px;padding:20px;margin:18px 0}}th,td{{text-align:left;padding:6px 20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 monospace}}.values{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.verdict{{font-size:22px;font-weight:700}}@media(max-width:600px){{.values{{grid-template-columns:1fr}}}}@media print{{article{{break-inside:avoid}}}}</style></head><body><main><p>API TIMEMACHINE / COMPATIBILITY</p><h1>{e(meta["project_name"])}</h1><p class="verdict">{e(data["verdict"].replace("_", " "))}</p><p>Session: {e(meta["session_name"])} · {e(data["replay_session_id"])}<br>Analysis: {e(data["id"])}<br>Analyzed: {e(data["analyzed_at"])} · Engine: {e(data["engine_version"])}<br>Source: {e(", ".join(meta["source_base_urls"]))}<br>Target: {e(meta["target_base_url"])}</p><h2>Executive summary</h2><table>{summary}</table><p>Missing comparison result IDs: {e(", ".join(data["missing_result_ids"]) or "None")}</p><h2>Scope and methodology</h2><ul>{"".join("<li>" + e(x) + "</li>" for x in LIMITATIONS)}</ul><h2>Findings</h2><p>Included: {data["included_findings"]}; omitted by export limit: {data["omitted_findings"]}. Summary counts cover all retained findings. Paginated APIs contain the full saved set.</p>{"".join(cards) or "<p>No findings in the assessed comparisons. Review coverage counts above.</p>"}<h2>Frozen policies and comparison rules</h2>{policies}</main></body></html>"""
    if len(content.encode()) > MAX_REPORT_BYTES * 2:
        raise HTTPException(
            413,
            "HTML report exceeds the 4 MB limit. Download JSON or use paginated findings.",
        )
    return content, "text/html"
