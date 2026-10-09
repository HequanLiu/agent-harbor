import type { HarborClient } from "../api/client";
import type { ModelConfig } from "./types";
type Client = Pick<HarborClient, "agents" | "sessions" | "credentials" | "models" | "createSession">;
export interface DefaultChat { id: string; agentId: string; agentName: string; name: string; model: string }
export async function defaultChat(api: Client, current: () => boolean = () => true, options: { agentId?: string; sourceSessionId?: string; createNew?: boolean } = {}): Promise<DefaultChat> {
  const agents = (await api.agents()).agents;
  const agent = options.agentId ? agents.find(a => a.id === options.agentId) : agents[0];
  if (!agent) throw new Error("还没有 Agent，请先在桌面端创建智能体。");
  const [history, choices] = await Promise.all([api.sessions(agent.id), api.credentials()]);
  const credentials = choices.credentials;
  if (!credentials.length) throw new Error("尚未配置模型服务，请先在桌面端添加模型凭据。");
  const base = {agentId: agent.id, agentName: agent.data.name};
  const recent = [...history.sessions].sort((a,b) => (Number(b.session.id === options.sourceSessionId) - Number(a.session.id === options.sourceSessionId)) || b.session.updated_at.localeCompare(a.session.updated_at)).find(item => {
    const model = item.session.config.chat_model_config;
    return model?.model && credentials.some(c => c.id === model.credential_id && c.type === model.type);
  });
  if (recent && !options.createNew) return {...base, id: recent.session.id, name: recent.session.config.name, model: recent.session.config.chat_model_config!.model};
  let selected: ModelConfig | undefined = recent?.session.config.chat_model_config || undefined;
  for (const credential of credentials) {
    if (selected) break;
    if (!current()) throw new Error("工作空间已变化，请重试。");
    const catalog = await api.models(credential.type);
    const model = catalog.models.find(m => m.status !== "sunset");
    if (model) { selected = {type: credential.type, credential_id: credential.id, model: model.name, parameters: {}}; break; }
  }
  if (!selected) throw new Error("该模型服务没有可用模型，请先在桌面端配置模型。");
  if (!current()) throw new Error("工作空间已变化，请重试。");
  const session = await api.createSession(agent.id, selected);
  return {...base, id: session.session_id, name: "新对话", model: selected.model};
}
