/** Shared presentational pieces. */
import type { ReactNode } from "react";
import type { Finding, Preview } from "./api";

export type Tone = "good" | "warning" | "critical" | "accent" | "neutral";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className="badge" data-tone={tone}>
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "good" | "warning" | "critical";
}) {
  return (
    <div className="stat" data-tone={tone}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note ? <div className="stat-note">{note}</div> : null}
    </div>
  );
}

export function Notice({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
}) {
  const icon = { good: "✓", warning: "!", critical: "×", accent: "i", neutral: "i" }[tone];
  return (
    <div className="notice" data-tone={tone} role={tone === "critical" ? "alert" : undefined}>
      <span className="notice-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="notice-body">
        {title ? <div className="notice-title">{title}</div> : null}
        <div className="small secondary">{children}</div>
      </div>
    </div>
  );
}

export function Card({
  title,
  sub,
  actions,
  className = "",
  id,
  children,
}: {
  title?: string;
  sub?: ReactNode;
  actions?: ReactNode;
  className?: string;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      {title ? (
        <header className="card-head">
          <div className="card-heading"><h2>{title}</h2>
          {sub ? <div className="sub">{sub}</div> : null}</div>
          <span className="spacer" />
          {actions}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function RoleChip({ role }: { role: string }) {
  return (
    <span className="role-chip" data-role={role}>
      {role}
    </span>
  );
}

export function FindingList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="stack">
      {findings.map((finding, index) => (
        <Notice
          key={`${finding.code}-${index}`}
          tone={finding.severity === "error" ? "critical" : "warning"}
          title={finding.scope ? `${finding.code} · ${finding.scope}` : finding.code}
        >
          {finding.message}
        </Notice>
      ))}
    </div>
  );
}

export function DataPreview({ preview, limit = 8 }: { preview: Preview; limit?: number }) {
  const rows = preview.rows.slice(0, limit);
  return (
    <>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Data preview; scroll horizontally for more columns">
        <table aria-label="Dataset preview">
          <thead>
            <tr>
              {preview.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {preview.columns.map((column) => (
                  <td key={column} className={typeof row[column] === "number" ? "num" : undefined}>
                    {formatCell(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        Showing {rows.length} of {preview.total_rows.toLocaleString()} rows.
      </p>
    </>
  );
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toFixed(4).replace(/\.?0+$/, "");
  }
  const text = String(value);
  return text.length > 40 ? `${text.slice(0, 37)}…` : text;
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
