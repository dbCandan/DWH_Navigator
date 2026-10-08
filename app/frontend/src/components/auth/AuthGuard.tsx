import {Navigate, Outlet, useLocation} from 'react-router';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';

/**
 * Protected routes need a session. While a page load restores it from the refresh cookie only a
 * screen-reader status is shown (no visible element the source did not have); without a
 * session the sign-in screen opens and returns here afterwards.
 */
export function AuthGuard() {
  const {user, loading} = useAuth();
  const {t} = useIntl();
  const location = useLocation();
  if (loading)
    return (
      <p className="sr-status" role="status">
        {t('auth.session.loading')}
      </p>
    );
  if (!user) return <Navigate to="/login" replace state={{from: location.pathname + location.search}} />;
  return <Outlet />;
}
