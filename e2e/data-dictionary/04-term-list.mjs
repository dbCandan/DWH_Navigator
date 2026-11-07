import {readFile} from 'node:fs/promises';
import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';
import {workbookText} from '../shared/xlsx.mjs';

// list-search Acceptance 6 and 8 and the page part of Acceptance 7 (Requirement 1, 4-9, 11-15,
// 17) on the local stack with a connected chat model: a 10-term list is uploaded from the browser,
// the progress shows term by term, the list goes on after its page is closed, another person and a
// manager get 404 for it and the other person cannot start a list of their own (409), the list is
// stopped and resumed, the report so far and the final report open with Turkish text, and a term's
// answer opens and takes a vote. The fixture's fourth term holds "YAVAS", which the local fake
// model answers after two minutes, so that the list is still running when it is checked; a real
// model answers it as any term. Kept answers of earlier runs are deleted first through the public
// API. Restarting the backend while the list runs is a separate check.
const LIST = new URL('../fixtures/liste_on_terim.xlsx', import.meta.url);
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

async function download(page, name) {
  const done = page.waitForEvent('download');
  await page.getByRole('link', {name}).first().click();
  const file = await done;
  const bytes = await readFile(await file.path());
  return {name: file.suggestedFilename(), strings: workbookText(bytes)};
}

await withBrowser('term list uploaded, followed, stopped, resumed and reported', async ({page: admin, assert, open}) => {
  await signIn(admin, accounts.superAdmin);
  const people = [];
  let listId = null;
  let owner = null;
  try {
    owner = await preparePerson(admin, 'e2e.liste.sahip', 'Liste Sahibi', 'kullanici');
    const other = await preparePerson(admin, 'e2e.liste.diger', 'Liste Diğer', 'kullanici');
    const manager = await preparePerson(admin, 'e2e.liste.yonetici', 'Liste Yönetici', 'yonetici');
    people.push(owner, other, manager);

    let page = await open({viewport: {width: 1440, height: 900}, acceptDownloads: true});
    await signInPerson(page, owner);
    await page.getByText(message('explorer.status.ready'), {exact: true}).waitFor();

    // Kept answers of earlier runs would answer the terms at once: they are deleted first.
    assert.equal((await api(admin, 'DELETE', '/saved-answers')).status, 200);

    // Upload from the Excel button's file picker; the terms are answered one by one.
    await page.locator('#xl-file').setInputFiles(LIST.pathname);
    await page.locator('section.list').waitFor();
    await page.getByRole('heading', {level: 2, name: 'liste_on_terim.xlsx'}).waitFor();
    await page.locator('.list-head .sub').filter({hasText: /^[1-9]\/10 terim tamamlandı/}).waitFor({timeout: 300000});
    listId = (await api(page, 'GET', '/term-lists?page=1&page_size=1')).body.items[0].id;
    const report = await download(page, message('list.reportSoFar'));
    assert.match(report.name, /^VSA_liste_\w+_\d{8}_\d{4}\.xlsx$/);
    assert.match(report.strings, /[ğüşıöçİ]/, 'the report so far has Turkish text');

    // The list goes on after its page is closed; the pill leads back to it.
    await page.close();
    page = await open({viewport: {width: 1440, height: 900}, acceptDownloads: true});
    await signInPerson(page, owner);
    const pill = page.locator('#listpill');
    await pill.filter({hasText: /^Liste \d+\/10$/}).waitFor();
    await pill.click();
    await page.locator('section.list .list-head .sub').filter({hasText: /terim tamamlandı/}).waitFor();

    // Another person and a manager do not see the list; the other person cannot start one now.
    const otherPage = await open();
    await signInPerson(otherPage, other);
    const managerPage = await open();
    await signInPerson(managerPage, manager);
    for (const view of [otherPage, managerPage]) {
      for (const [method, path] of [
        ['GET', `/term-lists/${listId}`],
        ['GET', `/term-lists/${listId}/report`],
        ['GET', `/term-lists/${listId}/items/1`],
        ['POST', `/term-lists/${listId}/cancel`],
        ['POST', `/term-lists/${listId}/resume`],
      ]) {
        const response = await api(view, method, path);
        assert.equal(response.status, 404, `${method} ${path}`);
        assert.equal(response.body.detail.code, 'term_list_not_found');
      }
    }
    const bytes = await readFile(LIST);
    // Decision 3 (Version 1.3.0): another visitor's upload succeeds in parallel; the primary
    // visitor's own second upload is refused with the single engel message.
    const parallel = await api(otherPage, 'POST', '/term-lists', undefined, {name: 'baska.xlsx', type: XLSX, bytes});
    assert.equal(parallel.status, 201);
    const parallelId = parallel.body.id;
    const selfRefused = await api(page, 'POST', '/term-lists', undefined, {name: 'kendi.xlsx', type: XLSX, bytes});
    assert.equal(selfRefused.status, 409);
    assert.equal(selfRefused.body.detail.message, 'Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.');
    const cancelled = await api(otherPage, 'POST', `/term-lists/${parallelId}/cancel`);
    assert.equal(cancelled.status, 200);

    // Stop, then resume: the answered terms stay, the rest is asked in order.
    await page.getByRole('button', {name: message('list.stop')}).click();
    await page.locator('.list-head .sub').filter({hasText: /^Durduruldu · \d+\/10 terim cevaplandı/}).waitFor({timeout: 30000});
    const stoppedAt = Number(/(\d+)\/10/.exec(await page.locator('.list-head .sub').textContent())[1]);
    await page.getByRole('button', {name: message('list.resume')}).click();
    await page.getByRole('button', {name: message('list.stop')}).waitFor();
    await page.locator('.list-head .sub').filter({hasText: /^Tamamlandı · 10 terim/}).waitFor({timeout: 900000});
    assert.ok(stoppedAt < 10, 'the list was stopped before its end');
    const final = await download(page, message('list.report'));
    assert.match(final.strings, /[ğüşıöçİ]/, 'the final report has Turkish text');

    // A term's answer opens under its row and takes a vote.
    await page.locator('.li-row[aria-expanded]').first().click();
    const detail = page.locator('.li-detail .ans');
    await detail.waitFor({timeout: 30000});
    if (await detail.locator('section.answer-fb').count()) {
      await detail.locator('section.answer-fb').getByRole('button', {name: message('vote.up')}).click();
      await detail.locator('section.answer-fb .fb-msg').filter({hasText: message('vote.thanks')}).waitFor();
    }
    await page.goto(baseUrl + '/');
    await page.locator('#listpill').filter({hasText: message('list.pillResult')}).waitFor();
  } finally {
    // A list that is still running is stopped through the public API.
    if (listId && owner) {
      const view = await open();
      await signInPerson(view, owner);
      await api(view, 'POST', `/term-lists/${listId}/cancel`);
    }
    await retirePeople(admin, people);
  }
});
