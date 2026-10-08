import path from 'path';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
import svgr from 'vite-plugin-svgr';

export default defineConfig(({ mode }) => {
 const env = loadEnv(mode, path.resolve(__dirname, "../.."), "HARBOR_");
 return {
	plugins: [react(), tailwindcss(), svgr()],
	server: {
        host: '127.0.0.1', port: Number(env.HARBOR_WEB_PORT || 5177), strictPort: true,
		proxy: {
			'/api': { target: `http://127.0.0.1:${env.HARBOR_API_PORT || 8017}`, rewrite: (p) => p.replace(/^\/api/, ''), },
		},
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
			'next/navigation': path.resolve(__dirname, './src/lib/next-navigation-shim.ts'),
		},
	},
	optimizeDeps: {
		include: ['mime'],
	},
}; });
