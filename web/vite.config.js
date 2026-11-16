import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// npm run dev: /api calls go to the Azure site (or set API_TARGET=http://localhost:7071 for func start)
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            '/api': {
                target: process.env.API_TARGET || 'https://witty-wave-0b6cca200.6.azurestaticapps.net',
                changeOrigin: true,
            },
        },
    },
});