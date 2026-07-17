export type FlowStage = {
  id: string;
  name: string;
  expert: string;
  agent_id: string;
  direction: string;
};

export type ChatMode = "main" | "subagent";

export type FlowInfo = {
  name: string;
  display_name: string;
  description: string;
  stage_count: number;
  stages: FlowStage[];
};

export type SessionListItem = {
  id: string;
  title: string;
  topic: string;
  flow_name: string;
  flow_display_name: string;
  current_stage_index: number;
  status: string;
  draft_mode_enabled: boolean;
  updated_at: string;
  created_at: string;
};

export type StageOutput = {
  stage_id: string;
  stage_name: string;
  order_index: number;
  draft_content: string;
  final_content: string;
  confirmed: boolean;
};

export type SessionDetail = SessionListItem & {
  current_stage: FlowStage | null;
  outputs: StageOutput[];
};

export type DraftProposalSegment = {
  id: string;
  kind: "equal" | "replace" | "delete" | "insert";
  base_start: number;
  base_end: number;
  candidate_start: number;
  candidate_end: number;
  base_text: string;
  candidate_text: string;
  status: "pending" | "accepted" | "rejected";
};

export type DraftSelection = {
  selected_text: string;
  start_offset: number;
  end_offset: number;
  stage_id: string;
  block_id?: string | null;
};

export type DraftProposal = {
  id: string;
  session_id: string;
  stage_id: string;
  base_content: string;
  candidate_content: string;
  segments: DraftProposalSegment[];
  status: "pending" | "accepted" | "rejected";
  proposal_kind: "generate" | "edit";
  target_mode: "selection" | null;
  target_summary: string | null;
  target_range?: {
    start_offset: number;
    end_offset: number;
  } | null;
  highlight_segment_ids: string[];
  created_at: string;
  updated_at: string;
};

export type MessageItem = {
  id?: string;
  stage_id: string;
  role: "user" | "assistant";
  content: string;
  agent_id?: string | null;
  agent_name?: string | null;
  message_type?: string;
  created_at?: string;
};

export type DifyAgentItem = {
  id: string;
  stage_id: string;
  command: string;
  name: string;
  description: string;
  flow_names: string[];
  configured: boolean;
};
