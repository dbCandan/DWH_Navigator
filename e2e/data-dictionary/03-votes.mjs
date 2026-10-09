import {readFile} from 'node:fs/promises';
import {accounts, message, signIn, withBrowser} from '../shared/harness.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';
import {workbookText} from '../shared/xlsx.mjs';

// answer-feedback Acceptance 6 and 7 (Requirement 5-7, 9-13) on the local stack with a connected
// chat model and three people: two give a table a reasoned 👎 and the third sees it among the
// rejected tables with the reason; a 👍 gives "✓ 1 kişi doğruladı" and the confidence before the
// votes; the answer's report is the same before and after the votes; two 👎 on the kept answer
// delete it, the question is analysed again, and the voter sees their own votes pressed in another
// browser. Votes are kept for good (Decision 13); every run casts the same votes with the same
// people on the same question, so a later run starts from, and ends in, the same tallies.
const QUESTION = 'Günlük mevduat bakiyesi nerede?';

async function ask(page, text) {
  const field = page.getByRole('textbox', {name: message('explorer.search.label')});
  await field.fill(text);
  await field.press('Enter');
  await page.locator('.ans').waitFor({timeout: 180000});
}

/** The suggestion card of a table, opened. */
async function card(page, name) {
  const pick = page.locator('article.pick').filter({has: page.locator('.pk-name', {hasText: new RegExp(`^${name}`)})}).first();
  if (!(await pick.isVisible())) {
    await page.locator('summary').filter({hasText: /^Kullanıcıların uygun bulmadığı tablolar/}).click();
  }
  if (!(await pick.evaluate((el) => el.classList.contains('open')))) await pick.locator('.pick-row').click();
  return pick;
}

/** The report's cells, without the time it was made ("Üretim"). */
async function reportCells(page) {
  const download = page.waitForEvent('download');
  await page.getByRole('link', {name: message('answer.report')}).first().click();
  const bytes = await readFile(await (await download).path());
  return workbookText(bytes, /^xl\/(worksheets\/[^/]+|sharedStrings)\.xml$/).replace(/\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}/g, '');
}

await withBrowser('votes of three people shape the answer and retire a kept answer', async ({page: admin, assert, open}) => {
  await signIn(admin, accounts.superAdmin);
  const people = [];
  try {
    for (const n of [1, 2, 3]) people.push(await preparePerson(admin, `e2e.oy.${n}`, `Oy Kişisi ${n}`, 'kullanici'));
    const first = people[0];
    const pages = [];
    for (const person of people) {
      const page = await open({viewport: {width: 1440, height: 900}, acceptDownloads: true});
      await signInPerson(page, person);
      await page.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
      pages.push(page);
    }
    const [one, two, three] = pages;

    // The viewer asks first and keeps the report of this answer.
    await ask(three, QUESTION);
    const reportBefore = await reportCells(three);

    // Which tables: the ones an earlier run rejected and approved, or else the best one and the next.
    const rejectedFold = one.locator('summary').filter({hasText: /^Kullanıcıların uygun bulmadığı tablolar/});
    await ask(one, QUESTION);
    const rows = await one.locator('.ans-main > .pick-list > article.pick .pk-name').allTextContents();
    const earlier = (await rejectedFold.count())
      ? await one.locator('details.ask-more').filter({has: rejectedFold}).locator('.pk-name').allTextContents()
      : [];
    const clean = (text) => text.replace(/[✓!↑]$/, '').trim();
    const rejectName = clean(earlier[0] ?? rows[0]);
    const approveName = clean(rows.find((row) => row.endsWith('✓')) ?? rows.find((row) => clean(row) !== rejectName));
    assert.ok(rejectName && approveName, 'the answer suggests at least two tables');

    // Two people give the rejected table a reasoned 👎; the first approves another table.
    for (const [page, reason] of [[one, message('vote.reason.topic')], [two, message('vote.reason.column')]]) {
      if (page === two) await ask(two, QUESTION);
      const pick = await card(page, rejectName);
      await pick.getByRole('button', {name: message('vote.down')}).click();
      await pick.getByRole('button', {name: reason}).click();
      await pick.getByText(message('vote.reasonSaved')).waitFor();
    }
    const approved = await card(one, approveName);
    await approved.getByRole('button', {name: message('vote.up')}).click();
    await approved.getByText(message('vote.thanks')).waitFor();

    // The viewer's next look: the table is apart with its reasons; the other one is approved.
    await ask(three, QUESTION);
    const fold = three.locator('details.ask-more').filter({has: three.locator('summary', {hasText: /^Kullanıcıların uygun bulmadığı tablolar/})});
    await fold.locator(':scope > summary').click();
    const rejectedCard = fold.locator('article.pick.dim').filter({hasText: rejectName});
    await rejectedCard.locator('.pick-row').click();
    const badge = rejectedCard.locator('.vb.down');
    assert.equal((await badge.textContent()).trim(), message('vote.badge.rejected').replace('{count}', '2'));
    const why = await badge.getAttribute('title');
    assert.ok(why.includes(message('vote.reason.topic')) && why.includes(message('vote.reason.column')), 'the reasons are in the badge');
    const approvedCard = await card(three, approveName);
    assert.equal(
      (await approvedCard.locator('.vb.up').textContent()).trim(),
      message('vote.badge.approved').replace('{count}', '1'),
    );
    assert.match(await approvedCard.locator('.pick-row').getAttribute('title'), /oylardan önce %\d+/);

    // The report is the answer as written: the votes do not change it.
    assert.equal(await reportCells(three), reportBefore, 'the report is the same before and after the votes');

    // Two 👎 on the kept answer delete it; the question is then analysed again.
    await ask(one, QUESTION);
    await one.locator('.ans .src.reused').waitFor();
    for (const page of [one, two]) {
      if (page === two) await ask(two, QUESTION);
      await page.locator('section.answer-fb').getByRole('button', {name: message('vote.down')}).click();
    }
    // The vote that makes the answer rejected deletes it: the second one, or the first when the
    // other person's earlier 👎 falls in the minute the kept answer was written (Requirement 6).
    const forgotten = (page) => page.locator('.fb-after').filter({hasText: message('vote.answer.forgotten')}).waitFor();
    await Promise.any([forgotten(one), forgotten(two)]);
    const recordsBefore = (await api(admin, 'GET', '/analysis-records?period=today&flow=analyst')).body.total;
    await ask(three, QUESTION);
    assert.equal(await three.locator('.ans .src.reused').count(), 0, 'the question is analysed again');
    await admin.waitForTimeout(500);
    const recordsAfter = (await api(admin, 'GET', '/analysis-records?period=today&flow=analyst')).body.total;
    assert.equal(recordsAfter, recordsBefore + 1, 'the new analysis is in the records');

    // In another browser the first person's own votes are pressed.
    const again = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(again, first);
    await again.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    await ask(again, QUESTION);
    const mine = await card(again, approveName);
    assert.equal(await mine.getByRole('button', {name: message('vote.up')}).getAttribute('aria-pressed'), 'true');
    const minedown = await card(again, rejectName);
    assert.equal(await minedown.getByRole('button', {name: message('vote.down')}).getAttribute('aria-pressed'), 'true');
  } finally {
    await retirePeople(admin, people);
  }
});
