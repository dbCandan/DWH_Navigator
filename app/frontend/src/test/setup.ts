import '@testing-library/jest-dom/vitest';
import {cleanup} from '@testing-library/react';
import {afterEach, beforeEach} from 'vitest';
import {setConfirmHandler} from '@/lib/confirm';
import {serveAdminDefaults} from './admin';
import {serveExplorerDefaults} from './explorer';

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
