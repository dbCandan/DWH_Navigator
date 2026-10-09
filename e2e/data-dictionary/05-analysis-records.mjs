import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';

// analysis-records Acceptance 4 and the browser part of Acceptance 5 (Requirement 1-3, 5, 11,
// 13-20, 22) on the local stack with a connected chat model: an ordinary user asks, stops a
// question and runs a small term list while a manager has Analizler open; the running analysis is
// not listed, the finished ones come within the 15-second refresh with the asker's name and the
// list terms' "📄 <file> #<n>"; the detail shows where the time went, the timeline and the tokens;
// ↑/↓ moves between records and the address opens the same record in a new tab; Genel bakış counts
// them. The user gets 403 from the records; deleting with "Cevabı yazan: Durduruldu" removes only
// the stopped analysis, whose report then cannot be downloaded; a record that ended after the page
// was read stays through "Temizle…" over "Tümü". The question with "YAVAS" is answered by the
// local fake model after two minutes, so it is still running when checked; a real model runs it
// as any question. The interruption by a backend restart and the absent address columns are
// separate checks.
const LIST = new URL('../fixtures/liste_iki_terim.xlsx', import.meta.url);
const run = Date.now().toString(36);
const SLOW = `YAVAS kayıt denemesi ${run}`;
const QUESTION = `Kart limit doluluk oranı nerede (kayıt ${run})?`;

const rowOf = (page, text) => page.locator('#p-analizler tbody tr').filter({hasText: text});

await withBrowser('analysis records seen, opened, navigated and deleted by a manager', async ({page: admin, assert, open}) => {
  await signIn(admin, accounts.superAdmin);
  const people = [];
  let user = null;
  try {
    const asker = await preparePerson(admin, 'e2e.kayit.kullanici', 'Kayıt Soran', 'kullanici');
    const manager = await preparePerson(admin, 'e2e.kayit.yonetici', 'Kayıt Yönetici', 'yonetici');
    people.push(asker, manager);
    user = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(user, asker);
    await user.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    assert.equal((await api(user, 'GET', '/analysis-records?period=today')).status, 403);

    const board = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(board, manager);
    await board.goto(baseUrl + '/admin/analizler');
    await board.locator('#p-analizler').waitFor();

    // A running analysis is not listed; stopped, it is listed within the refresh.
    const field = user.getByRole('textbox', {name: message('explorer.search.label')});
    await field.fill(SLOW);
    await field.press('Enter');
    await user.getByRole('button', {name: message('explorer.search.stop')}).waitFor();
    let running = null;
    for (let i = 0; i < 50 && !running; i++) {
      running = (await api(user, 'GET', '/analyses/active')).body.analysis;
      if (!running) await user.waitForTimeout(200);
    }
    assert.equal(running.query, SLOW);
    await board.getByRole('button', {name: message('records.refresh')}).click();
    await board.waitForTimeout(1500);
    assert.equal(await rowOf(board, SLOW).count(), 0, 'a running analysis is not listed');
    await user.keyboard.press('Escape');
    await user.getByText(message('explorer.ask.stopped')).waitFor();
    await rowOf(board, SLOW).waitFor({timeout: 20000});
    assert.match(await rowOf(board, SLOW).textContent(), /Kayıt Soran/);

    // A question and a small list: the list terms carry their file and position.
    await field.fill(QUESTION);
    await field.press('Enter');
    await user.locator('.ans').waitFor({timeout: 180000});
    await user.locator('#xl-file').setInputFiles(LIST.pathname);
    await user.locator('.list-head .sub').filter({hasText: /^Tamamlandı/}).waitFor({timeout: 600000});
    await rowOf(board, QUESTION).waitFor({timeout: 20000});
    const listRow = board.locator('#p-analizler tbody tr').filter({hasText: '📄 liste_iki_terim.xlsx #2'});
    await listRow.first().waitFor({timeout: 20000});

    // The detail: where the time went, the timeline and the tokens; ↑/↓ and the address.
    await rowOf(board, QUESTION).click();
    const drawer = board.getByRole('dialog');
    await drawer.getByText(message('records.detail.timeline')).waitFor();
    assert.match(await drawer.textContent(), /Süre nereye gitti/);
    assert.match(await drawer.textContent(), /token/);
    const address = board.url();
    await board.keyboard.press('ArrowDown');
    await board.waitForURL((url) => url.toString() !== address);
    const tab = await board.context().newPage();
    await tab.goto(address);
    await tab.getByRole('dialog').filter({hasText: QUESTION}).waitFor();
    await tab.close();
    await board.keyboard.press('Escape');

    // Genel bakış counts the records: the indicators, the 14-day chart and the recent questions.
    await board.goto(baseUrl + '/admin/genel');
    await board.getByRole('img', {name: message('overview.chart.label')}).waitFor();
    await board.getByText(QUESTION).first().waitFor();

    // Deleting only the stopped analyses: its report is gone, the others stay.
    await board.goto(baseUrl + '/admin/analizler');
    await board.getByRole('button', {name: message('records.period.today')}).click();
    const analysts = async () => (await api(board, 'GET', '/analysis-records?period=today&flow=analyst')).body.total;
    const before = await analysts();
    await board.getByLabel(message('records.flowFilter.label')).selectOption('cancelled');
    await rowOf(board, SLOW).waitFor();
    board.once('dialog', (dialog) => {
      board.once('dialog', (answers) => answers.dismiss());
      dialog.accept();
    });
    await board.getByRole('button', {name: message('records.clear')}).click();
    await board.locator('.toast').filter({hasText: message('records.clear.done')}).waitFor();
    assert.equal(await analysts(), before, 'the other analyses stay');
    assert.equal((await api(user, 'GET', `/analyses/${running.analysis_id}/report`)).status, 404);

    // A record that ended after the page was read stays through "Temizle…" (the page's snapshot).
    await board.getByLabel(message('records.flowFilter.label')).selectOption('');
    await board.getByRole('button', {name: message('records.period.all'), exact: true}).click();
    await board.getByRole('button', {name: message('records.refresh')}).click();
    await board.waitForTimeout(1500);
    await user.goto(baseUrl + '/');
    await user.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    const late = `Günlük mevduat bakiyesi (geç ${run})?`;
    await user.getByRole('textbox', {name: message('explorer.search.label')}).fill(late);
    await user.getByRole('textbox', {name: message('explorer.search.label')}).press('Enter');
    await user.locator('.ans').waitFor({timeout: 180000});
    board.once('dialog', (dialog) => {
      board.once('dialog', (answers) => answers.dismiss());
      dialog.accept();
    });
    await board.getByRole('button', {name: message('records.clear')}).click();
    await board.locator('.toast').filter({hasText: message('records.clear.done')}).waitFor();
    const left = (await api(board, 'GET', `/analysis-records?period=all&q=${encodeURIComponent(run)}`)).body;
    assert.ok(left.items.some((row) => row.query === late), 'the analysis that ended later stays');
  } finally {
    // A question still running (the scenario stopped early) is stopped through the public API.
    if (user) {
      const active = (await api(user, 'GET', '/analyses/active').catch(() => null))?.body?.analysis;
      if (active) await api(user, 'POST', `/analyses/${active.analysis_id}/cancel`);
    }
    await retirePeople(admin, people);
  }
});
