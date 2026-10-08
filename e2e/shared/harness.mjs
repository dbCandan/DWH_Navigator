import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdir} from 'node:fs/promises';

export const baseUrl = (process.env.APP_E2E_BASE || 'http://localhost:8080').replace(/\/$/, '');
export const apiPrefix = '/api/dwhnavigator/v1';
export const username = process.env.APP_E2E_SUPER_ADMIN_USER || process.env.DWHNAVIGATOR_SUPER_ADMIN_USER;
export const password = process.env.APP_E2E_SUPER_ADMIN_PASS || process.env.DWHNAVIGATOR_SUPER_ADMIN_PASS;

/**
 * Process-supplied local accounts; nothing is stored in the repository. A super admin opened from
 * the start-up password still holds a one-time password and sets `newPassword`
 * (APP_E2E_SUPER_ADMIN_NEW_PASS) at its first sign-in; later runs sign in with that password.
 */
export const accounts = {
  superAdmin: {username, password, newPassword: process.env.APP_E2E_SUPER_ADMIN_NEW_PASS},
};

const primaryCatalog = JSON.parse(
  readFileSync(new URL('../../app/frontend/src/locales/tr.json', import.meta.url), 'utf8'),
);

/** Resolve a UI text from the primary locale catalog so selectors follow the configured language. */
export function message(key) {
  const value = key in primaryCatalog
    ? primaryCatalog[key]
    : key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), primaryCatalog);
  assert.equal(typeof value, 'string', `missing primary locale message ${key}`);
  return value;
}

/**
 * Sign in through the real form and wait for the main screen. When the account still holds its
 * one-time password, the same screen asks for a new one (user-accounts Requirement 16); the
 * account's `newPassword` is set there. Returns whether that first-sign-in step ran.
 */
export async function signIn(page, account) {
  assert.ok(account.username && account.password, 'account credentials are required');
  await page.goto(baseUrl + '/login');
  await page.getByLabel(message('auth.login.username')).fill(account.username);
  await page.getByLabel(message('auth.login.password'), {exact: true}).fill(account.password);
  await page.getByRole('button', {name: message('auth.login.submit')}).click();
  const home = page.getByRole('heading', {name: message('explorer.hero.title')});
  const firstLogin = page.getByRole('heading', {name: message('auth.firstLogin.title')});
  await home.or(firstLogin).waitFor();
  if (!(await firstLogin.isVisible())) return false;
  assert.ok(account.newPassword, 'the account asks for a new password: set APP_E2E_SUPER_ADMIN_NEW_PASS');
  await page.getByLabel(message('auth.password.new'), {exact: true}).fill(account.newPassword);
  await page.getByLabel(message('auth.password.repeat')).fill(account.newPassword);
  await page.getByRole('button', {name: message('auth.firstLogin.submit')}).click();
  await home.waitFor();
  return true;
}

// Chromium logs every non-2xx fetch as "Failed to load resource". Those lines only repeat the
// HTTP status: a 401 of a session restore without a refresh cookie is part of the contract, and
// every 5xx is checked from the response itself below, with its URL.
const NETWORK_STATUS_LOG = /^Failed to load resource: the server responded with a status of \d{3}/;

export async function withBrowser(name, scenario) {
  assert.ok(username, 'APP_E2E_SUPER_ADMIN_USER is required');
  assert.ok(password, 'APP_E2E_SUPER_ADMIN_PASS is required');
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext();
  const allowedOrigin = new URL(baseUrl).origin;
  const externalRequests = [];
  const consoleErrors = [];
  const pageErrors = [];
  const serverErrors = [];
  await context.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    const protocol = new URL(requestUrl).protocol;
    if (new URL(requestUrl).origin === allowedOrigin || protocol === 'data:' || protocol === 'blob:') {
      await route.continue();
      return;
    }
    externalRequests.push(requestUrl);
    await route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error' && !NETWORK_STATUS_LOG.test(message.text())) {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.stack || error.message || String(error));
  });
  page.on('response', (response) => {
    const responseUrl = response.url();
    if (new URL(responseUrl).origin === allowedOrigin && response.status() >= 500) {
      serverErrors.push(`${response.status()} ${response.request().method()} ${responseUrl}`);
    }
  });
  try {
    await scenario({page, assert});
    assert.deepEqual(externalRequests, [], 'browser attempted an external network request');
    assert.deepEqual(consoleErrors, [], 'browser emitted console.error output');
    assert.deepEqual(pageErrors, [], 'browser emitted an uncaught page error');
    assert.deepEqual(serverErrors, [], 'same-origin request returned HTTP 5xx');
    console.log('PASS ' + name);
  } catch (error) {
    await mkdir('test-results', {recursive: true});
    const artifact = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    await page.screenshot({path: `test-results/${artifact || 'scenario'}-failure.png`, fullPage: true});
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }
}

export async function runScenario(name, scenario) {
  return withBrowser(name, ({page}) => scenario({page, expect}));
}
