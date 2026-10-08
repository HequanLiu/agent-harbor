import { Outlet } from 'react-router-dom';

import { AppSidebar } from '@/components/layout/AppSidebar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';

export function AppLayout() {
	return (
		<div className="h-[calc(100dvh-3.5rem)] flex">
			<SidebarProvider className="min-h-0">
				<AppSidebar />
				<SidebarInset className="flex-1 overflow-hidden bg-canvas">
					<Outlet />
				</SidebarInset>
			</SidebarProvider>
		</div>
	);
}
