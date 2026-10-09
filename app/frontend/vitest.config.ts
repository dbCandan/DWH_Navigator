import {fileURLToPath, URL} from 'node:url';
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {alias: {'@': fileURLToPath(new URL('./src', import.meta.url))}},
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {reporter: ['text', 'json-summary']},
    // Stylesheets read as text (`?raw`) keep their content; imported ones stay empty in tests.
    css: {include: [/\.css\?raw$/]},
  },
});
