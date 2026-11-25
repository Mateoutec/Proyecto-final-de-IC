export type EventType = "ENTRADA" | "SALIDA";
export type Method = "ROSTRO" | "HUELLA" | "HUELLA+ROSTRO" | "CODIGO+ROSTRO" | "MANUAL";

export type KioskState =
  | "waiting"
  | "detecting"
  | "challenge"
  | "need_code"
  | "success"
  | "already_registered"
  | "not_recognized"
  | "liveness_failed"
  | "no_enrolled"
  | "error"
  | "cancelled";

export interface PersonPublic {
  id: number;
  code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  area: string | null;
  position: string | null;
}

export interface SessionView {
  id: string;
  state: KioskState;
  terminal: boolean;
  title: string;
  hint: string;
  quality: string | null;
  face_box: [number, number, number, number] | null;
  mode: "identify" | "verify";
  method: Method;
  progress: number;
  challenge: {
    direction: "left" | "right";
    text: string;
    remaining_seconds: number;
    timeout_seconds: number;
    progress: number;
  } | null;
  candidate: { first_name: string; code: string } | null;
  fingerprint: { status: string; score: number | null; level: string } | null;
  result: {
    event_id?: number;
    event_type?: EventType;
    local_date?: string;
    local_time?: string;
    person?: PersonPublic;
    method?: Method;
    face_score?: number | null;
    face_threshold?: number | null;
    fingerprint_score?: number | null;
    liveness?: string;
    photo?: string | null;
    worked_hours?: number | null;
    worked_hhmm?: string | null;
    last_type?: EventType;
    seconds_ago?: number;
    message?: string;
    reason?: string;
    summary?: PersonalSummary | null;
  } | null;
}

/** Resumen que ve el Usuario en el kiosco tras identificarse. */
export interface PersonalSummary {
  week_from: string;
  week_days: number;
  week_hours: number;
  week_hhmm: string;
  week_incomplete: number;
  recent: { day: string; time: string; type: EventType; method: Method }[];
}

export interface EngineStatus {
  requested: string | null;
  active: string | null;
  description: string | null;
  embedding_dim: number | null;
  fallback: boolean;
  fallback_reason: string | null;
  error: string | null;
  ready: boolean;
  enrolled_people: number;
  templates_loaded: number;
}

export interface KioskStatus {
  engine: EngineStatus;
  enrolled_people: number;
  liveness_enabled: boolean;
  liveness_timeout_seconds: number;
  fallback_mode: "face" | "code_plus_face";
  fingerprint: { provider: string; connected: boolean; label: string; simulated: boolean; scan_enabled: boolean };
  timezone: string;
}

export interface Area {
  id: number;
  name: string;
  description: string | null;
  people_count: number | null;
}

export interface Person {
  id: number;
  code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  area_id: number | null;
  area: string | null;
  position: string | null;
  email: string | null;
  active: boolean;
  consent_signed: boolean;
  consent_date: string | null;
  fingerprint_slot: number | null;
  templates: Record<string, number>;
  templates_active: number;
  enrolled: boolean;
  needs_reindex: boolean;
  is_demo: boolean;
  last_event?: { event_type: EventType; local: string } | null;
}

export interface FaceTemplate {
  id: number;
  engine: string;
  pose: string;
  pose_label: string;
  quality: number;
  photo_path: string;
  photo_url: string;
  created_at: string;
  active_engine: boolean;
}

export interface PersonDetail extends Person {
  face_templates: FaceTemplate[];
  fingerprint_backup: number;
  events_count: number;
  poses: { key: string; label: string; frontal: boolean }[];
}

export interface AttendanceEvent {
  id: number;
  person_id: number;
  person_code: string;
  person_name: string;
  area: string | null;
  local: string;
  local_date: string;
  local_time: string;
  event_type: EventType;
  method: Method;
  face_score: number | null;
  face_threshold: number | null;
  face_margin: number | null;
  fingerprint_score: number | null;
  liveness: string;
  liveness_challenge: string | null;
  engine: string | null;
  photo_url: string | null;
  manual_reason: string | null;
  voided: boolean;
  void_reason: string | null;
  created_by: string;
}

export interface EventBrief {
  id: number;
  local_date: string;
  local_time: string;
  method: Method;
  photo_url: string | null;
}

export interface Shift {
  person_id: number;
  person_code: string;
  person_name: string;
  area: string | null;
  work_date: string;
  entry: EventBrief | null;
  exit: EventBrief | null;
  hours: number | null;
  hhmm: string | null;
  status: "COMPLETA" | "INCOMPLETA" | "EN_CURSO";
  crosses_midnight: boolean;
}

export interface PersonTotals {
  person_id: number;
  person_code: string;
  person_name: string;
  area: string | null;
  days: number;
  hours: number;
  hhmm: string;
  incomplete: number;
  open: number;
}

export interface Summary {
  date: string;
  counts: {
    present: number;
    entries: number;
    exits: number;
    incomplete_today: number;
    incomplete_week: number;
    active_people: number;
    enrolled_people: number;
    hours_today: number;
    hhmm_today: string;
  };
  present: {
    person_id: number;
    person_code: string;
    person_name: string;
    area: string | null;
    since: string;
    since_date: string;
    elapsed_hhmm: string;
  }[];
  by_area: { area: string; present: number; entries: number; exits: number }[];
  recent: AttendanceEvent[];
  engine: EngineStatus;
}

export interface RuntimeValues {
  face_engine: "insightface" | "sface" | "fake";
  threshold_insightface: number;
  threshold_sface: number;
  threshold_fake: number;
  identify_margin: number;
  debounce_seconds: number;
  max_shift_hours: number;
  liveness_enabled: boolean;
  liveness_timeout_seconds: number;
  liveness_yaw_threshold: number;
  fallback_mode: "face" | "code_plus_face";
  save_failed_attempts: boolean;
  csv_delimiter: string;
  min_sharpness: number;
  max_frontal_yaw: number;
}

export interface FingerprintStatus {
  provider: string;
  connected: boolean;
  configured?: boolean;
  label: string;
  detail?: string;
  experimental?: boolean;
  port?: string;
  baudrate?: number;
}

export interface SettingsPayload {
  values: RuntimeValues;
  labels: Record<string, string>;
  engine: EngineStatus;
  engines: { name: string; label: string; models: boolean }[];
  fingerprint: FingerprintStatus;
  undecryptable_templates: number;
  env: Record<string, string | number>;
}

export interface CalibrationResult {
  engine: string;
  people: number;
  templates: number;
  genuine_pairs: number;
  impostor_pairs: number;
  genuine_mean: number | null;
  impostor_mean: number | null;
  current_threshold: number;
  current_far: number;
  current_frr: number;
  suggested_threshold: number;
  suggested_far: number;
  suggested_frr: number;
  eer: number;
  eer_threshold: number;
  max_impostor: number | null;
  min_genuine: number | null;
  created_at: string;
  note: string;
  urls: { csv: string; scores: string; chart: string };
}

export interface AuditItem {
  id: number;
  local: string;
  actor: string;
  action: string;
  action_label: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
}
