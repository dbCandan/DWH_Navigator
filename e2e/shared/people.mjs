import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {apiPrefix, signIn} from './harness.mjs';

/**
 * Public API calls from a signed-in page: a fresh access token comes from the page's own refresh
 * cookie, so the call acts as that person. Nothing is stored in the repository.
 */
export async function api(page, method, path, body, raw = null) {
  return page.evaluate(
    async ({prefix, method, path, body, raw}) => {
      const refreshed = await fetch(prefix + '/auth/refresh', {method: 'POST'});
      const session = await refreshed.json();
      const headers = {Authorization: 'Bearer ' + session.access_token, 'x-tenant-id': session.user.tenant_id};
      let payload;
      if (raw) {
        headers['Content-Type'] = raw.type;
        headers['X-Filename'] = encodeURIComponent(raw.name);
        payload = new Uint8Array(raw.bytes);
      } else if (body !== undefined) {
        headers['Content-Type'] = 'application/json';
        payload = JSON.stringify(body);
      }
      const response = await fetch(prefix + path, {method, headers, body: payload});
      const type = response.headers.get('content-type') || '';
      return {status: response.status, body: type.includes('json') ? await response.json() : null};
    },
    {prefix: apiPrefix, method, path, body, raw: raw && {...raw, bytes: [...raw.bytes]}},
  );
}

const newPassword = () => `${randomBytes(10).toString('hex')} gizli sozcuk`;

/**
 * An ordinary account for a scenario (rules/14: role-specific acceptance uses ordinary roles):
 * opened by the super admin, or reactivated with a new one-time password when an earlier run left
 * it. The account sets its own password at its first sign-in through the real form.
 */
export async function preparePerson(adminPage, username, displayName, role) {
  const found = await api(adminPage, 'GET', `/admin/users?q=${encodeURIComponent(username)}`);
  assert.equal(found.status, 200);
  const known = found.body.items.find((user) => user.username === username);
  let oneTime;
  let publicId;
  if (known) {
    publicId = known.public_id;
    assert.equal((await api(adminPage, 'PUT', `/admin/users/${publicId}/active`, {active: true})).status, 200);
    assert.equal((await api(adminPage, 'PUT', `/admin/users/${publicId}/role`, {role})).status, 200);
    const reset = await api(adminPage, 'POST', `/admin/users/${publicId}/password-reset`);
    assert.equal(reset.status, 200);
    oneTime = reset.body.one_time_password;
  } else {
    const created = await api(adminPage, 'POST', '/admin/users', {username, display_name: displayName, role});
    assert.equal(created.status, 201);
    publicId = created.body.user.public_id;
    oneTime = created.body.one_time_password;
  }
  return {username, password: oneTime, newPassword: newPassword(), publicId};
}

/** Clean-up through the public API: the scenario's accounts are deactivated. */
export async function retirePeople(adminPage, people) {
  for (const person of people) {
    if (person?.publicId) await api(adminPage, 'PUT', `/admin/users/${person.publicId}/active`, {active: false});
  }
}

/** Sign a prepared person in; after the first sign-in the chosen password is the password. */
export async function signInPerson(page, person) {
  if (await signIn(page, person)) person.password = person.newPassword;
}
