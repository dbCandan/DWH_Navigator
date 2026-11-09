import '@testing-library/jest-dom/vitest';
import {cleanup, configure} from '@testing-library/react';
import {afterEach, beforeEach} from 'vitest';
import {setConfirmHandler} from '@/lib/confirm';
import {serveAdminDefaults} from './admin';
import {serveExplorerDefaults} from './explorer';

// Admin pages load lazily: a cold start with many workers (a container on a bind mount) can need
// more than the default second before the first page text appears. Passing tests do not wait longer.
configure({asyncUtilTimeout: 5000});

// The admin shell reads the settings, the index and the dictionary on every page; tests that do
// not look at them get a settled, empty installation instead of a network error.
beforeEach(() => {
  serveAdminDefaults();
  serveExplorerDefaults();
});

// Vitest globals are off, so Testing Library cannot register its own unmount hook.
afterEach(() => {
  cleanup();
  setConfirmHandler(null);
});
