import type {
  DifyAgentItem,
  ChatMode,
  DraftProposal,
  DraftSelection,
  FlowInfo,
  MessageItem,
  SessionDetail,
  SessionListItem,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8010";

type ApiEnvelope<T> = {
  code?: number;
  message?: string;
  data: T;
};

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function getFlows(): Promise<FlowInfo[]> {
  const payload = await readJson<ApiEnvelope<FlowInfo[]>>(`${API_BASE}/api/flows`);
  return payload.data || [];
}

export async function getSessions(): Promise<SessionListItem[]> {
  const payload = await readJson<ApiEnvelope<SessionListItem[]>>(`${API_BASE}/api/sessions`);
  return payload.data || [];
}

export async function createSession(topic: string, flowName: string): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, flow_name: flowName }),
  });
  return payload.data;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions/${sessionId}`);
  return payload.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function getMessages(sessionId: string): Promise<MessageItem[]> {
  const payload = await readJson<ApiEnvelope<MessageItem[]>>(`${API_BASE}/api/sessions/${sessionId}/messages`);
  return payload.data || [];
}

export async function selectFlow(sessionId: string, flowName: string): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions/${sessionId}/select_flow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flow_name: flowName, clear_messages: true }),
  });
  return payload.data;
}

export async function getDifyAgents(sessionId: string): Promise<DifyAgentItem[]> {
  const payload = await readJson<ApiEnvelope<DifyAgentItem[]>>(`${API_BASE}/api/sessions/${sessionId}/dify_agents`);
  return payload.data || [];
}

export async function getChatMode(): Promise<ChatMode> {
  const payload = await readJson<ApiEnvelope<{ chat_mode: ChatMode }>>(`${API_BASE}/api/settings/chat-mode`);
  return payload.data?.chat_mode || "main";
}

export async function setChatMode(chatMode: ChatMode): Promise<ChatMode> {
  const payload = await readJson<ApiEnvelope<{ chat_mode: ChatMode }>>(`${API_BASE}/api/settings/chat-mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_mode: chatMode }),
  });
  return payload.data?.chat_mode || "main";
}

export async function setDraftMode(sessionId: string, enabled: boolean): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions/${sessionId}/draft-mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return payload.data;
}

export async function getDraftProposal(sessionId: string, stageId: string): Promise<DraftProposal | null> {
  const payload = await readJson<ApiEnvelope<DraftProposal | null>>(
    `${API_BASE}/api/sessions/${sessionId}/draft-proposal?stage_id=${encodeURIComponent(stageId)}`,
  );
  return payload.data || null;
}

export async function applyDraftProposalActions(
  sessionId: string,
  proposalId: string,
  actions: { hunk_id: string; action: "accept" | "reject" }[],
): Promise<DraftProposal> {
  const payload = await readJson<ApiEnvelope<DraftProposal>>(
    `${API_BASE}/api/sessions/${sessionId}/draft-proposals/${proposalId}/actions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actions }),
    },
  );
  return payload.data;
}

export async function saveDraft(sessionId: string, stageId: string, draftContent: string): Promise<void> {
  await readJson(`${API_BASE}/api/sessions/${sessionId}/stages/${stageId}/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft_content: draftContent }),
  });
}

export async function rollbackSession(
  sessionId: string,
  payload: { steps: number; stage_back: boolean },
): Promise<SessionDetail> {
  const response = await readJson<ApiEnvelope<{ session: SessionDetail }>>(
    `${API_BASE}/api/sessions/${sessionId}/rollback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return response.data.session;
}

export async function exportSession(sessionId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/export`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.blob();
}

type StreamHandlers = {
  stage?: (data: any) => void | Promise<void>;
  agent?: (data: any) => void | Promise<void>;
  delta?: (data: any) => void | Promise<void>;
  draft?: (data: any) => void | Promise<void>;
  proposal?: (data: any) => void | Promise<void>;
  status?: (data: any) => void | Promise<void>;
  warning?: (data: any) => void | Promise<void>;
  done?: (data: any) => void | Promise<void>;
};

export type StreamChatPayload = {
  type: "chat" | "sys_action";
  message?: string;
  action?: "next_stage" | "prev_stage" | "intro" | "confirm_stage";
  final_content?: string;
  draft_request_kind?: "generate" | "edit";
  selection?: DraftSelection | null;
};

export async function streamChat(
  sessionId: string,
  payload: StreamChatPayload,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatch = async (eventName: string, rawData: string) => {
    if (!rawData) {
      return;
    }
    try {
      const data = JSON.parse(rawData);
      await handlers[eventName as keyof StreamHandlers]?.(data);
    } catch {
      await handlers[eventName as keyof StreamHandlers]?.({ text: rawData });
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const splitIndex = buffer.indexOf("\n\n");
      if (splitIndex < 0) {
        break;
      }

      const chunk = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);
      const lines = chunk.split(/\r?\n/);
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      await dispatch(eventName, dataLines.join("\n"));
    }
  }
}

export function buildFileDownloadUrl(sessionName: string): string {
  return `${API_BASE}/api/sessions/${encodeURIComponent(sessionName)}/export`;
}
