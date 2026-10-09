import {render} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import App from '@/App';
import {AuthProvider} from '@/contexts/AuthContext';
import {IntlProvider} from '@/contexts/IntlContext';
import {writeSession} from '@/lib/authStorage';
import messages from '@/locales/tr.json';
import type {AuthenticatedUser} from '@/types/auth';
import {Where} from './Where';

/** A catalog message, so tests follow the configured texts. */
export function message(key: string, values: Record<string, string | number> = {}): string {
  const value = (messages as Record<string, string>)[key];
  if (typeof value !== 'string') throw new Error(`missing catalog key ${key}`);
  return value.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? `{${name}}`));
}

type Role = Pick<AuthenticatedUser, 'role' | 'roles' | 'is_super_admin'>;

export const ROLES: Record<'super' | 'manager' | 'user', Role> = {
  super: {role: 'super_admin', roles: ['super_admin'], is_super_admin: true},
  manager: {role: 'yonetici', roles: ['yonetici'], is_super_admin: false},
  user: {role: 'kullanici', roles: ['kullanici'], is_super_admin: false},
};

export function signedIn(kind: keyof typeof ROLES, name = 'Ayşe Yılmaz'): AuthenticatedUser {
  const user: AuthenticatedUser = {
    public_id: '00000000-0000-4000-8000-000000000001',
    username: 'ayse.yilmaz',
    display_name: name,
    tenant_id: '00000000-0000-4000-8000-0000000000aa',
    permissions: [],
    ...ROLES[kind],
  };
  writeSession('token', user);
  return user;
}

/** The whole application at an address, with its providers. */
export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <IntlProvider>
        <AuthProvider>
          <App />
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
        </AuthProvider>
      </IntlProvider>
    </MemoryRouter>,
  );
}
