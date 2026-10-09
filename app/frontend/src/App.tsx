import {lazy, Suspense} from 'react';
import {Navigate, Route, Routes} from 'react-router';
import {AuthGuard} from '@/components/auth/AuthGuard';
import {RequireAccess} from '@/components/auth/RequireAccess';
import {GeneratedRoutes} from '@/generated/routes';
import LoginPage from '@/pages/LoginPage';
import NotFoundPage from '@/pages/NotFoundPage';

// Screens load lazily (rules/30); the sign-in screen and "not found" ship with the entry.
const ExplorerPage = lazy(() => import('@/pages/ExplorerPage'));
const PasswordChangePage = lazy(() => import('@/pages/PasswordChangePage'));
const AdminShell = lazy(() => import('@/components/admin/AdminShell').then((m) => ({default: m.AdminShell})));
const OverviewPage = lazy(() => import('@/pages/admin/OverviewPage'));
const AnalysesPage = lazy(() => import('@/pages/admin/AnalysesPage'));
const UsersPage = lazy(() => import('@/pages/admin/UsersPage'));
const AiPage = lazy(() => import('@/pages/admin/AiPage'));
const DictionaryPage = lazy(() => import('@/pages/admin/DictionaryPage'));
const VocabularyPage = lazy(() => import('@/pages/admin/VocabularyPage'));
const SearchSettingsPage = lazy(() => import('@/pages/admin/SearchSettingsPage'));
const MaintenancePage = lazy(() => import('@/pages/admin/MaintenancePage'));

/**
 * The application's addresses: the main screen at `/`, the admin screen under `/admin`
 * (`yonetici` and the super admin; search-settings Requirement 20), the account screens.
 * Item addresses (`/admin/analizler/<public_id>`, `/admin/sozluk/<DB.Şema.Obje>`) open their
 * page; an unknown `/admin/...` address is "not found".
 */
export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AuthGuard />}>
          <Route path="/" element={<ExplorerPage />} />
          <Route path="/parola" element={<PasswordChangePage />} />
          <Route path="/admin" element={<RequireAccess need="administer" />}>
            <Route element={<AdminShell />}>
              <Route index element={<Navigate to="genel" replace />} />
              <Route path="genel" element={<OverviewPage />} />
              <Route path="analizler/:analysisId?" element={<AnalysesPage />} />
              <Route path="sozluk/*" element={<DictionaryPage />} />
              <Route path="kelimeler" element={<VocabularyPage />} />
              <Route path="yapay-zeka" element={<AiPage />} />
              <Route path="arama" element={<SearchSettingsPage />} />
              <Route path="bakim" element={<MaintenancePage />} />
              <Route
                path="kullanicilar"
                element={
                  <RequireAccess need="manageUsers">
                    <UsersPage />
                  </RequireAccess>
                }
              />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          {GeneratedRoutes}
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
