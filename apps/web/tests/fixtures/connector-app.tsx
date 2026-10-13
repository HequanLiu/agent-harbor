import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ConnectorApp } from '../../src/components/connector-ui/ConnectorApp';
import { ConnectorChatContext } from '../../src/components/connector-ui/context';
import { ASBlock } from '../../src/components/chat/ASMessageBubble';
import '../../src/i18n';
import '../../src/index.css';

function Fixture() {
  const [message, setMessage] = useState('');
  const mes = new URLSearchParams(location.search).get('app') === 'mes';
  const background = new URLSearchParams(location.search).has('background');
  const binding = { binding_token: 'fixture-binding', resource_uri: mes ? 'ui://mes/order-editor/v1' : 'ui://crm/opportunity/v1', tool_name: mes ? 'mes_order_draft_create' : 'crm_opportunity_create' };
  const hint = { type: 'hint' as const, id: 'background-result', hint: 'Background tool completed',
    source: 'tool_output', created_at: new Date().toISOString(), finished_at: new Date().toISOString(),
    metadata: { connector_ui: binding } };
  return <ConnectorChatContext.Provider value={{ agentId: 'agent', sessionId: 'chat', busy: false, send: setMessage }}>
    {background ? <ASBlock block={hint} /> : <ConnectorApp binding={binding} />}
    <output data-testid="message">{message}</output>
  </ConnectorChatContext.Provider>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
