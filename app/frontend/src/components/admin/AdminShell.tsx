import {Suspense, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Link, NavLink, Outlet, useLocation, useNavigate} from 'react-router';
import {AdminLogo} from '@/components/brand/AdminLogo';
import {PersonIcon} from '@/components/auth/PersonIcon';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useDownload, useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useLlmState} from '@/hooks/useLlmState';
import {useSearchState} from '@/hooks/useSearchState';
import {useSurface} from '@/hooks/useSurface';
import {useVocabularyDraft} from '@/hooks/useVocabularyDraft';
import {dictionaryStatus, indexStatus, type IndexStatus} from '@/lib/adminStatus';
import {formatNumber, formatWhen} from '@/lib/format';
import {modelStatus, type ModelStatus} from '@/lib/modelStatus';
import type {PaletteEntry} from '@/lib/paletteSearch';
import {changedKeys, settingFields, type SettingField} from '@/lib/settingsDraft';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {DictionaryService} from '@/services/dictionary';
import type {RecordRow} from '@/types/records';
import {CommandPalette} from './CommandPalette';
import {DictionaryStateProvider} from './DictionaryStateProvider';
import {Icon} from './Icon';
import {LlmStateProvider} from './LlmStateProvider';
import {
  adminPath,
  analysisPath,
  dictionaryTablePath,
  NAV,
  NAV_PAGES,
  type AdminPageId,
  type AiDrawerRequest,
  type RecordsDrawerRequest,
} from './nav';
import {SaveBar} from './SaveBar';
import {SearchStateProvider} from './SearchStateProvider';
import {ToastProvider} from './Toasts';
import {VocabularyDraftProvider} from './VocabularyDraftProvider';
import './admin.css';
import './session.css';

/** The palette's "Son sorular": the newest 200 finished records (search-settings Requirement 22). */
const PALETTE_RECENT = 200;

/** The page id of an admin address (`/admin/sozluk/DB.Şema.Obje` → `sozluk`). */
function pageOf(pathname: string): AdminPageId | null {
  const id = pathname.split('/')[2] ?? '';
  return NAV_PAGES.some((page) => page.id === id) ? (id as AdminPageId) : null;
}

const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName);

/** The system status's light for a state (admin.html Shell.refresh led()). */
const led = (state: ModelStatus['state']) => (state === 'ok' ? 'ok' : state === 'down' ? 'bad' : state === 'unknown' ? '' : 'warn');

/** The AI page's menu badge: the model state's dot (llm-connection Requirement 19). */
const modelBadge = (state: ModelStatus['state']) =>
  state === 'ok' ? 'ok' : state === 'down' ? 'bad' : state === 'none' ? 'warn' : null;

const INDEX_LINE: Record<IndexStatus, string> = {
  ok: 'admin.sys.indexOk',
  building: 'admin.sys.indexBuilding',
  stale: 'admin.sys.indexStale',
  empty: 'admin.sys.indexEmpty',
  unknown: 'admin.sys.indexPending',
};

interface Badge {
  kind: 'ok' | 'warn' | 'bad' | 'count';
  text: string;
  title: string;
}

/** A menu item's badge (admin.html Shell.badge): a dot without text, else the text. */
function MenuBadge({badge}: {badge: Badge | null}) {
  if (!badge) return null;
  return (
    <span className={`bdg ${badge.kind}${badge.text ? '' : ' dot'}`} title={badge.title}>
      {badge.text}
    </span>
  );
}

/**
 * Bring a setting into view (search-settings Requirement 22; admin.html Settings.focus): open its
 * page, unfold its section, centre and flash its row and focus its control. The page may still be
 * loading, so the row is looked for a few times.
 */
function focusSettingRow(key: string) {
  let tries = 0;
  const find = () => {
    const row = document.getElementById('row-' + key);
    if (!row) {
      if (++tries < 40) window.setTimeout(find, 75);
      return;
    }
    const fold = row.closest('details');
    if (fold) fold.open = true;
    row.scrollIntoView?.({block: 'center', behavior: 'smooth'});
    row.classList.remove('flash');
    void row.offsetWidth;
    row.classList.add('flash');
    row.querySelector<HTMLElement>('input, select')?.focus({preventScroll: true});
  };
  window.setTimeout(find, 60);
}

