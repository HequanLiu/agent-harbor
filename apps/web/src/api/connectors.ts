import { harborRequest } from './harbor';
import { validateConnectorArchive } from '@/lib/connector-validation';
import { apiBaseUrl, apiFetch } from '@/lib/desktop';

export interface ConnectorTool { name: string; description?: string }
export interface Connector {
  examples?: string[];
  id: string;
  source: string;
  name: string;
  description?: string;
  version?: string;
  status: 'installed' | 'connected';
  skills: string[];
  tools: ConnectorTool[];
  sha256: string;
}
export interface ConnectorList { items: Connector[]; enabled: boolean }
const path = (id: string) => `/connectors/${encodeURIComponent(id)}`;

export const connectorApi = {
  selection: (agentId: string, sessionId: string) =>
    harborRequest<{ connector_ids: string[] }>(`/connectors/sessions/${encodeURIComponent(agentId)}/${encodeURIComponent(sessionId)}`),
  select: (agentId: string, sessionId: string, connectorIds: string[]) =>
    harborRequest<{ connector_ids: string[] }>(`/connectors/sessions/${encodeURIComponent(agentId)}/${encodeURIComponent(sessionId)}`, 'PUT', { connector_ids: connectorIds }),
  list: () => harborRequest<ConnectorList>('/connectors/'),
  async importArchive(file: File): Promise<Connector> {
    const problem = validateConnectorArchive(file);
    if (problem) throw new Error(problem);
    const response = await apiFetch(new URL('harbor/connectors/import', apiBaseUrl()), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/zip' },
      body: await file.arrayBuffer(),
    });
    if (response.status === 401) window.dispatchEvent(new Event('harbor:unauthorized'));
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : `导入失败 (${response.status})`);
    }
    return response.json();
  },
  authorize: (id: string, externalBrowser = false) => harborRequest<{ authorization_url: string }>(`${path(id)}/authorize${externalBrowser ? '?external_browser=true' : ''}`, 'POST'),
  tools: (id: string) => harborRequest<{ tools: ConnectorTool[] }>(`${path(id)}/tools`),
  install: (id: string, agentId: string, sessionId: string) =>
    harborRequest<{ installed: boolean }>(`${path(id)}/install`, 'POST', { agent_id: agentId, session_id: sessionId }),
  disconnect: (id: string) => harborRequest<{ status: 'installed'; remote_revoked: boolean }>(`${path(id)}/disconnect`, 'POST'),
  resolveDraft: (draftId: string) => harborRequest<{ connector_id: string; url: string }>(`/connectors/drafts/${encodeURIComponent(draftId)}/connection`),
  delete: (id: string) => harborRequest<void>(path(id), 'DELETE'),
};
