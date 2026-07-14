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