/**
 * The admin screen's shell (search-settings Requirement 20-22, 24, 25): the sidebar with the
 * brand, "Ara veya git…", the menu in three groups, the system status, the session area and
 * "← Uygulamaya dön"; the page; the notices; the command palette (Ctrl K / Cmd K). A page change
 * closes an open drawer and scrolls to the top. Hiding a menu item is not authorization.
 */
export function AdminShell() {
  useSurface('admin');
  return (
    <ToastProvider>
      <LlmStateProvider>
        <SearchStateProvider>
          <DictionaryStateProvider>
            <VocabularyDraftProvider>
              <ShellLayout />
            </VocabularyDraftProvider>
          </DictionaryStateProvider>
        </SearchStateProvider>
      </LlmStateProvider>
    </ToastProvider>
  );
}

function ShellLayout() {
  const {t} = useIntl();
  const {user, access, logout} = useAuth();
  const {llm, reload: reloadLlm} = useLlmState();
  const {settings, form, index, reloadSettings, reloadIndex} = useSearchState();
  const {dictionary, tables, reload: reloadDictionary} = useDictionaryState();
  const vocabulary = useVocabularyDraft();
  const rebuild = useIndexRebuild();
  const download = useDownload();
  const location = useLocation();
  const navigate = useNavigate();
  const page = pageOf(location.pathname);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [whoOpen, setWhoOpen] = useState(false);
  const [recent, setRecent] = useState<RecordRow[]>([]);
  const menu = useRef<HTMLElement>(null);
  const pages = useMemo(() => NAV_PAGES.filter((item) => !item.superAdmin || access.manageUsers), [access.manageUsers]);

  const model = modelStatus(llm, t);
  const dict = dictionaryStatus(dictionary);
  const ix = indexStatus(index);
  const fields = useMemo(() => (settings ? settingFields(settings) : new Map<string, SettingField>()), [settings]);
  const changedByPage = useMemo(() => {
    const counts: Partial<Record<AdminPageId, number>> = {};
    if (settings)
      for (const key of changedKeys(settings, form)) {
        const owner = fields.get(key)?.page as AdminPageId | undefined;
        if (owner) counts[owner] = (counts[owner] ?? 0) + 1;
      }
    return counts;
  }, [settings, form, fields]);
  const unsaved = Object.keys(changedByPage).length > 0 || vocabulary.dirty('terms') || vocabulary.dirty('stopwords');

  // The states are read when the shell opens and on every page change (search-settings Requirement 21).
  useEffect(() => {
    void reloadLlm();
    void reloadSettings();
    void reloadIndex();
    void reloadDictionary();
  }, [page, reloadLlm, reloadSettings, reloadIndex, reloadDictionary]);

  // Closing or reloading the tab with unsaved settings or word lists asks first (Requirement 23).
  useEffect(() => {
    if (!unsaved) return;
    const ask = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', ask);
    return () => window.removeEventListener('beforeunload', ask);
  }, [unsaved]);

  /** Leaving the admin screen with unsaved changes asks first; moving between its pages does not. */
  const mayLeave = useCallback(() => !unsaved || window.confirm(t('admin.leave.confirm')), [unsaved, t]);

  useDocumentTitle(
    page ? t('admin.documentTitle', {page: t(`admin.page.${page}.label`)}) : t('admin.documentTitleFallback'),
  );

  useEffect(() => {
    document.getElementById('main')?.scrollTo?.(0, 0);
    window.scrollTo(0, 0);
    const current = page ? document.getElementById('nav-' + page) : null;
    const list = menu.current;
    // Narrow screens: the menu scrolls sideways; keep the current page in view.
    if (current && list && list.scrollWidth > list.clientWidth)
      current.scrollIntoView({inline: 'center', block: 'nearest'});
  }, [page]);

  // Narrow screens: the session box opens from the person icon; outside or Esc closes it.
  useEffect(() => {
    if (!whoOpen) return;
    const outside = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest('.who, .who-toggle')) setWhoOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setWhoOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [whoOpen]);

  const togglePalette = useCallback(() => setPaletteOpen((open) => !open), []);

  // The newest questions are read whenever the palette opens; an unreadable list leaves the group out.
  useEffect(() => {
    if (!paletteOpen) return;
    let current = true;
    AnalysisRecordsService.list({period: 'all'}, 1, undefined, PALETTE_RECENT).then(
      (page) => current && setRecent(page.items),
      () => current && setRecent([]),
    );
    return () => {
      current = false;
    };
  }, [paletteOpen]);

  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && (event.key === 'k' || event.key === 'K')) {
        event.preventDefault();
        togglePalette();
        return;
      }
      // "/" goes to the page's search field when no field, palette or drawer has the keyboard.
      if (event.key === '/' && !typing(event.target) && !document.querySelector('.palette, .drawer')) {
        const search = document.querySelector<HTMLInputElement>('#main input[type=search]');
        if (search) {
          event.preventDefault();
          search.focus();
        }
      }
    };
    window.addEventListener('keydown', keyDown);
    return () => window.removeEventListener('keydown', keyDown);
  }, [togglePalette]);

  const entries = useMemo<PaletteEntry[]>(() => {
    const pageGroup = t('admin.palette.pages');
    const actionGroup = t('admin.palette.actions');
    const openOnAiPage = (open: AiDrawerRequest) => navigate(adminPath('yapay-zeka'), {state: {open}});
    const openOnAnalyses = (open: RecordsDrawerRequest) => navigate(adminPath('analizler'), {state: {open}});
    return [
      ...pages.map((item) => ({
        groupId: 'pages',
        group: pageGroup,
        icon: item.icon,
        title: t(`admin.page.${item.id}.label`),
        subtitle: t(`admin.page.${item.id}.tip`),
        run: () => navigate(adminPath(item.id)),
      })),
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'export' as const,
        title: t('admin.palette.exportDictionary'),
        subtitle: t('admin.palette.exportDictionaryTip'),
        run: () => void download(DictionaryService.exportWorkbook),
      },
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'refresh' as const,
        title: t('admin.palette.rebuild'),
        subtitle: t('admin.palette.rebuildTip'),
        run: () => void rebuild(),
      },
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'plus' as const,
        title: t('admin.palette.newIntegration'),
        subtitle: t('admin.palette.newIntegrationTip'),
        run: () => openOnAiPage('editor'),
      },
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'list' as const,
        title: t('admin.palette.inventory'),
        subtitle: t('admin.palette.inventoryTip'),
        run: () => openOnAiPage('inventory'),
      },
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'gauge' as const,
        title: t('admin.palette.performance'),
        subtitle: t('admin.palette.performanceTip'),
        run: () => openOnAnalyses('performance'),
      },
      {
        groupId: 'actions',
        group: actionGroup,
        icon: 'arrow' as const,
        title: t('admin.palette.backToApp'),
        subtitle: t('admin.palette.backToAppTip'),
        run: () => {
          if (mayLeave()) navigate('/');
        },
      },
      ...[...fields.values()].map((field) => ({
        groupId: 'settings',
        group: t('admin.palette.settings'),
        icon: 'sliders' as const,
        title: field.label,
        subtitle: t(field.help ? 'admin.palette.settingTipHelp' : 'admin.palette.settingTip', {
          page: t(`admin.page.${field.page}.label`),
          section: field.section,
          help: field.help,
        }),
        run: () => {
          navigate(adminPath(field.page));
          focusSettingRow(field.key);
        },
      })),
      ...(dict.active && tables
        ? tables.map((table) => ({
            groupId: 'tables',
            group: t('admin.palette.tables'),
            icon: 'db' as const,
            title: table.name,
            subtitle: t('admin.palette.tableTip', {
              where: table.group || table.key.split('.').slice(0, 2).join('.'),
              columns: table.columns,
            }),
            run: () => navigate(dictionaryTablePath(table.key)),
          }))
        : []),
      ...recent.map((row) => ({
        groupId: 'recent',
        group: t('admin.palette.recent'),
        icon: 'chart' as const,
        title: row.query,
        subtitle: t('admin.palette.recentTip', {
          when: formatWhen(row.asked_at, t),
          label: row.verdict || t(`records.flow.${row.flow}`),
        }),
        run: () => navigate(analysisPath(row.public_id)),
      })),
    ];
  }, [pages, navigate, t, download, rebuild, mayLeave, fields, dict.active, tables, recent]);

  const modelDot = modelBadge(model.state);
  const badges: Partial<Record<AdminPageId, Badge | null>> = {
    'yapay-zeka': modelDot ? {kind: modelDot, text: '', title: model.label} : null,
    sozluk: dict.state === 'none' ? {kind: 'warn', text: '!', title: t('admin.badge.noDictionary')} : null,
    arama: changedByPage.arama ? {kind: 'count', text: String(changedByPage.arama), title: t('admin.badge.unsaved')} : null,
    bakim: changedByPage.bakim
      ? {kind: 'count', text: String(changedByPage.bakim), title: t('admin.badge.unsaved')}
      : ix === 'stale'
        ? {kind: 'warn', text: '!', title: t('admin.badge.indexStale')}
        : null,
  };

  const name = user?.display_name || user?.username || '';
  return (
    <>
      <div className="app">
        <aside className="side">
          <Link className="brand" to={adminPath('genel')} aria-label={t('admin.page.genel.label')}>
            <AdminLogo />
            <span>
              <b>{t('admin.brand.name')}</b>
              <small>{t('admin.brand.tagline')}</small>
            </span>
          </Link>
          <button className="cmdk-open" id="cmdk-open" type="button" aria-label={t('admin.palette.open')} onClick={togglePalette}>
            <span>{t('admin.palette.button')}</span>
            <kbd>Ctrl K</kbd>
          </button>
          <nav className="menu" id="nav" aria-label={t('admin.nav.label')} ref={menu}>
            {NAV.map((entry) =>
              'group' in entry ? (
                <div className="grp" key={entry.group}>
                  {t(entry.group)}
                </div>
              ) : entry.superAdmin && !access.manageUsers ? null : (
                <NavLink
                  key={entry.id}
                  to={adminPath(entry.id)}
                  id={'nav-' + entry.id}
                  title={t(`admin.page.${entry.id}.tip`)}
                  className={() => undefined}
                >
                  <Icon name={entry.icon} />
                  <span className="lbl">{t(`admin.page.${entry.id}.label`)}</span>
                  <span className="nb">
                    <MenuBadge badge={badges[entry.id] ?? null} />
                  </span>
                </NavLink>
              ),
            )}
          </nav>
          <div className="side-foot">
            <div className="sys" id="sys" aria-live="polite">
              <div title={model.detail}>
                <i className={'led ' + led(model.state)} />
                <span>
                  {model.state === 'ok'
                    ? model.label
                    : model.state === 'down'
                      ? t('admin.sys.modelDown')
                      : model.state === 'none'
                        ? t('admin.sys.modelNone')
                        : t('admin.sys.modelPending')}
                </span>
              </div>
              <div>
                <i className={'led ' + (dict.state === 'ok' ? 'ok' : dict.state === 'unknown' ? '' : 'warn')} />
                <span>
                  {dict.state === 'none'
                    ? t('admin.sys.dictionaryNone')
                    : dict.active
                      ? t('admin.sys.dictionary', {
                          objects: formatNumber(dict.active.object_count),
                          columns: formatNumber(dict.active.column_count),
                        })
                      : t('admin.sys.dictionaryPending')}
                </span>
              </div>
              <div>
                <i className={'led ' + (ix === 'ok' ? 'ok' : ix === 'unknown' ? '' : 'warn')} />
                <span>{t(INDEX_LINE[ix])}</span>
              </div>
            </div>
            <button
              className="who-toggle"
              type="button"
              aria-expanded={whoOpen}
              aria-controls="who"
              aria-label={t('session.menu', {name})}
              onClick={() => setWhoOpen(!whoOpen)}
            >
              <PersonIcon />
            </button>
            <div className={'who' + (whoOpen ? ' open' : '')} id="who" title={name}>
              <div className="who-name">
                <PersonIcon />
                <span className="nm">{name}</span>
              </div>
              <div>
                <Link
                  className="who-act"
                  to="/parola"
                  state={{from: location.pathname}}
                  onClick={(event) => {
                    if (!mayLeave()) event.preventDefault();
                  }}
                >
                  {t('session.changePassword')}
                </Link>
                <span aria-hidden="true">·</span>
                <button
                  className="who-act"
                  type="button"
                  onClick={() => {
                    if (mayLeave()) void logout();
                  }}
                >
                  {t('session.signOut')}
                </button>
              </div>
            </div>
            <Link
              className="back"
              to="/"
              onClick={(event) => {
                if (!mayLeave()) event.preventDefault();
              }}
            >
              {t('admin.back')}
            </Link>
          </div>
        </aside>
        <main id="main">
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <svg width="0" height="0" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="gr-bar" x1="0" y1="1" x2="0" y2="0">
            <stop className="logo-stop-mid" offset="0" />
            <stop className="logo-stop-start" offset="1" />
          </linearGradient>
        </defs>
      </svg>
      <SaveBar />
      {paletteOpen && <CommandPalette entries={entries} onClose={() => setPaletteOpen(false)} />}
    </>
  );
}
