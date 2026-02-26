export interface AppConfig {
  llm_available: boolean;
  llm_model: string;
  smtp_configured: boolean;
}

export interface ReviewListItem {
  id: number;
  contract_name: string;
  date: string;
  reviewer: string;
  status: string;
  analysis_mode: string;
}

export interface TriggeredRule {
  rule_id: string;
  source: string;
  clause: string;
  subclause?: string;
  risk: string;
}

export interface Flag {
  flag_id: string;
  input_clause_id: string;
  input_clause_section: string;
  input_text: string;
  matched_playbook_id: string | null;
  matched_playbook_text: string | null;
  similarity_score: number | null;
  match_type: string;
  triggered_rules: TriggeredRule[];
  classification: string;
  risk_level: string;
  explanation: string;
  suggested_redline: string;
  confidence: number;
  start_index: number;
  end_index: number;
  raw_text: string;
}

export interface ReviewSummary {
  total_clauses_analyzed: number;
  classification_breakdown: Record<string, number>;
  risk_breakdown: Record<string, number>;
  high_risk_count: number;
  non_compliant_count: number;
  top_risks: Record<string, unknown>[];
}

export interface ReviewMetadata {
  input_source: string;
  contract_name?: string;
  model?: string;
  elapsed_seconds?: number;
  [key: string]: unknown;
}

export interface ReviewDetail {
  id: number;
  contract_name: string;
  date: string;
  reviewer: string;
  status: string;
  analysis_mode: string;
  summary: ReviewSummary;
  metadata: ReviewMetadata;
  flags: Flag[];
}

export interface FlagAction {
  id: number;
  review_id: number;
  flag_id: string;
  classification: string;
  risk_level: string;
  confidence: number;
  reviewer_action: string;
  reviewer_note: string;
  reviewer_name: string;
  action_timestamp: string | null;
}

export interface ReviewStats {
  total_reviews: number;
  avg_flags_per_contract: number;
  common_deviations: Record<string, number>;
}

export interface RuleEffectiveness {
  rule_id: string;
  source: string;
  clause: string;
  triggered: number;
  accepted: number;
  rejected: number;
  false_positive_rate: number;
}

export interface TeamEmails {
  [team: string]: string;
}

export interface AcceptResponse {
  flag_id: string;
  status: string;
  messages: string[];
  errors: string[];
}

export interface SSEProgress {
  type: "progress";
  step: number;
  total: number;
  message: string;
}

export interface SSEComplete {
  type: "complete";
  data: {
    review_id: number;
    summary: ReviewSummary;
    metadata: ReviewMetadata;
    flags: Flag[];
  };
}

export interface SSEError {
  type: "error";
  message: string;
  traceback?: string;
}

export type SSEEvent = SSEProgress | SSEComplete | SSEError;
