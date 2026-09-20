/** Typed client for the platform API. */

const BASE = import.meta.env.DEV ? "http://localhost:8770" : "";

export type Severity = "error" | "warning";

export interface Finding {
  severity: Severity;
  code: string;
  message: string;
  scope: string;
}

export interface ValidationResult {
  ok: boolean;
  error_count: number;
  warning_count: number;
  findings: Finding[];
  engine?: string;
  open_assumptions?: { scope: string; origin: string; detail: string }[];
}

export interface ProfileNote {
  column?: string;
  kind: string;
  severity: "high" | "info";
  message: string;
  applied?: boolean;
  agreement?: number;
  match_count?: number;
  eligible_rows?: number;
  exceptions?: number;
}

export interface ProfileReport {
  rows: number;
  columns: number;
  sha256: string;
  notes: ProfileNote[];
  quality: { kind: string; severity: string; message: string }[];
  role_summary: Record<string, number>;
}

export interface Preview {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
  dtypes: Record<string, string>;
}

export interface UploadResult {
  upload_id: string;
  filename: string;
  profile: ProfileReport;
  proposed_table: SpecTable;
  preview: Preview;
}

export interface SpecColumn {
  name: string;
  type: string;
  role: string;
  description?: string;
  nullable?: boolean;
  null_fraction?: number;
  minimum?: number | null;
  maximum?: number | null;
  allowed_values?: unknown[] | null;
  constant_value?: unknown;
  formula?: unknown;
  rule?: unknown;
  sensitive?: boolean;
  provenance?: { origin: string; detail: string; confirmed: boolean };
}

export interface SpecConstraint {
  operator: string;
  columns: string[];
  description?: string;
  minimum?: number | null;
  maximum?: number | null;
  values?: unknown[];
}

export interface SpecTable {
  name: string;
  rows?: number | null;
  primary_key?: string | null;
  unique_keys?: string[][];
  columns: SpecColumn[];
  constraints: SpecConstraint[];
  source: { kind: string; reference?: string | null };
}

export interface Spec {
  spec_version: string;
  name: string;
  mode: string;
  purpose: string;
  description?: string;
  engine?: string | null;
  seed: number;
  tables: SpecTable[];
  relationships: Relationship[];
  privacy: {
    protected_entity?: string | null;
    mechanism: string;
    epsilon?: number | null;
    release_claim_permitted: boolean;
    notes?: string;
  };
  evaluation: { checks: string[]; target?: string | null; task?: string | null; split?: string; split_column?: string | null };
}

export interface Relationship {
  parent_table: string;
  parent_key: string;
  child_table: string;
  child_key: string;
  cardinality: string;
  optional?: boolean;
  null_fraction?: number;
  child_count_min?: number | null;
  child_count_max?: number | null;
}

export interface SuggestionColumn {
  name: string;
  type: string;
  role: string;
  description?: string;
}

export interface FixSuggestion {
  column: string;
  kind: string;
  title: string;
  rationale: string;
  adds: SuggestionColumn[];
  replaces_role: string | null;
  confirmed: boolean;
  origin: string;
}

export interface Engine {
  name: string;
  label: string;
  description: string;
  single_table: boolean;
  multi_table: boolean;
  learns_from_records: boolean;
  schema_only: boolean;
  privacy_mechanism: string;
  baseline?: boolean;
}

export interface ConstraintResult {
  operator: string;
  columns: string[];
  passed: boolean;
  failing_rows: number;
  detail: string;
  description?: string;
}

export interface TableReport {
  table: string;
  requested_rows: number;
  generated_rows: number;
  complete: boolean;
  elapsed_seconds: number;
  engine_settings: Record<string, unknown>;
  warnings: string[];
  repairs: {
    by_column: Record<string, number>;
    repaired_row_fraction: number;
    raw_invalid_row_fraction: number;
    note: string;
  };
  derived_columns: { column: string; depends_on: string[]; computed_rows: number; note: string }[];
  column_roles: Record<string, string[]>;
  constraints: ConstraintResult[];
  constraints_passed: boolean;
}

