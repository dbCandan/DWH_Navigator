import {mkdir} from 'node:fs/promises';
import {accounts, baseUrl, message, signIn, withBrowser} from '../shared/harness.mjs';
import {api, preparePerson, retirePeople, signInPerson} from '../shared/people.mjs';

// dictionary-explorer Acceptance 3 (Requirement 1, 2, 7-9, 12-15) and question-analysis Task 13 on
// the local stack: the map counts the galaxy endpoint's tables and clusters, a typed table name
// opens its file from the keyboard without an analysis, the column search and the filters work,
// the focus ring shows only for keyboard focus, Esc gives the focus back to the bar, a name in two
// schemas is asked as a question, a question draws the voyage and the result constellation, the
// map keeps moving, the compass turns and a kept answer still waits for the radar with "reduce
// motion" (Requirement 8, Decision 8), and neither role sees a link
// to the admin screen. The map rebuilt after another import is in 02-dictionary-versions.mjs.
const QUESTION = 'Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?';

await withBrowser('main screen map, table file by keyboard, voyage and roles', async ({page: admin, assert, open}) => {
  await signIn(admin, accounts.superAdmin);
  const people = [];
  try {
    const user = await preparePerson(admin, 'e2e.gezgin.kullanici', 'Gezgin Kullanıcı', 'kullanici');
    const manager = await preparePerson(admin, 'e2e.gezgin.yonetici', 'Gezgin Yönetici', 'yonetici');
    people.push(user, manager);

    const page = await open({viewport: {width: 1440, height: 900}});
    await signInPerson(page, user);
    await page.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    const field = page.getByRole('textbox', {name: message('explorer.search.label')});

    // The HUD counts the galaxy endpoint's tables and clusters.
    const galaxy = (await api(page, 'GET', '/explorer/galaxy')).body;
    const clusters = new Set(galaxy.items.map((table) => table.group)).size;
    const count = message('explorer.hud.count').replace('{tables}', galaxy.total).replace('{clusters}', clusters);
    await page.locator('#hud-count').filter({hasText: count}).waitFor();

    // A typed table name opens its file; no analysis is recorded.
    const records = async () => (await api(admin, 'GET', '/analysis-records?period=all')).body.total;
    const before = await records();
    const unique = galaxy.items.find((table) => galaxy.items.filter((t) => t.name === table.name).length === 1 && table.columns > 3);
    await field.focus();
    await page.keyboard.type(unique.name);
    await page.keyboard.press('Enter');
    const dossier = page.locator('#dossier.on');
    await dossier.waitFor();
    await page.locator('#ds-path').filter({hasText: unique.key}).waitFor();
    await page.locator('#ds-list .ds-col').first().waitFor();
    const close = page.getByRole('button', {name: message('dossier.close')});
    assert.equal(await close.evaluate((el) => el === document.activeElement), true, 'the focus goes to "Kapat"');
    assert.equal(await records(), before, 'a table name is not analysed');
    assert.equal(await field.inputValue(), unique.name, 'the name stays in the bar');

    // "/" goes to the column search; a filter is chosen from the keyboard.
    await page.keyboard.press('/');
    const search = page.getByRole('searchbox', {name: message('dossier.searchLabel')});
    assert.equal(await search.evaluate((el) => el === document.activeElement), true);
    const total = await page.locator('#ds-list .ds-col').count();
    const firstColumn = (await page.locator('#ds-list .ds-cname').first().textContent()).trim();
    await page.keyboard.type(firstColumn.slice(0, 4).toLocaleUpperCase('tr-TR'));
    await page.locator('#ds-count').filter({hasText: '/'}).waitFor();
    assert.ok((await page.locator('#ds-list mark').count()) > 0, 'the matches are marked');
    await search.fill('');
    await page.locator('#ds-count').filter({hasText: new RegExp(`^${total}$`)}).waitFor();
    const filterAll = page.getByRole('button', {name: new RegExp(`^${message('dossier.filterAll')} · `)});
    assert.equal(await filterAll.getAttribute('aria-pressed'), 'true');

    // The focus ring shows for keyboard focus only.
    await page.keyboard.press('Tab');
    const ring = () => page.evaluate(() => document.activeElement?.matches(':focus-visible') ?? false);
    assert.equal(await ring(), true, 'keyboard focus is visible');
    const row = page.locator('#ds-list .ds-ctop').first();
    await row.focus();
    await page.keyboard.press('Enter');
    assert.equal(await row.getAttribute('aria-expanded'), 'true', 'Enter opens a column row');
    await page.locator('#ds-list .ds-col').nth(1).click();
    assert.equal(await ring(), false, 'a mouse click shows no focus ring');

    // Esc closes the file and gives the focus back to the bar.
    await page.keyboard.press('Escape');
    await page.locator('#dossier:not(.on)').waitFor({state: 'attached'});
    assert.equal(await field.evaluate((el) => el === document.activeElement), true, 'the focus is back on the bar');

    // A name in two schemas is a question.
    const twice = galaxy.items.find((table) => galaxy.items.filter((t) => t.name === table.name).length > 1);
    assert.ok(twice, 'the dictionary has a table name in two schemas');
    await field.fill(twice.name);
    await field.press('Enter');
    await page.getByRole('button', {name: message('explorer.search.stop')}).or(page.locator('.ans')).first().waitFor();
    assert.equal(await page.locator('#dossier.on').count(), 0);
    await page.locator('.ans, .stopped, .error').first().waitFor({timeout: 180000});

    // A question: the voyage and then the result constellation (screenshots for the eye).
    await mkdir('test-results', {recursive: true});
    await field.fill(QUESTION);
    await field.press('Enter');
    await page.waitForTimeout(2500);
    await page.screenshot({path: 'test-results/explorer-voyage.png'});
    await page.locator('.ans').waitFor({timeout: 180000});
    await page.locator('#hud-focus').filter({hasText: /·/}).waitFor({state: 'attached'});
    await page.screenshot({path: 'test-results/explorer-constellation.png'});

    // "Reduce motion" changes nothing on the main screen: the map moves, the compass turns and the
    // kept answer waits for the radar's turn.
    const moving = await open({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
    await signInPerson(moving, user);
    await moving.getByText(message('explorer.status.ready'), {exact: true}).waitFor();
    const changes = () =>
      moving.evaluate(
        () =>
          new Promise((resolve) => {
            const canvas = document.getElementById('cosmos');
            const first = canvas.toDataURL();
            setTimeout(() => resolve(first !== canvas.toDataURL()), 1500);
          }),
      );
    assert.equal(await changes(), true, 'the map moves with "reduce motion"');
    const movingField = moving.getByRole('textbox', {name: message('explorer.search.label')});
    await movingField.fill(QUESTION);
    const asked = Date.now();
    await movingField.press('Enter');
    const needle = await moving.evaluate(() => getComputedStyle(document.querySelector('.compass .needle')).animationName);
    assert.equal(needle, 'seek', 'the compass turns with "reduce motion"');
    await moving.locator('.ans .src.reused').waitFor({timeout: 15000});
    assert.ok(Date.now() - asked >= 4000, 'a kept answer waits for the radar turn');

    // Neither role has a link to the admin screen.
    for (const person of [user, manager]) {
      const view = person === user ? page : await open();
      if (person !== user) await signInPerson(view, person);
      await view.goto(baseUrl + '/');
      await view.getByRole('heading', {name: message('explorer.hero.title')}).waitFor();
      const links = await view.locator('a[href]').evaluateAll((all) => all.map((a) => a.getAttribute('href')));
      assert.ok(!links.some((href) => /admin/.test(href)), `${person.username} sees no admin link`);
    }
  } finally {
    await retirePeople(admin, people);
  }
});
