import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {api} from './people.mjs';

const STACK = fileURLToPath(new URL('../../scripts/stack.sh', import.meta.url));

/**
 * The product has no dictionary upload (dictionary-sync Requirement 13): a scenario writes its
 * synthetic dictionary with the backend's test-only seeder on the local stack, then rebuilds the
 * search index through the API as the signed-in page. The workbook goes in through standard input.
 */
export async function seedDictionary(page, file) {
  const seeded = spawnSync(
    'sh',
    [STACK, 'exec', '-T', 'backend', 'python', '-m', 'tests.dictionary_seed', '-'],
    {input: await readFile(file)},
  );
  assert.equal(seeded.status, 0, String(seeded.stderr));
  const rebuilt = await api(page, 'POST', '/search-index/rebuilds');
  assert.equal(rebuilt.status, 200, JSON.stringify(rebuilt.body));
}
