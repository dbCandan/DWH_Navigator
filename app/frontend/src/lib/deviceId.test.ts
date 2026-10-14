import {afterEach, describe, expect, it, vi} from 'vitest';
import {deviceId, forgetDeviceIdForTests} from './deviceId';

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('device id (application-foundation 003-anonymous-visitor Requirement 2, Decision 1)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    forgetDeviceIdForTests();
  });

  it('is made once as a random UUID 4 and kept in the browser', () => {
    const first = deviceId();
    expect(first).toMatch(UUID4);
    expect(localStorage.getItem('dwhnavigator.device')).toBe(first);
    forgetDeviceIdForTests();
    expect(deviceId()).toBe(first);
  });

  it('replaces a stored value that is not a UUID 4', () => {
    localStorage.setItem('dwhnavigator.device', 'kisi');
    expect(deviceId()).toMatch(UUID4);
  });

  it('stays in memory for the page when the browser storage is closed', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const first = deviceId();
    expect(first).toMatch(UUID4);
    expect(deviceId()).toBe(first);
  });
});
