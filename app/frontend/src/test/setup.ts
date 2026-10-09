import '@testing-library/jest-dom/vitest';
import {cleanup} from '@testing-library/react';
import {afterEach, beforeEach} from 'vitest';
import {serveAdminDefaults} from './admin';

// The admin shell reads the settings, the index and the dictionary on every page; tests that do
// not look at them get a settled, empty installation instead of a network error.
beforeEach(() => serveAdminDefaults());

// Vitest globals are off, so Testing Library cannot register its own unmount hook.
afterEach(() => cleanup());