export interface EvidenceReport {
  generated_utc: string;
  platform_version: string;
  specification: { name: string; mode: string; purpose: string; seed: number };
  engine: { selected: string; capabilities: Engine; note: string };
  environment: Record<string, string>;
  summary: {
    tables: number;
    total_rows: number;
    all_constraints_passed: boolean;
    incomplete_tables: string[];
    open_assumptions: number;
    elapsed_seconds: number;
  };
  tables: TableReport[];
  evaluation: {
    checks?: Record<string, {status: string; reason?: string}>;
    relationship_checks?: {relationship: string; passed: boolean; invalid_keys: number; parents_outside_bounds: number}[];
    split?: {strategy: string; train_rows: number; test_rows: number; note: string};
    fidelity?: {
      numeric_ks: Record<string, number>;
      categorical_tv: Record<string, number>;
      mean_numeric_ks: number | null;
      mean_categorical_tv: number | null;
      numeric_correlation_mae: number | null;
      exact_row_match_fraction: number;
      interpretation: string;
    };
    predictive_utility?: {
      error?: string;
      target: string;
      task: string;
      metric: string;
      better: string;
      test_rows: number;
      trained_on_synthetic: Record<string, number>;
      trained_on_real: Record<string, number>;
      trained_on_independent_baseline: Record<string, number>;
      interpretation: string;
    };
    referential_integrity?: {
      relationship: string;
      child_rows: number;
      null_keys: number;
      orphan_rows: number;
      integrity: number;
    }[];
    cardinality?: { relationship: string; synthetic: Record<string, number>; real?: Record<string, number> }[];
  };
  validation: { findings: Finding[]; warnings: Finding[] };
  assumptions: { scope: string; origin: string; detail: string }[];
  privacy: {
    mechanism: string;
    protected_entity: string | null;
    release_claim_permitted: boolean;
    statement: string;
  };
  reproduction: { seed: number; note: string };
}

export interface Job {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "rejected";
  spec_name: string;
  created_utc: string;
  progress: string;
  error?: string;
  findings?: Finding[];
  traceback?: string;
  report?: EvidenceReport;
  previews?: Record<string, Preview>;
  tables?: string[];
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status line */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  assistantConfig: () => fetch(`${BASE}/api/assistant/config`).then(json<{configured:boolean;model:string;data_policy:string}>),
  propose: (prompt:string) => fetch(`${BASE}/api/assistant`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})}).then(json<{spec:Spec;notice:string}>),
  health: () => fetch(`${BASE}/api/health`).then(json<{ status: string; version: string }>),

  engines: () => fetch(`${BASE}/api/engines`).then(json<{ engines: Engine[] }>),

  examples: () =>
    fetch(`${BASE}/api/examples`).then(
      json<{ examples: { id: string; name: string; mode: string; purpose: string; description: string; spec: Spec }[] }>,
    ),

  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return fetch(`${BASE}/api/upload`, { method: "POST", body }).then(json<UploadResult>);
  },

  reprofile: (uploadId: string, tzOffsetHours: number) =>
    fetch(`${BASE}/api/reprofile/${uploadId}?tz_offset_hours=${tzOffsetHours}`, { method: "POST" }).then(
      json<{ profile: ProfileReport; proposed_table: SpecTable; tz_offset_hours: number }>,
    ),

  suggest: (spec: Spec, uploadId?: string, tzOffsetHours = 0) =>
    fetch(`${BASE}/api/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, upload_id: uploadId, tz_offset_hours: tzOffsetHours }),
    }).then(json<{ engine: string; suggestions: FixSuggestion[] }>),

  applySuggestions: (spec: Spec, accept: string[], uploadId?: string, tzOffsetHours = 0) =>
    fetch(`${BASE}/api/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, upload_id: uploadId, tz_offset_hours: tzOffsetHours, accept }),
    }).then(json<{ engine: string; applied: string[]; spec: Spec; validation: ValidationResult }>),

  validate: (spec: Spec) =>
    fetch(`${BASE}/api/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec }),
    }).then(json<ValidationResult>),

  generate: (spec: Spec, rows?: number, uploadId?: string) =>
    fetch(`${BASE}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, rows, upload_id: uploadId }),
    }).then(json<{ job_id: string; status: string }>),

  job: (id: string) => fetch(`${BASE}/api/jobs/${id}`).then(json<Job>),

  downloadUrl: (jobId: string, table: string) => `${BASE}/api/jobs/${jobId}/download/${table}`,
  reportUrl: (jobId: string) => `${BASE}/api/jobs/${jobId}/report`,
  specUrl: (jobId: string) => `${BASE}/api/jobs/${jobId}/specification`,
};
