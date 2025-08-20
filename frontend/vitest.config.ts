/// <reference types="vitest" />
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: './src/setupTests.ts',
        coverage: {
            provider: 'v8',
            reporter: ['text', 'html'],
            lines: 80,
            exclude: [
                'src/types.ts',
                'src/pages/ScenarioTester.tsx',
                'src/pages/GroupPortfolio.tsx',
                'src/pages/VirtualPortfolio.tsx'
            ]
        }
    }
});
