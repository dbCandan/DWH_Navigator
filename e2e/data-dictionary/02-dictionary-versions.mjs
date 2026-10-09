import {readFile} from 'node:fs/promises';
import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';

// dictionary-management Acceptance 4 (Requirement 7, 8, 13-15) and the map part of
// dictionary-explorer Acceptance 3 (Requirement 2, 16): a manager drops a second synthetic workbook
// on Genel bakış, sees the counts and the warnings, opens a table by its address, exports and
// re-imports the dictionary unchanged, is refused a workbook off the template, and after one more
// import the previous version is the one before, with no button to go back. An ordinary user gets
// no Sözlük page and 403 from /dictionary, and the open main screen shows the new column count and
// draws the new tables within a status poll. The original synthetic dictionary is imported back.
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const ORIGINAL = new URL('../../app/backend/tests/fixtures/parity/sozluk_sentetik.xlsx', import.meta.url);
const SECOND = new URL('../fixtures/sozluk_sentetik_ek.xlsx', import.meta.url);
const OFF_TEMPLATE = new URL('../fixtures/liste_on_terim.xlsx', import.meta.url);
const ADDED_TABLE = 'SYNDM.E2E.vE2eEkTablo';

/** Drop a workbook on the admin page, accept the replace question and wait for the toast. */
async function drop(page, file, name, toast) {
  const bytes = [...(await readFile(file))];
  const transfer = await page.evaluateHandle(
    ({bytes, name, type}) => {
      const data = new DataTransfer();
      data.items.add(new File([new Uint8Array(bytes)], name, {type}));
      return data;
    },
    {bytes, name, type: XLSX},
  );
  page.once('dialog', (dialog) => dialog.accept());
  await page.dispatchEvent('body', 'dragenter', {dataTransfer: transfer});
  await page.dispatchEvent('body', 'drop', {dataTransfer: transfer});
  await page.locator('.toast').filter({hasText: toast}).first().waitFor({timeout: 120000});
}

await withBrowser('dictionary versions, roles and the map after an import', async ({page: admin, assert, open}) => {
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

    // A second workbook dropped on Genel bakış becomes the active version.
    await page.goto(baseUrl + '/admin');
    await page.getByRole('heading', {level: 1, name: message('admin.page.genel.label')}).waitFor();
    await page.waitForLoadState('networkidle');
    await drop(page, SECOND, 'sozluk_sentetik_ek.xlsx', message('dictionary.import.done'));
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

    // Exported and imported unchanged: "Sözlük değişmedi" and the same version.
    const download = page.waitForEvent('download');
    await page.getByRole('button', {name: message('dictionary.export.button')}).click();
    const exported = await (await download).path();
    await drop(page, exported, 'disa-aktarilan.xlsx', message('dictionary.import.unchanged'));
    assert.equal((await api(page, 'GET', '/dictionary')).body.active.version, state.active.version);

    // A workbook off the template is refused and the dictionary stays.
    await drop(page, OFF_TEMPLATE, 'liste.xlsx', message('dictionary.import.failed'));
    assert.equal((await api(page, 'GET', '/dictionary')).body.active.version, state.active.version);

    // One more import: the version before becomes the previous one.
    await drop(page, ORIGINAL, 'sozluk_sentetik.xlsx', message('dictionary.import.done'));
    const last = (await api(page, 'GET', '/dictionary')).body;
    assert.equal(last.previous.version, state.active.version);
    await home.locator('#hud-count').filter({hasText: String(before.objects)}).waitFor({timeout: 130000});
  } finally {
    // The original synthetic dictionary is active again whatever happened above.
    const bytes = await readFile(ORIGINAL);
    await api(admin, 'POST', '/dictionary/imports', undefined, {name: 'sozluk_sentetik.xlsx', type: XLSX, bytes});
    await retirePeople(admin, people);
  }
});
