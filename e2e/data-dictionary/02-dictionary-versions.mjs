import {readFile} from 'node:fs/promises';
import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';
import {seedDictionary} from '../shared/dictionary.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';
import {workbookText} from '../shared/xlsx.mjs';

// dictionary-management Acceptance 4 (Requirement 8, 12-15) and the map part of
// dictionary-explorer Acceptance 3 (Requirement 2, 16): a second synthetic dictionary is seeded and
// the index rebuilt; a manager sees the counts and the warnings, opens a table by its address and
// exports the dictionary, and after one more version the previous one is the one before, with no
// button to go back. An ordinary user gets no Sözlük page and 403 from /dictionary, and the open
// main screen shows the new column count and draws the new tables within a status poll. The Excel
// upload and the template are gone (dictionary-sync Requirement 13), so both routes refuse here.
// The original synthetic dictionary is seeded back.
const ORIGINAL = new URL('../../app/backend/tests/fixtures/parity/sozluk_sentetik.xlsx', import.meta.url);
const SECOND = new URL('../fixtures/sozluk_sentetik_ek.xlsx', import.meta.url);
const ADDED_TABLE = 'SYNDM.E2E.vE2eEkTablo';

await withBrowser('dictionary versions, roles and the map after a new version', async ({page: admin, assert, open}) => {
  await signIn(admin, accounts.superAdmin);
  const people = [];
  try {
    const manager = await preparePerson(admin, 'e2e.sozluk.yonetici', 'Sözlük Yönetici', 'yonetici');
    const user = await preparePerson(admin, 'e2e.sozluk.kullanici', 'Sözlük Kullanıcı', 'kullanici');
    people.push(manager, user);

    // The ordinary user keeps the main screen open and has no dictionary page or endpoint.
    const home = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(home, user);
    await home.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    assert.equal((await api(home, 'GET', '/dictionary')).status, 403);
    const before = (await api(home, 'GET', '/status')).body;
    await home.goto(baseUrl + '/admin/sozluk');
    await home.getByRole('heading', {name: message('access.forbidden.title')}).waitFor();
    assert.equal(await home.getByRole('heading', {name: message('dictionary.tables.title').split(' ·')[0]}).count(), 0);
    await home.goto(baseUrl + '/');
    await home.locator('#hud-count').filter({hasText: String(before.objects)}).waitFor();

    const page = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(page, manager);
    const first = (await api(page, 'GET', '/dictionary')).body.active.version;

    // The upload and the template answer no more, whoever asks.
    assert.ok([404, 405].includes((await api(page, 'POST', '/dictionary/imports')).status));
    assert.ok([404, 405].includes((await api(page, 'GET', '/dictionary/template')).status));

    // A second dictionary becomes the active version.
    await seedDictionary(page, SECOND);
    const state = (await api(page, 'GET', '/dictionary')).body;
    assert.notEqual(state.active.version, first);
    assert.equal(state.previous.version, first, 'the version before is kept as the previous one');

    // Sözlük shows the counts and the warnings; a table opens by its address.
    await page.goto(baseUrl + '/admin/sozluk');
    await page.getByText(message('dictionary.info.version')).first().waitFor();
    await page.waitForLoadState('networkidle');
    const pageText = await page.locator('main').innerText();
    assert.ok(pageText.includes((before.objects + 1).toLocaleString('tr-TR')), 'the table count');
    if (state.active.warning_count) {
      assert.ok(pageText.includes(message('dictionary.info.warnings').split(' {count}')[0]), 'the warnings line');
    }
    await page.goto(baseUrl + '/admin/sozluk/' + encodeURIComponent(ADDED_TABLE));
    await page.getByRole('dialog').filter({hasText: 'vE2eEkTablo'}).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('button', {name: /önceki sürüme dön/i}).count(), 0, 'no button to go back');

    // The open main screen shows the new column count and draws the new table at the next status
    // poll (every 60 seconds) after the new index serves; two polls are allowed for the index build.
    await home.locator('#hud-count').filter({hasText: String(before.objects + 1)}).waitFor({timeout: 130000});
    const pill = await home.locator('#status .pill').getAttribute('title');
    assert.ok(pill.includes((before.columns + 3).toLocaleString('tr-TR')), 'the pill names the new column count');
    await home.locator('#q').fill('vE2eEkTablo');
    await home.locator('#q').press('Enter');
    await home.locator('#dossier.on #ds-path').filter({hasText: ADDED_TABLE}).waitFor();
    await home.keyboard.press('Escape');

    // The export gives the active version back.
    const download = page.waitForEvent('download');
    await page.getByRole('button', {name: message('dictionary.export.button')}).click();
    const exported = await readFile(await (await download).path());
    assert.ok(workbookText(exported).includes('vE2eEkTablo'), 'the export carries the new table');

    // One more version: the version before becomes the previous one.
    await seedDictionary(page, ORIGINAL);
    const last = (await api(page, 'GET', '/dictionary')).body;
    assert.equal(last.previous.version, state.active.version);
    await home.locator('#hud-count').filter({hasText: String(before.objects)}).waitFor({timeout: 130000});
  } finally {
    // The original synthetic dictionary is active again whatever happened above.
    await seedDictionary(admin, ORIGINAL);
    await retirePeople(admin, people);
  }
});
