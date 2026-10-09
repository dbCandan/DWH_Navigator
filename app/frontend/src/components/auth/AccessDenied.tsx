import {Link} from 'react-router';
import {AuthCard} from '@/components/auth/AuthCard';
import {useIntl} from '@/contexts/IntlContext';

/**
 * The "no access" screen for an address the account's role does not open (user-accounts
 * Requirement 16). It is only a courtesy: the backend answers 403 anyway.
 */
export function AccessDenied() {
  const {t} = useIntl();
  return (
    <AuthCard title={t('access.forbidden.title')} lead={t('access.forbidden.body')}>
      <div className="auth-links">
        <Link to="/">{t('access.forbidden.back')}</Link>
      </div>
    </AuthCard>
  );
}
