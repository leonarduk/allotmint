/// <reference types="vitest" />
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: './src/setupTests.ts',
        include: ['src/**/*.test.{ts,tsx,js}'],
        coverage: {
            reporter: ['text', 'lcov'],
            lines: 80,
            statements: 80,
            functions: 80,
            branches: 80
        }
    }
});
