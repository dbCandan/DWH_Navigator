import type {IconName} from './Icon';

/** The admin screen's pages and their addresses (search-settings Requirement 20 and 21). */
export type AdminPageId =
  | 'genel'
  | 'analizler'
  | 'sozluk'
  | 'kelimeler'
  | 'yapay-zeka'
  | 'arama'
  | 'bakim'
  | 'kullanicilar';

export interface NavPage {
  id: AdminPageId;
  icon: IconName;
  /** Shown to the super admin only (user-accounts Requirement 16). */
  superAdmin?: boolean;
}

export type NavEntry = {group: string} | NavPage;

/**
 * The menu in three groups, as the source (admin.html NAV). Labels, tooltips and page
 * descriptions are catalog messages: `admin.page.<id>.label`, `.tip` and `.description`.
 */
export const NAV: readonly NavEntry[] = [
  {group: 'admin.nav.monitoring'},
  {id: 'genel', icon: 'home'},
  {id: 'analizler', icon: 'chart'},
  {group: 'admin.nav.data'},
  {id: 'sozluk', icon: 'book'},
  {id: 'kelimeler', icon: 'list'},
  {id: 'yapay-zeka', icon: 'spark'},
  {group: 'admin.nav.settings'},
  {id: 'arama', icon: 'sliders'},
  {id: 'bakim', icon: 'wrench'},
  {id: 'kullanicilar', icon: 'users', superAdmin: true},
];

export const NAV_PAGES: readonly NavPage[] = NAV.filter((entry): entry is NavPage => 'id' in entry);

export const adminPath = (id: AdminPageId) => `/admin/${id}`;
