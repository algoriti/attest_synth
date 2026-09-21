import { Component, useCallback, useEffect, useMemo, useRef, useState, type ErrorInfo, type ReactNode } from "react";
import {
  api,
  type AssistantReview,
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
import { SpecEditor, blankSpec } from "./SpecEditor";

type Step = "start" | "review" | "generate" | "report";

class ScreenErrorBoundary extends Component<{children:ReactNode},{error:string}> {
  state={error:''};
  static getDerivedStateFromError(error:unknown){return {error:String(error)};}
  componentDidCatch(error:unknown,info:ErrorInfo){console.error('Screen render failed',error,info.componentStack);}
  render(){
    if(this.state.error)return <main id="main-content" className="error-recovery" tabIndex={-1}><Notice tone="critical" title="This screen could not be displayed"><p>Your dataset job is still available on the server. Reload the workspace to fetch the screen again.</p><p className="small mono">{this.state.error}</p><button className="primary" onClick={()=>window.location.reload()}>Reload workspace</button></Notice></main>;
    return this.props.children;
  }
}

const STEPS: { id: Step; label: string }[] = [
  { id: "start", label: "Start" },
  { id: "review", label: "Design" },
  { id: "generate", label: "Generate" },
  { id: "report", label: "Evidence" },
];

export default function App() {
  return <ScreenErrorBoundary><Workspace /></ScreenErrorBoundary>;
}

function Workspace() {
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
  const [assistantReview, setAssistantReview] = useState<AssistantReview | null>(null);
  const [unsaved, setUnsaved] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    mainRef.current?.focus();
    window.scrollTo(0, 0);
  }, [step]);

  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

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
    setAssistantReview(null);
    setUnsaved(false);
    setStep("start");
  }, []);

  const goReview = useCallback(
    async (next: Spec, upload?: string, review?: AssistantReview) => {
      setUploadId(upload);
      setAssistantReview(review ?? null);
      setError(null);
      try {
        const result = await api.validate(next);
        if (!result.spec) throw new Error(result.findings.map(f=>f.message).join(' '));
        setSpec(result.spec);
        setValidation(result);
        setStep("review");
      } catch (exc) {
        setError(String(exc));
      }
    },
    [],
  );

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">a</span>
          <span>Attest <span className="brand-light">Synth</span><span className="brand-caption">Attest Synth workspace</span></span>
        </div>
        <span className="spacer" />
        <nav className="steps" aria-label="Dataset workflow">
          {STEPS.map((entry, index) => (
            <button
              key={entry.id}
              className="step"
              data-active={entry.id === step}
              data-done={index < stepIndex}
              aria-current={entry.id === step ? "step" : undefined}
              aria-label={`Step ${index + 1}: ${entry.label}`}
              disabled={index > stepIndex || (entry.id === 'generate' && step === 'report')}
              onClick={() => {
                if (entry.id === step) return;
                if (unsaved && !window.confirm('Leave the editor and discard unapplied changes?')) return;
                setUnsaved(false);setError(null);setStep(entry.id);
              }}
            >
              <span className="step-num">{index < stepIndex ? "✓" : index + 1}</span>
              <span>{entry.label}</span>
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <button className="ghost theme-toggle" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
          <span aria-hidden="true">{theme === "light" ? "◐" : "☀"}</span><span>{theme === "light" ? "Dark" : "Light"}</span>
        </button>
      </header>

      <main id="main-content" ref={mainRef} tabIndex={-1}>
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
              const result = await api.validate(next);
              if (result.spec) setSpec(result.spec);
              setValidation(result);
            }}
            onGenerate={(jobId) => {
              setJob({ id: jobId, status: "queued", spec_name: spec.name, created_utc: "", progress: "queued" });
              setStep("generate");
            }}
            uploadId={uploadId}
            onError={setError}
            onDirty={setUnsaved}
            assistantReview={assistantReview}
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
        {step === "report" && job && !job.report && (
          <Notice tone="critical" title="The completed result could not be loaded">
            The job finished, but its report data is missing. Return to the job screen to fetch it again.
            <button style={{ marginLeft: 10 }} onClick={()=>setStep("generate")}>Reload result</button>
          </Notice>
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
  onReady: (spec: Spec, uploadId?: string, review?: AssistantReview) => void;
  onProfile: (profile: ProfileReport | null, preview: Preview | null) => void;
  onError: (message: string) => void;
}) {
  const [examples, setExamples] = useState<{ id: string; name: string; description: string; mode: string; spec: Spec }[]>([]);
  const [busy, setBusy] = useState(false);
  const [assistantReady,setAssistantReady]=useState(false);
  const [prompt,setPrompt]=useState('');
  const [proposing,setProposing]=useState(false);
  const [assistantError,setAssistantError]=useState('');
  useEffect(()=>{api.assistantConfig().then(c=>setAssistantReady(c.configured)).catch(()=>setAssistantReady(false));},[]);
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
      <div className="page-head start-head">
        <div className="eyebrow">Your next dataset starts here</div>
        <h1>Create a dataset</h1>
        <p>Build the records you need, then see the evidence behind them. Start with your own design or learn from approved data.</p>
      </div>

      <div className="grid grid-2 source-paths">
        <Card title="Start with your design" sub="No source data needed" className="design-path">
          <div className="path-symbol" aria-hidden="true">＋</div>
          <p>Choose your columns, define values and connect tables. The guided editor walks you through each choice.</p>
          <button className="primary" onClick={()=>{onProfile(null,null);onReady(blankSpec());}}>Create your own dataset <span aria-hidden="true">↗</span></button>
          <p className="path-note">Generated values follow your assumptions. They do not establish facts about a real population.</p>
          <details className="import-details">
            <summary>Already have a specification?</summary>
            <label className="import-button">Import specification JSON<input aria-label="Import specification JSON" type="file" accept=".json" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;try{const spec=JSON.parse(await file.text());const result=await api.validate(spec);if(!result.ok)throw new Error(result.findings.map(f=>f.message).join(' '));onProfile(null,null);onReady(spec);}catch(exc){onError(String(exc));}e.target.value='';}}/></label>
          </details>
        </Card>
        <Card title="Learn from existing data" sub="Upload an approved CSV or TSV" className="upload-path">
          <button
            className="dropzone"
            disabled={busy}
            aria-label="Upload a CSV or TSV"
            aria-busy={busy}
            data-over={dragging}
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); const file=e.dataTransfer.files?.[0]; if(file&&!busy)void handleFile(file); }}
          >
            <span className="upload-symbol" aria-hidden="true">↑</span>
            <strong>{busy ? 'Reading your data…' : 'Drop a file here, or browse'}</strong>
            <span className="small secondary">{busy ? 'Checking columns and suggesting a starting design.' : 'CSV or TSV · up to 20 MB'}</span>
            {busy && <Spinner />}
          </button>
          <input ref={fileInput} type="file" accept=".csv,.tsv,.txt" hidden onChange={(e)=>{const file=e.target.files?.[0];if(file)void handleFile(file);e.target.value='';}}/>
          <p className="path-note">Review suggested columns and rules before generating. Use only authorised data; learned output has no privacy guarantee.</p>
        </Card>
      </div>

      <section className="template-section" aria-labelledby="templates-heading">
        <div className="section-heading"><div><div className="eyebrow">A starting point, ready to edit</div><h2 id="templates-heading">Explore a template</h2></div><span className="small secondary">Different domains. The same workflow.</span></div>
        <div className="template-grid">
          {examples.map((example) => (
            <button key={example.id} className="example-card" data-example={example.id} onClick={()=>{onProfile(null,null);onReady(example.spec);}}>
              <span className="template-kind">{example.mode==='relational_rules'?'Linked tables':'Single table'}<span aria-hidden="true">↗</span></span>
              <span className="name">{({education_relational:'Students & courses',employee_relational:'People & attendance',retail_orders:'Retail orders',retail_relational:'Customers & purchases',sensor_readings:'Sensor readings'} as Record<string,string>)[example.id]??example.name.replace(/_/g,' ')}</span>
              <span className="desc">{example.description}</span>
              <span className="template-meta">{example.spec.tables.length} {example.spec.tables.length===1?'table':'tables'} · {example.spec.tables.reduce((n,t)=>n+t.columns.length,0)} columns</span>
            </button>
          ))}
          {examples.length===0&&<p className="small secondary">Templates are unavailable. You can still create your own dataset.</p>}
        </div>
      </section>

      <Card title="Turn an idea into a starting design" sub="Optional AI assistant · you review every proposal" className="assistant-card">
        <div className="assistant-layout">
          <div><p>Describe the records and relationships you need in your own words.</p><p className="small secondary">Only your description and the specification format go to the hosted provider. Uploaded records stay out of the request. Do not include personal records.</p><Badge tone={assistantReady?'good':'neutral'}>{assistantReady?'Assistant connected':'Assistant not configured'}</Badge></div>
          <div className="stack">
            <label className="stack" htmlFor="scenario">Your scenario<textarea id="scenario" rows={4} maxLength={4000} value={prompt} onChange={e=>{setPrompt(e.target.value);setAssistantError('');}} placeholder="For example: 30 customers, each with 1 to 4 orders. Calculate each order total from quantity and price." aria-describedby="scenario-help"/></label>
            {assistantError&&<Notice tone="critical" title="The assistant could not build this proposal">{assistantError}</Notice>}
            <div className="assistant-actions"><span id="scenario-help" className="small secondary">{proposing?'Preparing and validating a proposal. One correction may be attempted.':!assistantReady?'Use the guided editor or templates while the assistant is unavailable.':prompt.trim().length<10?'Describe your idea in at least 10 characters.':`${prompt.length.toLocaleString()} / 4,000 characters`}</span><button className="primary" disabled={!assistantReady||proposing||prompt.trim().length<10} onClick={async()=>{setProposing(true);setAssistantError('');try{const result=await api.propose(prompt);onProfile(null,null);onReady(result.spec,undefined,result.review);}catch(exc){setAssistantError(String(exc).replace(/^Error:\s*/,''));}finally{setProposing(false);}}}>{proposing?<><Spinner /> Preparing proposal…</>:'Propose a dataset'}</button></div>
          </div>
        </div>
      </Card>
      <details className="engine-details">
        <summary>Under the hood <span className="small secondary">Explore generation engines and their limits</span></summary>
        <Card title="Available engines" sub="Choose an engine when reviewing your dataset.">
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Engine comparison">
            <table><thead><tr><th>Engine</th><th>What it does</th><th>Source records</th><th>Linked tables</th><th>Privacy mechanism</th></tr></thead>
              <tbody>{engines.map(engine=><tr key={engine.name}><td><strong>{engine.label}</strong>{engine.baseline&&<Badge tone="neutral">Baseline</Badge>}</td><td className="secondary">{engine.description}</td><td>{engine.learns_from_records?'Required':'Not needed'}</td><td>{engine.multi_table?'Supported':'No'}</td><td>{engine.privacy_mechanism==='none'?'None':engine.privacy_mechanism}</td></tr>)}</tbody>
            </table>
          </div>
        </Card>
      </details>
      <footer className="workspace-footer"><span>Attest Synth</span><span>Define your data. Inspect its evidence.</span></footer>
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
  onDirty,
  assistantReview,
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
  onDirty: (dirty: boolean) => void;
  assistantReview: AssistantReview | null;
}) {
  const specifiedRows = spec.tables[0]?.rows ?? 1000;
  const [rows, setRows] = useState<number>(specifiedRows);
  useEffect(()=>setRows(specifiedRows),[specifiedRows]);
  const [starting, setStarting] = useState(false);
  const [editorDirty,setEditorDirty]=useState(false);
  const [showEditor,setShowEditor]=useState(false);
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
    if (!window.confirm("Changing timezone reprofiles the upload and replaces column edits and rule decisions. Continue?")) return;
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
  const blocked = !validation?.ok || errors.length > 0 || editorDirty;

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
    (spec.tables.length>1 || spec.relationships.length ? engine.multi_table : engine.single_table) && (spec.mode==='learned_table'?engine.learns_from_records:engine.schema_only),
  );

  // A derived column is predictable from its own formula, so it measures the formula
  // rather than the synthesis. It stays selectable but is labelled as such.
  const utilityTargets = (spec.tables[0]?.columns ?? []).filter(
    (column) => !["identifier", "foreign_key", "empty", "constant", "derived"].includes(column.role) && !["date","timestamp"].includes(column.type),
  );

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Step 02 · Design & review</div>
        <h1>Review your dataset</h1>
        <p>
          <strong>{spec.name}</strong> · Check the columns, rules and relationships. You can change the design before generating.
        </p>
      </div>

      <div className="review-overview">
        <div className="review-counts"><span><strong>{spec.tables.length}</strong> {spec.tables.length===1?'table':'tables'}</span><span><strong>{spec.tables.reduce((n,t)=>n+t.columns.length,0)}</strong> {spec.tables.reduce((n,t)=>n+t.columns.length,0)===1?'column':'columns'}</span><span><strong>{spec.relationships.length}</strong> relationships</span></div>
        <Badge tone={editorDirty?'warning':validation?.ok?'good':'critical'}>{editorDirty?'Unapplied edits':validation?.ok?'Ready to generate':'Needs attention'}</Badge>
      </div>
      {assistantReview&&(
        <Card title="Assistant reconciliation" sub="What the platform preserved, corrected or could not represent">
          {assistantReview.explicit_row_requirements.map(requirement=><Notice key={requirement.table} tone="good" title={`${requirement.requested_rows.toLocaleString()} ${requirement.table}`}>
            Preserved from your prompt{requirement.changed&&requirement.assistant_rows!==null?`; the assistant initially proposed ${requirement.assistant_rows.toLocaleString()}`:''}.
          </Notice>)}
          {assistantReview.unsupported_requests.map((message,index)=><Notice key={index} tone="warning" title="Requested calculation is outside the current engine">{message}</Notice>)}
          {assistantReview.omitted_tables.length>0&&<p className="small secondary">Omitted rather than fabricated: <code>{assistantReview.omitted_tables.join(', ')}</code>.</p>}
          {(assistantReview.automatic_reconciliations?.length??0)>0&&<details><summary>Platform reconciliation ({assistantReview.automatic_reconciliations.length})</summary><ul>{assistantReview.automatic_reconciliations.map((message,index)=><li key={index}>{message}</li>)}</ul></details>}
          {assistantReview.correction_attempted&&<p className="small secondary">The first model response failed platform checks. One bounded correction was applied and this is the validated proposal.</p>}
        </Card>
      )}
      <div className="review-toolbar"><button onClick={()=>setShowEditor(!showEditor)} aria-expanded={showEditor} aria-controls="dataset-editor">{showEditor?'Hide dataset editor':'Edit tables, columns and relationships'}</button><a className="button-link" href="#generation-settings">Go to generation settings <span aria-hidden="true">↓</span></a></div>
      <div id="dataset-editor" hidden={!showEditor}><SpecEditor key={JSON.stringify(spec)} spec={spec} onApply={onValidate} onDirty={dirty=>{setEditorDirty(dirty);onDirty(dirty);}}/></div>
      {derivedNotes.length > 0 ? (
        <Card
          title="Possible rules to review"
          sub="Proposed as computed columns"
          actions={
            uploadId ? (
              <label className="row" style={{ gap: 7 }}>
                <span className="small secondary">Site timezone</span>
                <select
                  value={tzOffset}
                  disabled={reprofiling || editorDirty}
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
          <Notice tone="accent" title="Statistical matches need your decision">
            Left as ordinary columns, a generator reproduces their frequency while contradicting the
            columns they are computed from — a six-hour shift stamped with nine hours of overtime.
            Accept a formula only when it represents the scenario or policy you intend. Its exceptions may be meaningful.
          </Notice>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Rule</th>
                  <th className="num">Match</th><th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {derivedNotes.map((note, index) => (
                  <tr key={index}>
                    <td className="mono">{note.column}</td>
                    <td className="small secondary">{note.message.split(" (")[0]}</td>
                    <td className="num">
                      <Badge tone={(note.agreement ?? 0) >= 0.99 ? "good" : "warning"}>
                        {((note.agreement ?? 0) * 100).toFixed(1)}%{note.eligible_rows!==undefined?` (${note.match_count}/${note.eligible_rows})`:""}
                      </Badge>
                    </td>
                    <td><div className="row"><button disabled={editorDirty} onClick={()=>{const next=structuredClone(spec);const c=next.tables[0].columns.find(c=>c.name===note.column);if(c){c.provenance={origin:'user',detail:'Accepted as a scenario rule by the user',confirmed:true};void onValidate(next);}}}>Accept rule</button><button disabled={editorDirty} onClick={()=>{const next=structuredClone(spec);const c=next.tables[0].columns.find(c=>c.name===note.column);if(c){c.role='learned';delete c.formula;c.provenance={origin:'profiled',detail:'Candidate formula rejected; learn observed values',confirmed:false};void onValidate(next);}}}>Learn instead</button></div><span className="small">{spec.tables[0].columns.find(c=>c.name===note.column)?.role==='learned'?'Rejected':spec.tables[0].columns.find(c=>c.name===note.column)?.provenance?.confirmed?'Accepted':'Unconfirmed'}</span></td>
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
            <button className="primary" disabled={applying || editorDirty} onClick={() => void applyFixes()}>
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

      {errors.length > 0 ? (
        <Card title="A few details need attention" sub={`${errors.length} ${errors.length===1?'issue':'issues'} to resolve`}>
          <Notice tone="critical">
            Fix these details in the editor before generating. Your design remains available to edit.
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
              <h3 style={{ marginBottom: 8 }}>Hard rules</h3>
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
        <Card title="Relationships" sub="Keys and child counts are checked after generation">
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
                      {rel.child_count_min ?? 0}–{rel.child_count_max ?? "not specified"}
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

      <Card title="Generation settings" sub="Choose the output size and how it should be created." id="generation-settings" className="generation-settings">
        <fieldset className="generation-controls" disabled={editorDirty}>
        <legend className="sr-only">Generation options</legend>
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
                    ...spec.evaluation,
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

        {spec.evaluation.target&&<div className="grid grid-2 editor-fields">
          <label>How should real test records be held out?<select value={spec.evaluation.split??'random'} onChange={e=>void onValidate({...spec,evaluation:{...spec.evaluation,split:e.target.value}})}><option value="random">Random records</option><option value="group">Entire entities (such as employees)</option><option value="time">Latest records</option></select></label>
          {spec.evaluation.split&&spec.evaluation.split!=='random'&&<label>Split column<select value={spec.evaluation.split_column??''} onChange={e=>void onValidate({...spec,evaluation:{...spec.evaluation,split_column:e.target.value}})}><option value="">Choose a column</option>{spec.tables[0].columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>}
        </div>}
        </fieldset>
        <div className="generation-actions">
          <button className="primary" disabled={blocked || starting} onClick={start}>
            {starting ? "Starting…" : "Generate dataset"}
          </button>
          {blocked ? <span className="small secondary">{editorDirty?'Apply or discard your editor changes first.':'Resolve the validation issues above first.'}</span> : null}
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
  foreign_key: "Assigned from a declared parent relationship",
  learned: "A generator may model this column",
  rule: "Sampled from a declared rule",
  derived: "Computed from other columns after generation",
  constant: "One value throughout",
  empty: "No observed values; emitted as null",
};

/* --------------------------------------------------------------- generate */

// Matches each engine's own capabilities().label so the generating screen never
// invents a name the engine did not declare.
const ENGINE_LABELS: Record<string, string> = {
  rules: "Rules + Faker",
  relational_rules: "Relational (parent-first rules)",
  arf: "Adversarial Random Forest",
  independent: "Independent columns (baseline)",
};

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

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
  const [pollError,setPollError]=useState('');
  const [retry,setRetry]=useState(0);
  const [elapsedMs,setElapsedMs]=useState(0);
  const doneRef=useRef(onDone);
  useEffect(() => { doneRef.current = onDone; }, [onDone]);

  useEffect(() => {
    let failures=0;const started=Date.now();setPollError('');setElapsedMs(0);
    let cancelled = false;
    // A visible, ticking clock is what tells a person a slow job is still alive
    // rather than frozen — a bare spinner looks identical whether it has been
    // running for two seconds or two minutes.
    const clock = window.setInterval(() => { if (!cancelled) setElapsedMs(Date.now() - started); }, 1000);
    const tick = async () => {
      try {
        const next = await api.job(jobId);
        if (cancelled) return;
        failures = 0;
        setPollError('');
        setJob(next);
        if (next.status === "completed" || next.status === "failed" || next.status === "rejected") {
          doneRef.current(next);
          return;
        }
      } catch {
        // A slow-but-succeeding job and a genuinely lost connection need different
        // responses, so they are not collapsed into one error path: this counts
        // only real fetch failures, five in a row, before saying the connection
        // itself is the problem.
        failures++; if(failures>=5){setPollError("Connection lost. Your job may still be running in the background. Reconnect to check its status.");return;}
      }
      // No time-based cutoff here. The adversarial random forest genuinely takes
      // minutes on tables with tens of thousands of rows — measured up to several
      // minutes when its internal retry ladder needs more than one attempt — so a
      // fixed timeout on an otherwise healthy, still-succeeding poll was reporting
      // a hang that was not actually happening. Polling continues for as long as
      // the server keeps answering; only real connection loss stops it.
      if (!cancelled) window.setTimeout(tick, 700);
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(clock);
    };
  }, [jobId, retry]);

  const status = job?.status ?? "queued";
  const active = status === "queued" || status === "running";
  const slow = active && elapsedMs > 45000;

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Step 03 · Create your records</div><h1>Generating your dataset</h1>
        <p>
          Generation runs as a background job. Learned engines take tens of seconds on a few
          thousand rows, and several minutes on tens of thousands.
        </p>
      </div>

      {pollError&&<Notice tone="warning" title="Status unavailable">{pollError}<button onClick={()=>setRetry(n=>n+1)}>Reconnect</button></Notice>}
      <Card>
        <div className="row" style={{ gap: 12 }}>
          {active ? <Spinner /> : null}
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>
              {status === "running" ? job?.progress ?? "working" : status}
            </div>
            <div className="small muted mono">job {jobId}</div>
            {(job?.engine || job?.requested_rows) ? (
              <div className="small muted">
                {job?.engine ? ENGINE_LABELS[job.engine] ?? job.engine : "engine"}
                {job?.requested_rows ? ` · ${job.requested_rows.toLocaleString()} rows requested` : ""}
              </div>
            ) : null}
          </div>
          {active ? (
            <div className="small muted mono" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              {formatElapsed(elapsedMs)} elapsed
            </div>
          ) : null}
        </div>

        {slow ? (
          <Notice tone="accent" title="Still working">
            This is expected for a learned engine on a table this size — it has not stalled.
            Polling continues in the background regardless of how long generation takes; the
            elapsed time above is the only thing to watch.
          </Notice>
        ) : null}

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
