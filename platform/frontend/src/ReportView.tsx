/** The evidence report.
 *
 * This screen is the reason the platform exists. A download button alone would let
 * someone ship a dataset without ever seeing that 40% of its rows were repaired, that
 * a third of its distributions were invented, or that its utility barely beats random
 * sampling. Everything that qualifies the data is shown before the download link.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type EvidenceReport, type Preview } from "./api";
import { Badge, Card, DataPreview, Notice, Stat } from "./components";
import { useChartColors } from "./useChartColors";

export function ReportView({
  report,
  previews,
  jobId,
  onRestart,
}: {
  report: EvidenceReport;
  previews: Record<string, Preview>;
  jobId: string;
  onRestart: () => void;
}) {
  const { summary, evaluation } = report;
  const warnings = report.validation.warnings ?? [];

  return (
    <>
      <div className="page-head">
        <div className="row">
          <h1>Evidence report</h1>
          <Badge tone={summary.all_constraints_passed ? "good" : "critical"}>
            {summary.all_constraints_passed ? "All constraints passed" : "Constraints failed"}
          </Badge>
        </div>
        <p>
          {report.specification.name} · generated {new Date(report.generated_utc).toLocaleString()} ·
          engine <code>{report.engine.selected}</code> · seed {report.specification.seed}
        </p>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <Stat
          label="Rows generated"
          value={summary.total_rows.toLocaleString()}
          note={
            summary.incomplete_tables.length
              ? `Incomplete: ${summary.incomplete_tables.join(", ")}`
              : "Exactly as requested"
          }
          tone={summary.incomplete_tables.length ? "critical" : undefined}
        />
        <Stat label="Tables" value={summary.tables} note={report.specification.mode.replace(/_/g, " ")} />
        <Stat
          label="Open assumptions"
          value={summary.open_assumptions}
          note={summary.open_assumptions ? "Unconfirmed claims" : "All confirmed"}
          tone={summary.open_assumptions > 0 ? "warning" : "good"}
        />
        <Stat label="Elapsed" value={`${summary.elapsed_seconds.toFixed(1)}s`} note="Generation and evaluation" />
      </div>

      <PrivacyPanel report={report} />

      {warnings.length > 0 ? (
        <Card title="Validation warnings" sub={`${warnings.length} noted, generation proceeded`}>
          {warnings.map((finding, index) => (
            <Notice key={index} tone="warning" title={finding.scope || finding.code}>
              {finding.message}
            </Notice>
          ))}
        </Card>
      ) : null}

      {report.tables.map((table) => (
        <Card
          key={table.table}
          title={table.table}
          sub={`${table.generated_rows.toLocaleString()} rows · ${table.elapsed_seconds.toFixed(2)}s`}
          actions={
            <a href={api.downloadUrl(jobId, table.table)} download>
              <button className="primary">Download CSV</button>
            </a>
          }
        >
          {!table.complete ? (
            <Notice tone="critical" title="Incomplete result">
              Requested {table.requested_rows.toLocaleString()} rows, produced{" "}
              {table.generated_rows.toLocaleString()}. Treat this as a partial result.
            </Notice>
          ) : null}

          {table.warnings.map((warning, index) => (
            <Notice key={index} tone="warning">
              {warning}
            </Notice>
          ))}

          <div className="grid grid-2">
            <div>
              <h4 style={{ marginBottom: 8 }}>Declared constraints</h4>
              {table.constraints.length === 0 ? (
                <p className="small muted">No constraints declared for this table.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 62 }}>Result</th>
                        <th>Rule</th>
                        <th className="num">Failing</th>
                      </tr>
                    </thead>
                    <tbody>
                      {table.constraints.map((constraint, index) => (
                        <tr key={index}>
                          <td>
                            <Badge tone={constraint.passed ? "good" : "critical"}>
                              {constraint.passed ? "pass" : "fail"}
                            </Badge>
                          </td>
                          <td>
                            <div>{constraint.description || constraint.operator}</div>
                            <div className="small muted mono">{constraint.detail}</div>
                          </td>
                          <td className="num">{constraint.failing_rows.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <h4 style={{ marginBottom: 8 }}>Repairs applied after generation</h4>
              <RepairPanel table={table} />
            </div>
          </div>

          {table.derived_columns.length > 0 ? (
            <div style={{ marginTop: 16 }}>
              <h4 style={{ marginBottom: 8 }}>Computed, not generated</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Column</th>
                      <th>Computed from</th>
                      <th className="num">Rows</th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.derived_columns.map((derived) => (
                      <tr key={derived.column}>
                        <td className="mono">{derived.column}</td>
                        <td className="small secondary">{derived.depends_on.join(", ")}</td>
                        <td className="num">{derived.computed_rows.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="small muted" style={{ marginTop: 8 }}>
                These columns were calculated from the specification's formulas after generation, so
                they cannot contradict the columns they depend on.
              </p>
            </div>
          ) : null}

          {previews[table.table] ? (
            <div style={{ marginTop: 16 }}>
              <h4 style={{ marginBottom: 8 }}>Preview</h4>
              <DataPreview preview={previews[table.table]} />
            </div>
          ) : null}
        </Card>
      ))}

      {evaluation.predictive_utility ? <UtilityPanel utility={evaluation.predictive_utility} /> : null}
      {evaluation.fidelity ? <FidelityPanel fidelity={evaluation.fidelity} /> : null}
      {evaluation.referential_integrity ? (
        <RelationalPanel
          integrity={evaluation.referential_integrity}
          cardinality={evaluation.cardinality ?? []}
        />
      ) : null}

      {report.assumptions.length > 0 ? (
        <Card
          title="Open assumptions"
          sub="Values nobody has confirmed against evidence"
        >
          <Notice tone="warning">
            Each row below is a claim about the world that was invented or proposed rather than
            measured. A model trained on this data learns these assumptions as if they were facts.
          </Notice>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Scope</th>
                  <th>Origin</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {report.assumptions.map((assumption, index) => (
                  <tr key={index}>
                    <td className="mono">{assumption.scope}</td>
                    <td>
                      <Badge tone={assumption.origin === "unresolved" ? "critical" : "warning"}>
                        {assumption.origin.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="small secondary">{assumption.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <Card title="Reproduction">
        <div className="grid grid-3">
          <Stat label="Seed" value={report.reproduction.seed} />
          <Stat label="Platform" value={`v${report.platform_version}`} />
          <Stat label="Python" value={report.environment.python} />
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          {report.reproduction.note}
        </p>
        <div className="row" style={{ marginTop: 14 }}>
          <a href={api.reportUrl(jobId)} download>
            <button>Download full report (JSON)</button>
          </a>
          <a href={api.specUrl(jobId)} download>
            <button>Download specification (JSON)</button>
          </a>
          <button className="ghost" onClick={onRestart}>
            Start another dataset
          </button>
        </div>
      </Card>
    </>
  );
}

function PrivacyPanel({ report }: { report: EvidenceReport }) {
  return (
    <Card title="Privacy">
      <Notice tone="critical" title="No privacy guarantee">
        {report.privacy.statement}
      </Notice>
      <div className="row small secondary">
        <span>
          Mechanism: <strong>{report.privacy.mechanism}</strong>
        </span>
        <span>
          Protected entity: <strong>{report.privacy.protected_entity ?? "not declared"}</strong>
        </span>
        <span>
          Release claim permitted: <strong>no</strong>
        </span>
      </div>
    </Card>
  );
}

function RepairPanel({ table }: { table: EvidenceReport["tables"][number] }) {
  const entries = Object.entries(table.repairs.by_column);
  const fraction = table.repairs.repaired_row_fraction;
  const tone = fraction > 0.5 ? "warning" : fraction > 0 ? "accent" : "good";

  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <Badge tone={tone}>{(fraction * 100).toFixed(1)}% of rows touched</Badge>
      </div>
      <div className="bar-track" style={{ marginBottom: 10 }}>
        <div
          className="bar-fill"
          style={{
            width: `${Math.max(fraction * 100, fraction > 0 ? 1.5 : 0)}%`,
            background: fraction > 0.5 ? "var(--warning)" : "var(--accent)",
          }}
        />
      </div>
      {entries.length === 0 ? (
        <p className="small muted">No values needed correcting.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Column</th>
                <th className="num">Values repaired</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([column, count]) => (
                <tr key={column}>
                  <td className="mono">{column}</td>
                  <td className="num">{count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted" style={{ marginTop: 8 }}>
        {table.repairs.note}
      </p>
    </>
  );
}

function UtilityPanel({
  utility,
}: {
  utility: NonNullable<EvidenceReport["evaluation"]["predictive_utility"]>;
}) {
  const c = useChartColors();
  const metric = utility.metric;
  const higherIsBetter = utility.better === "higher";

  const data = [
    { name: "Real data", value: utility.trained_on_real?.[metric], slot: 1 },
    { name: "Synthetic", value: utility.trained_on_synthetic?.[metric], slot: 2 },
    { name: "Independent baseline", value: utility.trained_on_independent_baseline?.[metric], slot: 3 },
  ].filter((row) => typeof row.value === "number") as { name: string; value: number; slot: number }[];

  const real = data.find((d) => d.slot === 1)?.value;
  const synthetic = data.find((d) => d.slot === 2)?.value;
  const baseline = data.find((d) => d.slot === 3)?.value;

  let verdict = "";
  let verdictTone: "good" | "warning" | "critical" = "good";
  if (real !== undefined && synthetic !== undefined && baseline !== undefined) {
    const span = Math.abs(real - baseline);
    const recovered = span === 0 ? 0 : Math.abs(synthetic - baseline) / span;
    const closerToReal = higherIsBetter ? synthetic > baseline : synthetic < baseline;
    if (!closerToReal || recovered < 0.15) {
      verdict =
        "Synthetic data performs no better than sampling each column independently. For this task it preserves little usable signal.";
      verdictTone = "critical";
    } else if (recovered < 0.6) {
      verdict = `Synthetic data recovers roughly ${(recovered * 100).toFixed(0)}% of the gap between the independent baseline and real data. Usable for development, not for final measurement.`;
      verdictTone = "warning";
    } else {
      verdict = `Synthetic data recovers roughly ${(recovered * 100).toFixed(0)}% of the gap between the independent baseline and real data.`;
      verdictTone = "good";
    }
  }

  const colors = [c["--series-3"], c["--series-1"], c["--series-2"]];

  return (
    <Card
      title="Predictive utility"
      sub={`target ${utility.target} · ${metric} · ${utility.better} is better · ${utility.test_rows.toLocaleString()} real test rows`}
    >
      {verdict ? <Notice tone={verdictTone}>{verdict}</Notice> : null}

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 52, bottom: 4, left: 4 }}>
            <CartesianGrid horizontal={false} stroke={c["--grid"]} />
            <XAxis
              type="number"
              stroke={c["--text-muted"]}
              fontSize={12}
              tickLine={false}
              axisLine={{ stroke: c["--border"] }}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={150}
              stroke={c["--text-secondary"]}
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: c["--surface-2"] }}
              contentStyle={{
                background: c["--surface-1"],
                border: `1px solid ${c["--border"]}`,
                borderRadius: 8,
                fontSize: 12,
                color: c["--text-primary"],
              }}
              formatter={(value) => [Number(value).toFixed(4), metric] as [string, string]}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={22} isAnimationActive={false} label={{
              position: "right",
              fill: c["--text-secondary"],
              fontSize: 12,
              formatter: (v: unknown) => Number(v).toFixed(3),
            }}>
              {data.map((row, index) => (
                <Cell key={row.name} fill={colors[index % colors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <p className="small muted">{utility.interpretation}</p>
    </Card>
  );
}

function FidelityPanel({
  fidelity,
}: {
  fidelity: NonNullable<EvidenceReport["evaluation"]["fidelity"]>;
}) {
  const c = useChartColors();
  const ks = Object.entries(fidelity.numeric_ks).map(([column, value]) => ({ column, value }));
  const tv = Object.entries(fidelity.categorical_tv).map(([column, value]) => ({ column, value }));
  const data = [...ks, ...tv].sort((a, b) => b.value - a.value).slice(0, 10);

  return (
    <Card title="Distribution fidelity" sub="lower is closer to the source">
      <Notice tone="accent" title="Fidelity is necessary, not sufficient">
        {fidelity.interpretation}
      </Notice>

      <div className="grid grid-4" style={{ marginBottom: 14 }}>
        <Stat
          label="Mean numeric KS"
          value={fidelity.mean_numeric_ks !== null ? fidelity.mean_numeric_ks.toFixed(4) : "—"}
        />
        <Stat
          label="Mean categorical TV"
          value={fidelity.mean_categorical_tv !== null ? fidelity.mean_categorical_tv.toFixed(4) : "—"}
        />
        <Stat
          label="Correlation error"
          value={
            fidelity.numeric_correlation_mae !== null ? fidelity.numeric_correlation_mae.toFixed(4) : "—"
          }
          note="Numeric pairs only"
        />
        <Stat
          label="Exact row matches"
          value={`${(fidelity.exact_row_match_fraction * 100).toFixed(2)}%`}
          note="Diagnostic, not a privacy score"
          tone={fidelity.exact_row_match_fraction > 0.01 ? "warning" : undefined}
        />
      </div>

      {data.length > 0 ? (
        <div className="chart-wrap" style={{ height: Math.max(170, data.length * 26 + 40) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 4 }}>
              <CartesianGrid horizontal={false} stroke={c["--grid"]} />
              <XAxis
                type="number"
                stroke={c["--text-muted"]}
                fontSize={12}
                tickLine={false}
                axisLine={{ stroke: c["--border"] }}
              />
              <YAxis
                type="category"
                dataKey="column"
                width={150}
                stroke={c["--text-secondary"]}
                fontSize={12}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                cursor={{ fill: c["--surface-2"] }}
                contentStyle={{
                  background: c["--surface-1"],
                  border: `1px solid ${c["--border"]}`,
                  borderRadius: 8,
                  fontSize: 12,
                  color: c["--text-primary"],
                }}
                formatter={(value) => [Number(value).toFixed(4), "distance"] as [string, string]}
              />
              <Bar dataKey="value" fill={c["--series-1"]} radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false} label={{
                position: "right",
                fill: c["--text-secondary"],
                fontSize: 11,
                formatter: (v: unknown) => Number(v).toFixed(3),
              }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </Card>
  );
}

function RelationalPanel({
  integrity,
  cardinality,
}: {
  integrity: NonNullable<EvidenceReport["evaluation"]["referential_integrity"]>;
  cardinality: NonNullable<EvidenceReport["evaluation"]["cardinality"]>;
}) {
  const allValid = integrity.every((row) => row.orphan_rows === 0);
  return (
    <Card title="Relational integrity" sub={`${integrity.length} relationships`}>
      <Notice tone={allValid ? "good" : "critical"}>
        {allValid
          ? "Every foreign key resolves to a parent that exists. Parent-first generation makes an orphan row unrepresentable rather than merely unlikely."
          : "Some child rows reference a parent that does not exist."}
      </Notice>

      <div className="table-wrap" style={{ marginBottom: 14 }}>
        <table>
          <thead>
            <tr>
              <th>Relationship</th>
              <th className="num">Child rows</th>
              <th className="num">Orphans</th>
              <th className="num">Integrity</th>
            </tr>
          </thead>
          <tbody>
            {integrity.map((row) => (
              <tr key={row.relationship}>
                <td className="mono small">{row.relationship}</td>
                <td className="num">{row.child_rows.toLocaleString()}</td>
                <td className="num">{row.orphan_rows}</td>
                <td className="num">
                  <Badge tone={row.integrity === 1 ? "good" : "critical"}>
                    {(row.integrity * 100).toFixed(1)}%
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {cardinality.length > 0 ? (
        <>
          <h4 style={{ marginBottom: 8 }}>Children per parent</h4>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Relationship</th>
                  <th className="num">Parents</th>
                  <th className="num">Min</th>
                  <th className="num">Median</th>
                  <th className="num">Max</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {cardinality.map((row) => (
                  <tr key={row.relationship}>
                    <td className="mono small">{row.relationship}</td>
                    <td className="num">{row.synthetic.parents}</td>
                    <td className="num">{row.synthetic.min}</td>
                    <td className="num">{row.synthetic.median}</td>
                    <td className="num">{row.synthetic.max}</td>
                    <td className="num">{row.synthetic.total_children?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>
            Real cardinality is usually heavily skewed. A tidy uniform spread here is a consequence of
            the declared range, not a property recovered from any source.
          </p>
        </>
      ) : null}
    </Card>
  );
}
