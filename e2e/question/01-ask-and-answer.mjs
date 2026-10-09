import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';

// question-analysis Requirement 19-21 on the local stack with a connected chat model: ask, follow
// the live progress, stop, read the answer, download the report through the shared client, get the
// kept answer again and ask for a new analysis.
const QUESTION = 'Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?';

await withBrowser('question asked, stopped, answered, reported and answered again', async ({page, assert}) => {
  await signIn(page, accounts.superAdmin);
  await page.waitForURL(baseUrl + '/');
  const field = page.getByRole('textbox', {name: message('explorer.search.label')});
  const root = page.locator('html');

  // The status pill reads GET /status; a model must be connected for this scenario.
  await page.getByText(message('explorer.status.ready'), {exact: true}).waitFor();

  // Ask, then stop: the button says "Durdur" while the analysis runs and Esc stops it.
  await field.fill(QUESTION);
  await field.press('Enter');
  const stop = page.getByRole('button', {name: message('explorer.search.stop')});
  await stop.waitFor();
  assert.match((await root.getAttribute('class')) ?? '', /\bdocked\b/);
  assert.match((await root.getAttribute('class')) ?? '', /\bbusy\b/);
  await page.keyboard.press('Escape');
  await page.getByText(message('explorer.ask.stopped')).waitFor({timeout: 10000});

  // Ask again and wait for the answer; a kept answer is analysed again with "Yeniden analiz et".
  await field.fill(QUESTION);
  await field.press('Enter');
  const answer = page.locator('.ans');
  await answer.waitFor({timeout: 180000});
  if (await page.locator('.src.reused').count()) {
    await page.getByRole('button', {name: message('answer.redo')}).click();
    await page.locator('.ans .src.ai').waitFor({timeout: 180000});
  }
  await page.locator('.ans-verdict').waitFor();
  assert.equal(await page.locator('.src.reused').count(), 0, 'a new analysis is not a kept answer');

  // The report comes through the shared client: the token travels in the header, not the address.
  const reportRequest = page.waitForRequest((request) => request.url().endsWith('/report'));
  const download = page.waitForEvent('download');
  await page.getByRole('link', {name: message('answer.report')}).click();
  const request = await reportRequest;
  assert.match(request.headers().authorization ?? '', /^Bearer /);
  assert.doesNotMatch(request.url(), /token|bearer/i);
  const file = await download;
  assert.match(file.suggestedFilename(), /^VSA_ask_\w+_\d{8}_\d{4}\.xlsx$/);

  // The same question again comes from the kept answer; "Yeniden analiz et" analyses it again.
  await field.click();
  await field.fill(QUESTION);
  await field.press('Enter');
  await page.locator('.ans .src.reused').waitFor({timeout: 15000});
  await page.getByRole('button', {name: message('answer.redo')}).click();
  await page.locator('.ans .src.ai').waitFor({timeout: 180000});
  assert.equal(await page.locator('.src.reused').count(), 0, '"Yeniden analiz et" gives a new analysis');
});
