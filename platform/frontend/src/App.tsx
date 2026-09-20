import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Engine,
  type EvidenceReport,
  type Job,
  type Preview,
  type ProfileReport,
  type FixSuggestion,
  type Spec,
  type SpecTable,
  type UploadResult,
  type ValidationResult,
} from "./api";
import { Badge, Card, DataPreview, FindingList, Notice, RoleChip, Spinner } from "./components";
import { ReportView } from "./ReportView";
import "./theme.css";

type Step = "start" | "review" | "generate" | "report";

const STEPS: { id: Step; label: string }[] = [
  { id: "start", label: "Source" },
  { id: "review", label: "Specification" },
  { id: "generate", label: "Generate" },
  { id: "report", label: "Evidence" },
];

export default function App() {
  const [step, setStep] = useState<Step>("start");
  const [engines, setEngines] = useState<Engine[]>([]);
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("theme") as "light" | "dark") ?? "light",
  );

  const [spec, setSpec] = useState<Spec | null>(null);
  const [uploadId, setUploadId] = useState<string | undefined>();
  const [profile, setProfile] = useState<ProfileReport | null>(null);
  const [sourcePreview, setSourcePreview] = useState<Preview | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    api.engines().then((r) => setEngines(r.engines)).catch(() => setEngines([]));
  }, []);

  const reset = useCallback(() => {
    setSpec(null);
    setUploadId(undefined);
    setProfile(null);
    setSourcePreview(null);
    setValidation(null);
    setJob(null);
    setError(null);
    setStep("start");
  }, []);

  const goReview = useCallback(
    async (next: Spec, upload?: string) => {
      setSpec(next);
      setUploadId(upload);
      setError(null);
      setStep("review");
      try {
        setValidation(await api.validate(next));
      } catch (exc) {
        setError(String(exc));
      }
    },
    [],
  );

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <span>Synthetic Data Platform</span>
        </div>
        <span className="spacer" />
        <nav className="steps">
          {STEPS.map((entry, index) => (
            <button
              key={entry.id}
              className="step"
              data-active={entry.id === step}
              data-done={index < stepIndex}
              disabled={index > stepIndex}
              onClick={() => index <= stepIndex && setStep(entry.id)}
            >
              <span className="step-num">{index < stepIndex ? "✓" : index + 1}</span>
              <span>{entry.label}</span>
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <button className="ghost" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
          {theme === "light" ? "Dark" : "Light"}
        </button>
      </header>

      <main>
        {error ? (
          <Notice tone="critical" title="Something went wrong">
            {error}
          </Notice>
        ) : null}

        {step === "start" && <StartView engines={engines} onReady={goReview} onError={setError} onProfile={(p, prev) => { setProfile(p); setSourcePreview(prev); }} />}

        {step === "review" && spec && (
          <ReviewView
            spec={spec}
            setSpec={setSpec}
            profile={profile}
            setProfile={setProfile}
            sourcePreview={sourcePreview}
            validation={validation}
            engines={engines}
            onValidate={async (next) => {
              setSpec(next);
              setValidation(await api.validate(next));
            }}
            onGenerate={(jobId) => {
              setJob({ id: jobId, status: "queued", spec_name: spec.name, created_utc: "", progress: "queued" });
              setStep("generate");
            }}
            uploadId={uploadId}
            onError={setError}
          />
        )}

        {step === "generate" && job && (
          <GenerateView
            jobId={job.id}
            onDone={(finished) => {
              setJob(finished);
              if (finished.status === "completed") setStep("report");
            }}
            onBack={() => setStep("review")}
          />
        )}

        {step === "report" && job?.report && (
          <ReportView
            report={job.report as EvidenceReport}
            previews={job.previews ?? {}}
            jobId={job.id}
            onRestart={reset}
          />
        )}
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ start */

function StartView({
  engines,
  onReady,
  onProfile,
  onError,
}: {
  engines: Engine[];
  onReady: (spec: Spec, uploadId?: string) => void;
  onProfile: (profile: ProfileReport | null, preview: Preview | null) => void;
  onError: (message: string) => void;
}) {
  const [examples, setExamples] = useState<{ id: string; name: string; description: string; mode: string; spec: Spec }[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.examples().then((r) => setExamples(r.examples)).catch(() => setExamples([]));
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setBusy(true);
      try {
        const result: UploadResult = await api.upload(file);
        onProfile(result.profile, result.preview);
        const table: SpecTable = result.proposed_table;
        const hasLearnable = table.columns.some((c) => c.role === "learned");
        const spec: Spec = {
          spec_version: "2.0",
          name: table.name,
          mode: hasLearnable ? "learned_table" : "schema_rules",
          purpose: "ml_development",
          description: `Learned from ${result.filename}`,
          engine: hasLearnable ? "arf" : "rules",
          seed: 2026,
          tables: [table],
          relationships: [],
          privacy: {
            protected_entity: null,
            mechanism: "none",
            release_claim_permitted: false,
            notes: "Learned from uploaded records. No privacy mechanism applied.",
          },
          evaluation: { checks: ["schema", "constraints", "fidelity"] },
        };
        onReady(spec, result.upload_id);
      } catch (exc) {
        onError(String(exc));
      } finally {
        setBusy(false);
      }
    },
    [onReady, onProfile, onError],
  );

  return (
    <>
      <div className="page-head">
        <h1>Create a dataset</h1>
        <p>
          Upload an approved CSV to learn from, or start from a schema and generate without any
          source records at all. Either path produces the same kind of specification.
        </p>
      </div>

      <div className="grid grid-2">
        <Card title="Learn from approved records" sub="Upload a CSV">
          <div
            className="dropzone"
            data-over={dragging}
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const file = e.dataTransfer.files?.[0];
              if (file) void handleFile(file);
            }}
          >
            {busy ? (
              <div className="row" style={{ justifyContent: "center" }}>
                <Spinner />
                <span className="secondary">Profiling…</span>
              </div>
            ) : (
              <>
                <div style={{ fontSize: 22, marginBottom: 6 }}>↑</div>
                <div style={{ fontWeight: 600 }}>Drop a CSV here or click to browse</div>
                <div className="small muted" style={{ marginTop: 4 }}>
                  The profiler proposes column roles, finds business rules and flags data quality
                  problems. Nothing is applied until you confirm it.
                </div>
              </>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.tsv,.txt"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          <Notice tone="warning" title="Upload only data you are authorised to use">
            Learned output is not anonymised. Records stay on this machine, but the platform applies
            no privacy mechanism to what it generates from them.
          </Notice>
        </Card>

        <Card title="Start from a schema" sub="No source records needed">
          <p className="small secondary">
            Every distribution is one you declare, so there is no disclosure risk — and equally, a
            model trained on the result has learned your assumptions rather than a fact about any
            population.
          </p>
          <div className="grid" style={{ gap: 10 }}>
            {examples.map((example) => (
              <button
                key={example.id}
                className="example-card"
                onClick={() => {
                  onProfile(null, null);
                  onReady(example.spec);
                }}
              >
                <div className="row" style={{ gap: 8 }}>
                  <span className="name">{example.name}</span>
                  <Badge tone={example.mode === "relational_rules" ? "accent" : "neutral"}>
                    {example.mode.replace(/_/g, " ")}
                  </Badge>
                </div>
                <span className="desc">{example.description}</span>
              </button>
            ))}
            {examples.length === 0 ? <p className="small muted">No examples available.</p> : null}
          </div>
        </Card>
      </div>

      <Card title="Registered engines" sub="Capabilities are declared, not assumed">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Engine</th>
                <th>Role</th>
                <th>Source records</th>
                <th>Multi-table</th>
                <th>Privacy</th>
              </tr>
            </thead>
            <tbody>
              {engines.map((engine) => (
                <tr key={engine.name}>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <strong>{engine.label}</strong>
                      {engine.baseline ? <Badge tone="warning">baseline</Badge> : null}
                    </div>
                    <div className="small muted mono">{engine.name}</div>
                  </td>
                  <td className="small secondary">{engine.description}</td>
                  <td>{engine.learns_from_records ? "required" : "not needed"}</td>
                  <td>{engine.multi_table ? "yes" : "no"}</td>
                  <td>
                    <Badge tone="critical">{engine.privacy_mechanism}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

/* ----------------------------------------------------------------- review */

function ReviewView({
  spec,
  setSpec,
  profile,
  setProfile,
  sourcePreview,
  validation,
  engines,
  onValidate,
  onGenerate,
  uploadId,
  onError,
}: {
  spec: Spec;
  setSpec: (spec: Spec) => void;
  profile: ProfileReport | null;
  setProfile: (profile: ProfileReport | null) => void;
  sourcePreview: Preview | null;
  validation: ValidationResult | null;
  engines: Engine[];
  onValidate: (spec: Spec) => Promise<void>;
  onGenerate: (jobId: string) => void;
  uploadId?: string;
  onError: (message: string) => void;
}) {
  const [rows, setRows] = useState<number>(spec.tables[0]?.rows ?? 1000);
  const [starting, setStarting] = useState(false);
  const [tzOffset, setTzOffset] = useState(0);
  const [reprofiling, setReprofiling] = useState(false);
  const [fixes, setFixes] = useState<FixSuggestion[]>([]);
  const [applying, setApplying] = useState(false);

  const blockedColumns = (validation?.findings ?? []).filter(
    (f) => f.code === "unsupported_column_type",
  );

  useEffect(() => {
    if (blockedColumns.length === 0) {
      setFixes([]);
      return;
    }
    let cancelled = false;
    api
      .suggest(spec, uploadId, tzOffset)
      .then((r) => !cancelled && setFixes(r.suggestions))
      .catch(() => !cancelled && setFixes([]));
    return () => {
      cancelled = true;
    };
  }, [blockedColumns.length, spec, uploadId, tzOffset]);

  const applyFixes = async () => {
    setApplying(true);
    try {
      const result = await api.applySuggestions(
        spec,
        fixes.map((f) => f.column),
        uploadId,
        tzOffset,
      );
      setSpec(result.spec);
      await onValidate(result.spec);
      setFixes([]);
    } catch (exc) {
      onError(String(exc));
    } finally {
      setApplying(false);
    }
  };

  // Threshold rules are only discoverable against the clock the policy is written in:
  // the same attendance cutoff reads as 07:45 at UTC+3 and 04:45 at UTC.
  const reprofile = async (offset: number) => {
    if (!uploadId) return;
    setTzOffset(offset);
    setReprofiling(true);
    try {
      const result = await api.reprofile(uploadId, offset);
      setProfile(result.profile);
      const next: Spec = { ...spec, tables: [result.proposed_table, ...spec.tables.slice(1)] };
      setSpec(next);
      await onValidate(next);
    } catch (exc) {
      onError(String(exc));
    } finally {
      setReprofiling(false);
    }
  };

  const derivedNotes = useMemo(
    () => (profile?.notes ?? []).filter((n) => n.kind === "derived_candidate" && n.applied),
    [profile],
  );
  const qualityNotes = profile?.quality ?? [];
  const errors = validation?.findings.filter((f) => f.severity === "error") ?? [];
  const warnings = validation?.findings.filter((f) => f.severity === "warning") ?? [];
  const blocked = errors.length > 0;

  const setEngine = (engine: string) => {
    const next = { ...spec, engine };
    setSpec(next);
    void onValidate(next);
  };

  const start = async () => {
    setStarting(true);
    try {
      const { job_id } = await api.generate(spec, spec.relationships.length ? undefined : rows, uploadId);
      onGenerate(job_id);
    } catch (exc) {
      onError(String(exc));
    } finally {
      setStarting(false);
    }
  };

  const usable = engines.filter((engine) =>
    spec.relationships.length ? engine.multi_table : true,
  );

  // A derived column is predictable from its own formula, so it measures the formula
  // rather than the synthesis. It stays selectable but is labelled as such.
  const utilityTargets = (spec.tables[0]?.columns ?? []).filter(
    (column) => !["identifier", "empty", "constant"].includes(column.role),
  );

  return (
    <>
      <div className="page-head">
        <h1>{spec.name}</h1>
        <p>
          Review what the platform intends to do before anything is generated. Column roles decide
          what a generator is even allowed to model.
        </p>
      </div>

      {derivedNotes.length > 0 ? (
        <Card
          title="Business rules found in your data"
          sub="Proposed as computed columns"
          actions={
            uploadId ? (
              <label className="row" style={{ gap: 7 }}>
                <span className="small secondary">Site timezone</span>
                <select
                  value={tzOffset}
                  disabled={reprofiling}
                  onChange={(e) => void reprofile(Number(e.target.value))}
                >
                  {TIMEZONE_OFFSETS.map((offset) => (
                    <option key={offset} value={offset}>
                      {offset === 0 ? "UTC" : `UTC${offset > 0 ? "+" : ""}${offset}`}
                    </option>
                  ))}
                </select>
                {reprofiling ? <Spinner /> : null}
              </label>
            ) : undefined
          }
        >
          <Notice tone="accent" title="These columns are formulas, not behaviour">
            Left as ordinary columns, a generator reproduces their frequency while contradicting the
            columns they are computed from — a six-hour shift stamped with nine hours of overtime.
            Marked as derived, they are calculated after generation and cannot disagree.
          </Notice>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Rule</th>
                  <th className="num">Match</th>
                </tr>
              </thead>
              <tbody>
                {derivedNotes.map((note, index) => (
                  <tr key={index}>
                    <td className="mono">{note.column}</td>
                    <td className="small secondary">{note.message.split(" (")[0]}</td>
                    <td className="num">
                      <Badge tone={(note.agreement ?? 0) >= 0.99 ? "good" : "warning"}>
                        {((note.agreement ?? 0) * 100).toFixed(1)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {qualityNotes.length > 0 ? (
        <Card title="Data quality" sub={`${qualityNotes.length} issues in the source`}>
          {qualityNotes.slice(0, 4).map((note, index) => (
            <Notice key={index} tone={note.severity === "high" ? "warning" : "neutral"}>
              {note.message}
            </Notice>
          ))}
        </Card>
      ) : null}

      {fixes.length > 0 ? (
        <Card
          title="Suggested fix"
          sub={`${fixes.length} column${fixes.length > 1 ? "s" : ""} this engine cannot model`}
          actions={
            <button className="primary" disabled={applying} onClick={() => void applyFixes()}>
              {applying ? "Applying…" : "Apply suggested fix"}
            </button>
          }
        >
          <Notice tone="warning" title="A default, not a finding">
            Nothing in your data says these are the right features to keep — they are a
            sensible default this tool chose. Applying them records each new column as an
            unconfirmed assumption in the evidence report.
          </Notice>
          <div className="stack" style={{ gap: 12 }}>
            {fixes.map((fix) => (
              <div key={fix.column}>
                <div className="row" style={{ gap: 8, marginBottom: 4 }}>
                  <strong className="mono">{fix.column}</strong>
                  <Badge tone="accent">{fix.kind.replace(/_/g, " ")}</Badge>
                </div>
                <p className="small secondary" style={{ marginBottom: 6 }}>
                  {fix.rationale}
                </p>
                <div className="row small" style={{ gap: 6 }}>
                  <span className="muted">adds</span>
                  {fix.adds.map((added) => (
                    <span key={added.name} className="row" style={{ gap: 4 }}>
                      <code>{added.name}</code>
                      <RoleChip role={added.role} />
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {blocked ? (
        <Card title="The specification was rejected" sub={`${errors.length} errors`}>
          <Notice tone="critical">
            Generation cannot start until these are resolved. The validator runs before any engine
            does, so an impossible request fails clearly instead of producing plausible nonsense.
          </Notice>
          <FindingList findings={errors} />
        </Card>
      ) : null}

      {warnings.length > 0 ? (
        <Card title="Warnings" sub="Generation can proceed; these appear in the report">
          <FindingList findings={warnings} />
        </Card>
      ) : null}

      {spec.tables.map((table) => (
        <Card
          key={table.name}
          title={table.name}
          sub={`${table.columns.length} columns · ${table.constraints.length} constraints`}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Type</th>
                  <th>Role</th>
                  <th>What happens to it</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {table.columns.map((column) => (
                  <tr key={column.name}>
                    <td className="mono">
                      {column.name}
                      {column.sensitive ? (
                        <>
                          {" "}
                          <Badge tone="warning">sensitive</Badge>
                        </>
                      ) : null}
                    </td>
                    <td className="small secondary">{column.type}</td>
                    <td>
                      <RoleChip role={column.role} />
                    </td>
                    <td className="small secondary">
                      {column.description || ROLE_EXPLANATION[column.role] || "—"}
                    </td>
                    <td className="small muted">
                      {column.provenance?.origin?.replace(/_/g, " ") ?? "—"}
                      {column.provenance && !column.provenance.confirmed ? " (unconfirmed)" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {table.constraints.length > 0 ? (
            <div style={{ marginTop: 14 }}>
              <h4 style={{ marginBottom: 8 }}>Hard rules</h4>
              <div className="stack" style={{ gap: 6 }}>
                {table.constraints.map((constraint, index) => (
                  <div key={index} className="row small">
                    <Badge tone="neutral">{constraint.operator}</Badge>
                    <span className="mono muted">{constraint.columns.join(", ")}</span>
                    <span className="secondary">{constraint.description}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Card>
      ))}

      {spec.relationships.length > 0 ? (
        <Card title="Relationships" sub="Generated parent-first, so orphans are impossible">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Parent</th>
                  <th>Child</th>
                  <th>Cardinality</th>
                  <th className="num">Children per parent</th>
                </tr>
              </thead>
              <tbody>
                {spec.relationships.map((rel, index) => (
                  <tr key={index}>
                    <td className="mono small">
                      {rel.parent_table}.{rel.parent_key}
                    </td>
                    <td className="mono small">
                      {rel.child_table}.{rel.child_key}
                    </td>
                    <td className="small secondary">{rel.cardinality.replace(/_/g, " ")}</td>
                    <td className="num">
                      {rel.child_count_min ?? 1}–{rel.child_count_max ?? 5}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {sourcePreview ? (
        <Card title="Source preview" sub={`${sourcePreview.total_rows.toLocaleString()} rows uploaded`}>
          <DataPreview preview={sourcePreview} limit={6} />
        </Card>
      ) : null}

      <Card title="Generate">
        <div className="grid grid-3" style={{ marginBottom: 14 }}>
          <label className="stack" style={{ gap: 5 }}>
            <span className="stat-label">Engine</span>
            <select value={spec.engine ?? ""} onChange={(e) => setEngine(e.target.value)}>
              {usable.map((engine) => (
                <option key={engine.name} value={engine.name}>
                  {engine.label}
                </option>
              ))}
            </select>
          </label>
          {spec.relationships.length === 0 ? (
            <label className="stack" style={{ gap: 5 }}>
              <span className="stat-label">Rows</span>
              <input
                type="number"
                min={1}
                max={200000}
                value={rows}
                onChange={(e) => setRows(Number(e.target.value))}
              />
            </label>
          ) : (
            <div className="stack" style={{ gap: 5 }}>
              <span className="stat-label">Rows</span>
              <span className="small secondary">Decided by the relationship cardinality.</span>
            </div>
          )}
          <label className="stack" style={{ gap: 5 }}>
            <span className="stat-label">Seed</span>
            <input
              type="number"
              value={spec.seed}
              onChange={(e) => setSpec({ ...spec, seed: Number(e.target.value) })}
            />
          </label>
        </div>

        {spec.mode === "learned_table" ? (
          <label className="stack" style={{ gap: 5, marginBottom: 14, maxWidth: 420 }}>
            <span className="stat-label">Measure usefulness for predicting</span>
            <select
              value={spec.evaluation.target ?? ""}
              onChange={(e) => {
                const target = e.target.value || null;
                const column = spec.tables[0].columns.find((c) => c.name === target);
                const checks = new Set(spec.evaluation.checks);
                if (target) checks.add("predictive_utility");
                else checks.delete("predictive_utility");
                const next: Spec = {
                  ...spec,
                  evaluation: {
                    checks: [...checks],
                    target,
                    task: column && ["category", "boolean"].includes(column.type)
                      ? "classification"
                      : "regression",
                  },
                };
                setSpec(next);
                void onValidate(next);
              }}
            >
              <option value="">Skip the utility check</option>
              {utilityTargets.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}
                  {column.role === "derived" ? " (derived — trivially predictable)" : ""}
                </option>
              ))}
            </select>
            <span className="small muted">
              Trains a model on the synthetic data and scores it against held-out real rows,
              alongside real-data training and an independent-sampling floor.
            </span>
          </label>
        ) : null}

        <div className="row">
          <button className="primary" disabled={blocked || starting} onClick={start}>
            {starting ? "Starting…" : "Generate dataset"}
          </button>
          {blocked ? <span className="small muted">Resolve the errors above first.</span> : null}
          {validation?.open_assumptions?.length ? (
            <span className="small muted">
              {validation.open_assumptions.length} unconfirmed assumptions will be recorded in the
              report.
            </span>
          ) : null}
        </div>
      </Card>

      <details className="raw">
        <summary>View the raw specification</summary>
        <pre>{JSON.stringify(spec, null, 2)}</pre>
      </details>
    </>
  );
}

const TIMEZONE_OFFSETS = [-8, -5, -3, 0, 1, 2, 3, 4, 5.5, 7, 8, 9, 10];

const ROLE_EXPLANATION: Record<string, string> = {
  identifier: "Regenerated; never copied from the source",
  learned: "A generator may model this column",
  rule: "Sampled from a declared rule",
  derived: "Computed from other columns after generation",
  constant: "One value throughout",
  empty: "No observed values; emitted as null",
};

/* --------------------------------------------------------------- generate */

function GenerateView({
  jobId,
  onDone,
  onBack,
}: {
  jobId: string;
  onDone: (job: Job) => void;
  onBack: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await api.job(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "completed" || next.status === "failed" || next.status === "rejected") {
          onDone(next);
          return;
        }
      } catch {
        /* keep polling; the job may not be registered yet */
      }
      if (!cancelled) window.setTimeout(tick, 700);
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [jobId, onDone]);

  const status = job?.status ?? "queued";

  return (
    <>
      <div className="page-head">
        <h1>Generating</h1>
        <p>
          Generation runs as a background job. Learned engines take tens of seconds on a few
          thousand rows.
        </p>
      </div>

      <Card>
        <div className="row" style={{ gap: 12 }}>
          {status === "queued" || status === "running" ? <Spinner /> : null}
          <div>
            <div style={{ fontWeight: 600 }}>
              {status === "running" ? job?.progress ?? "working" : status}
            </div>
            <div className="small muted mono">job {jobId}</div>
          </div>
        </div>

        {status === "rejected" ? (
          <div style={{ marginTop: 16 }}>
            <Notice tone="critical" title="Rejected before generation">
              {job?.error}
            </Notice>
            {job?.findings ? <FindingList findings={job.findings} /> : null}
            <button style={{ marginTop: 10 }} onClick={onBack}>
              Back to the specification
            </button>
          </div>
        ) : null}

        {status === "failed" ? (
          <div style={{ marginTop: 16 }}>
            <Notice tone="critical" title="The engine failed">
              {job?.error}
            </Notice>
            {job?.traceback ? (
              <details className="raw">
                <summary>Traceback</summary>
                <pre>{job.traceback}</pre>
              </details>
            ) : null}
            <button style={{ marginTop: 10 }} onClick={onBack}>
              Back to the specification
            </button>
          </div>
        ) : null}
      </Card>
    </>
  );
}
