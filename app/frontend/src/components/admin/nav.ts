import type {IconName} from './Icon';

/** The admin screen's pages and their addresses (search-settings Requirement 20 and 21). */
export type AdminPageId =
  | 'genel'
  | 'analizler'
  | 'llm-kayitlari'
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
  {id: 'llm-kayitlari', icon: 'file'},
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

/** A dictionary table's deep link: `/admin/sozluk/<DB.Şema.Obje>` (search-settings Requirement 20). */
export const dictionaryTablePath = (key: string) => `${adminPath('sozluk')}/${encodeURIComponent(key)}`;

/**
 * The drawer the command palette's "Yeni model entegrasyonu" and "Model envanteri" open on the AI
 * page (search-settings Requirement 25); it travels in the address's navigation state.
 */
export type AiDrawerRequest = 'editor' | 'inventory';

/** An analysis record's deep link: `/admin/analizler/<public_id>` (search-settings Requirement 20). */
export const analysisPath = (publicId: string) => `${adminPath('analizler')}/${encodeURIComponent(publicId)}`;

/**
 * The drawer the command palette's "Performans ayrıntıları" opens on the Analizler page
 * (analysis-records Requirement 21); it travels in the address's navigation state.
 */
export type RecordsDrawerRequest = 'performance';
