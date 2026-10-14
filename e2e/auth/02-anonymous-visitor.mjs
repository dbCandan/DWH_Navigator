import {accounts, apiPrefix, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';

// application-foundation 003-anonymous-visitor Acceptance 2 (Requirement 1-8): a browser without a
// session opens the main screen, asks a question and gets the answer; a second browser context is
// another visitor and cannot reach the first one's analysis; the main screen has no session area;
// /admin asks for the sign-in and the analysis record shows the visitor by its address.
const QUESTION = 'Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?';

await withBrowser('anonymous visitor: main screen without a session, admin behind it', async ({page, assert, open}) => {
  await page.goto(baseUrl + '/');
  await page.getByRole('heading', {name: message('explorer.hero.title')}).waitFor();
  assert.equal(new URL(page.url()).pathname, '/', 'the main screen does not redirect to the sign-in');
  const sessionMenu = new RegExp('^' + message('session.menu').replace('{name}', ''));
  assert.equal(await page.getByRole('button', {name: sessionMenu}).count(), 0, 'no session area');

  const device = await page.evaluate(() => localStorage.getItem('dwhnavigator.device'));
  assert.match(device ?? '', /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);

  const field = page.getByRole('textbox', {name: message('explorer.search.label')});
  await field.fill(QUESTION);
  await field.press('Enter');
  await page.locator('.ans').waitFor({timeout: 180000});
  const checks = await page.evaluate(async (prefix) => {
    const device = localStorage.getItem('dwhnavigator.device');
    const active = await fetch(prefix + '/analyses/active', {headers: {'X-Device-Id': device}});
    const seen = await fetch(prefix + '/analysis-records', {headers: {'X-Device-Id': device}});
    return {active: active.status, records: seen.status};
  }, apiPrefix);
  assert.equal(checks.active, 200);
  assert.equal(checks.records, 401, 'the device id opens no administration endpoint');

  // A second browser context is another visitor: the first one's analysis is "not found".
  const ownJob = await page.evaluate(async (prefix) => {
    const device = localStorage.getItem('dwhnavigator.device');
    const started = await fetch(prefix + '/analyses', {
      method: 'POST',
      headers: {'X-Device-Id': device, 'Content-Type': 'application/json'},
      body: JSON.stringify({query: 'kart limiti', top: 5, fresh: false}),
    });
    return (await started.json()).analysis_id;
  }, apiPrefix);
  const other = await open();
  await other.goto(baseUrl + '/');
  await other.getByRole('heading', {name: message('explorer.hero.title')}).waitFor();
  const foreign = await other.evaluate(
    async ([prefix, id]) => {
      const device = localStorage.getItem('dwhnavigator.device');
      return (await fetch(prefix + '/analyses/' + id, {headers: {'X-Device-Id': device}})).status;
    },
    [apiPrefix, ownJob],
  );
  assert.equal(foreign, 404, "another visitor's analysis is not found");
  const missing = await other.evaluate(async (prefix) => (await fetch(prefix + '/status')).status, apiPrefix);
  assert.equal(missing, 400, 'a request without a device id is refused');

  // /admin asks for the sign-in; the record shows the visitor by its host name and address.
  const admin = await open();
  await admin.goto(baseUrl + '/admin');
  await admin.waitForURL(baseUrl + '/login');
  await signIn(admin, accounts.superAdmin);
  await admin.waitForURL(baseUrl + '/admin/genel');
  await admin.goto(baseUrl + '/admin/analizler');
  await admin.getByText(QUESTION).first().waitFor();
  const row = admin.locator('tr', {hasText: QUESTION}).first();
  assert.match(await row.innerText(), /\d+\.\d+\.\d+\.\d+/, 'the asker is shown by its address');
});
