import type { Report } from "../api/client";
import { CLAIM_TYPE_LABEL, FIELD_LABEL, VERIFICATION_LABEL, date, fieldValue, metricValue } from "./format";

export function reportToMarkdown(report: Report): string {
  const number = new Map(report.claims.map((c, i) => [c.id, i + 1]));
  const cite = (ids: string[]) => (ids.length ? ` [${ids.map((id) => number.get(id)).filter(Boolean).join(", ")}]` : "");
  const lines: string[] = [];
  lines.push(`# ${report.job.company} (${report.company.ticker})`, "", `**${report.headline}**`, "");
  lines.push(`> Question: ${report.job.query}`, "");
  lines.push(`Data as of ${date(report.data_as_of)} · Generated ${date(report.generated_at)} · ${report.verification_summary.supported} of ${report.verification_summary.total} claims supported`, "");
  lines.push("## Answer", "", report.direct_answer, "");
  lines.push("## Executive summary", "", report.executive_summary, "");
  for (const point of report.key_points) lines.push(`- ${point.text}${cite(point.claim_ids)}`);
  if (report.investment_thesis) lines.push("", "## Investment thesis", "", report.investment_thesis);
  lines.push("", "## Scenarios", "");
  for (const s of report.scenarios) {
    lines.push(`### ${s.name[0]!.toUpperCase()}${s.name.slice(1)}`, "", s.summary, "");
    for (const a of s.assumptions) lines.push(`- **${a.driver}**: ${a.assumption}${a.basis ? ` _(basis: ${a.basis})_` : ""}`);
    lines.push("");
  }
  lines.push("## Risks", "");
  for (const r of report.risks) lines.push(`- **${r.title}** (${r.severity}): ${r.description}${cite(r.claim_ids)}`);
  lines.push("", "## Financials (USD)", "");
  const periods = report.financials.map((f) => f.period);
  lines.push(`| Item | ${periods.join(" | ")} |`, `| --- | ${periods.map(() => "---:").join(" | ")} |`);
  for (const field of Object.keys(FIELD_LABEL)) {
    lines.push(`| ${FIELD_LABEL[field]} | ${report.financials.map((f) => fieldValue(field, f.values[field]?.value ?? null)).join(" | ")} |`);
  }
  lines.push("", "## Evidence ledger", "");
  report.claims.forEach((claim, i) => {
    lines.push(`${i + 1}. ${claim.text} — _${CLAIM_TYPE_LABEL[claim.claim_type]}, ${VERIFICATION_LABEL[claim.verification_status]}_`);
    for (const m of claim.metrics) lines.push(`   - ${m.label} ${m.period} = ${metricValue(m.value, m.unit)} (${m.formula})`);
    for (const e of claim.evidence) lines.push(`   - "${e.quote}" — ${e.document.form} filed ${e.document.filed}, ${e.document.url}`);
  });
  lines.push("", "## Limitations", "", ...report.limitations.map((l) => `- ${l}`));
  lines.push("", "## Sources", "", ...report.filings.map((f) => `- ${f.title} (${f.accession}), filed ${f.filed}: ${f.url}`));
  lines.push("", `_${report.disclaimer}_`, "");
  return lines.join("\n");
}

export function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
