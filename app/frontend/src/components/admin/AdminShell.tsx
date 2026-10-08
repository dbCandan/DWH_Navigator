import {Suspense, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Link, NavLink, Outlet, useLocation, useNavigate} from 'react-router';
import {AdminLogo} from '@/components/brand/AdminLogo';
import {PersonIcon} from '@/components/auth/PersonIcon';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useLlmState} from '@/hooks/useLlmState';
import {useSurface} from '@/hooks/useSurface';
import {modelStatus, type ModelStatus} from '@/lib/modelStatus';
import type {PaletteEntry} from '@/lib/paletteSearch';
import {CommandPalette} from './CommandPalette';
import {Icon} from './Icon';
import {LlmStateProvider} from './LlmStateProvider';
import {adminPath, NAV, NAV_PAGES, type AdminPageId, type AiDrawerRequest} from './nav';
import {ToastProvider} from './Toasts';
import './admin.css';
import './session.css';

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
        <ShellLayout />
      </LlmStateProvider>
    </ToastProvider>
  );
}

function ShellLayout() {
  const {t} = useIntl();
  const {user, access, logout} = useAuth();
  const {llm, reload: reloadLlm} = useLlmState();
  const location = useLocation();
  const navigate = useNavigate();
  const page = pageOf(location.pathname);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [whoOpen, setWhoOpen] = useState(false);
  const menu = useRef<HTMLElement>(null);
  const pages = useMemo(() => NAV_PAGES.filter((item) => !item.superAdmin || access.manageUsers), [access.manageUsers]);

  const model = modelStatus(llm, t);

  // The states are read when the shell opens and on every page change (search-settings Requirement 21).
  useEffect(() => {
    void reloadLlm();
  }, [page, reloadLlm]);

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
        icon: 'arrow' as const,
        title: t('admin.palette.backToApp'),
        subtitle: t('admin.palette.backToAppTip'),
        run: () => navigate('/'),
      },
    ];
  }, [pages, navigate, t]);

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
                    {entry.id === 'yapay-zeka' && modelBadge(model.state) ? (
                      <span className={`bdg ${modelBadge(model.state)} dot`} title={model.label} />
                    ) : null}
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
                <i className="led" />
                <span>{t('admin.sys.dictionaryPending')}</span>
              </div>
              <div>
                <i className="led" />
                <span>{t('admin.sys.indexPending')}</span>
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
                <Link className="who-act" to="/parola" state={{from: location.pathname}}>
                  {t('session.changePassword')}
                </Link>
                <span aria-hidden="true">·</span>
                <button className="who-act" type="button" onClick={() => void logout()}>
                  {t('session.signOut')}
                </button>
              </div>
            </div>
            <Link className="back" to="/">
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
      {paletteOpen && <CommandPalette entries={entries} onClose={() => setPaletteOpen(false)} />}
    </>
  );
}
