import {Link} from 'react-router';
import {AuthCard} from '@/components/auth/AuthCard';
import {useIntl} from '@/contexts/IntlContext';

/** An address the application does not know, including unknown `/admin/...` addresses. */
export default function NotFoundPage() {
  const {t} = useIntl();
  return (
    <AuthCard title={t('routing.notFound.title')} lead={t('routing.notFound.body')}>
      <div className="auth-links">
        <Link to="/">{t('routing.notFound.home')}</Link>
      </div>
    </AuthCard>
  );
}
