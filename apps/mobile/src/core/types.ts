export interface Identity {
  user: { id: string; name: string; email: string };
  active_tenant_id: string;
  tenants: { id: string; name: string; role: string }[];
}
export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
  identity: Identity;
}
export interface Agent {
  id: string;
  data: { id: string; name: string; system_prompt?: string };
}
export interface ModelConfig {
  type: string;
  credential_id: string;
  model: string;
  parameters: Record<string, unknown>;
}
export interface Session {
  session: {
    id: string;
    agent_id: string;
    updated_at: string;
    config: { name: string; chat_model_config: ModelConfig | null };
  };
  is_running: boolean;
  status?: { type: string };
}
export interface Block {
  id?: string;
  type: string;
  text?: string;
  state?: string;
}
export interface Message {
  id: string;
  role: string;
  name?: string;
  content: Block[];
  created_at?: string;
}
export interface History {
  messages: Message[];
  is_running: boolean;
  has_more: boolean;
}
export interface AgentEvent {
  id?: string;
  type: string;
  reply_id?: string;
  block_id?: string;
  delta?: string;
  text?: string | null;
  name?: string;
  role?: string;
  finished_reason?: string;
  error?: { message?: string };
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  value?: {
    worker_session_id: string;
    worker_agent_name?: string;
    reply_id: string;
    event_type?: string;
    event?: { tool_calls?: ToolCall[] };
  };
}
export interface CredentialChoice {
  id: string;
  name: string;
  type: string;
}
export interface ModelChoice {
  name: string;
  label?: string;
  status?: string;
}

export interface PermissionRule {
  tool_name: string;
  rule_content: string | null;
  [key: string]: unknown;
}
export interface ToolCall extends Block {
  type: "tool_call";
  id: string;
  name: string;
  input: string;
  suggested_rules?: PermissionRule[];
}
export interface Confirmation {
  replyId: string;
  toolCall: ToolCall;
  workerSession?: string;
  workerName?: string;
}
export interface ConfirmEvent {
  type: "USER_CONFIRM_RESULT";
  id: string;
  created_at: string;
  reply_id: string;
  confirm_results: { confirmed: boolean; tool_call: ToolCall; rules: PermissionRule[] | null }[];
}
