import { QueryClientProvider } from '@tanstack/react-query';
import { Onborda, OnbordaProvider } from 'onborda';
import { useEffect, useMemo, useState } from 'react';
import { createBrowserRouter, createHashRouter, Navigate, RouterProvider } from 'react-router-dom';

import { MCPHubPage } from './pages/mcp';
import { SkillHubPage } from './pages/skill';
import { harborRequest, rememberIdentity } from '@/api/harbor';
import type { Identity } from '@/api/harbor';
import { RouteError } from '@/components/error/RouteError';
import { AppLayout } from '@/components/layout/AppLayout';
import { HarborBar } from '@/components/layout/HarborBar';
import { buildChatTour } from '@/components/tour/chatTourSteps';
import { TourCard } from '@/components/tour/TourCard';
import { Toaster } from '@/components/ui/sonner';
import { HarborContext } from '@/context/HarborContext';
import { UploadProvider } from '@/context/UploadContext';
import { useTranslation } from '@/i18n/useI18n';
import { isDesktop } from '@/lib/desktop';
import { queryClient } from '@/lib/query-client';
import { ChannelPage } from '@/pages/channel';
import { ChatPage } from '@/pages/chat';
import { CredentialPage } from '@/pages/credential';
import { KnowledgePage } from '@/pages/knowledge';
import { SchedulePage } from '@/pages/schedule';
import { SetupPage } from '@/pages/setup/HarborLogin';
import { TenantPage } from '@/pages/tenants';

const router = (isDesktop ? createHashRouter : createBrowserRouter)([
	{
		element: <AppLayout />,
		errorElement: <RouteError />,
		children: [
			{
				// Content-level boundary: a crash in a page replaces only
				// the Outlet area, so AppLayout (the icon rail / nav) stays
				// usable. The parent route keeps its own errorElement as a
				// last-resort catch-all for AppLayout/AppSidebar crashes.
				errorElement: <RouteError />,
				children: [
					{ path: '/', element: <Navigate to="/chat" replace /> },
					{
						path: '/chat/:agentId?/:sessionId?/:memberId?',
						element: <ChatPage />,
					},
					{ path: '/tenants', element: <TenantPage /> },
					{ path: '/schedule', element: <SchedulePage /> },
					{ path: '/channel', element: <ChannelPage /> },
					{ path: '/credential', element: <CredentialPage /> },
					{ path: '/mcp', element: <MCPHubPage /> },
					{ path: '/mcp/:hubId', element: <MCPHubPage /> },
					{ path: '/skill', element: <SkillHubPage /> },
					{ path: '/skill/:hubId', element: <SkillHubPage /> },
					{ path: '/knowledge', element: <KnowledgePage /> },
					{ path: '/knowledge/:kbId', element: <KnowledgePage /> },
				],
			},
		],
	},
	{ path: '/setup', element: <Navigate to="/tenants" replace />, errorElement: <RouteError /> },
]);

function App() {
	const { t } = useTranslation();
	const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const loadIdentity = () => {
    setLoading(true);
    harborRequest<Identity>('/auth/me').then(me => { rememberIdentity(me); setIdentity(me); })
      .catch(() => setIdentity(null)).finally(() => setLoading(false));
  };
  useEffect(() => {
    loadIdentity();
    const unauthorized = () => { queryClient.clear(); setIdentity(null); };
    window.addEventListener('harbor:unauthorized', unauthorized);
    return () => window.removeEventListener('harbor:unauthorized', unauthorized);
  }, []);
	const tours = useMemo(() => [buildChatTour(t)], [t]);

	if (loading) return <div className="h-dvh grid place-items-center text-muted-foreground">正在连接智港…</div>;
	if (!identity) return <SetupPage onComplete={loadIdentity} />;

	return (
		<HarborContext.Provider value={identity}>
		<QueryClientProvider client={queryClient}>
        <HarborBar />
			<OnbordaProvider>
				<Onborda
					steps={tours}
					cardComponent={TourCard}
					shadowOpacity="0.6"
					cardTransition={{ type: 'spring', duration: 0.4 }}
				>
					<UploadProvider>
						<RouterProvider router={router} />
					</UploadProvider>
					<Toaster richColors position="top-right" />
				</Onborda>
			</OnbordaProvider>
		</QueryClientProvider>
      </HarborContext.Provider>
	);
}

export default App;
