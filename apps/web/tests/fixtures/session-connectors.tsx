import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { HarborContext } from '../../src/context/HarborContext';
import { ChatContent } from '../../src/components/chat/ChatContent';
import { ConnectorsPage } from '../../src/pages/connectors';
import { TooltipProvider } from '../../src/components/ui/tooltip';
import '../../src/index.css';
import i18n from '../../src/i18n';
void i18n.changeLanguage('zh');
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
function Fixture() {
  const [session, setSession] = useState('first');
  const [phase, setPhase] = useState<'idle' | 'streaming'>('idle');
  const [manage, setManage] = useState(false);
  return <><button onClick={() => setSession(session === 'first' ? 'second' : 'first')}>Switch session</button>
    <button onClick={() => setPhase(phase === 'idle' ? 'streaming' : 'idle')}>Toggle running</button>
    <button onClick={() => setManage(!manage)}>Manage</button>
    <div style={{ height: '85vh' }}>{manage ? <ConnectorsPage /> : <ChatContent
      msgs={[]} phase={phase} disabled={false} onSend={() => {}} onUserConfirm={async () => {}}
      allowedInputTypes={['text']} fileProcessor={async () => null} agentId="agent"
      sessionId={session} cwd={null} onCwdChange={() => {}} />}</div></>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={client}>
  <HarborContext.Provider value={{ user: { id: 'user', name: 'Test', email: 'test@example.test' }, active_tenant_id: 'tenant', tenants: [] }}>
    <MemoryRouter><TooltipProvider><Fixture /></TooltipProvider></MemoryRouter>
  </HarborContext.Provider>
</QueryClientProvider>);
