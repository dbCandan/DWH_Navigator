import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, readAccessToken, readUser, subscribeAuth, writeSession} from './authStorage';
import type {AuthenticatedUser} from '@/types/auth';

const user = {username: 'ad.soyad', tenant_id: 'tenant-1'} as AuthenticatedUser;

describe('session store (user-accounts Requirement 6)', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => clearAuth());

  it('keeps the token and the user in memory only', () => {
    writeSession('token', user);
    expect(readAccessToken()).toBe('token');
    expect(readUser()).toEqual(user);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).toBe('');
  });

  it('tells subscribers about a new session and its end, once each', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuth(listener);
    writeSession('token', user);
    clearAuth();
    clearAuth();
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    writeSession('token', user);
    expect(listener).toHaveBeenCalledTimes(2);
    expect(readAccessToken()).toBe('token');
  });
});
