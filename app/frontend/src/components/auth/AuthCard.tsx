import type {ReactNode} from 'react';
import {AdminLogo} from '@/components/brand/AdminLogo';
import {useIntl} from '@/contexts/IntlContext';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useSurface} from '@/hooks/useSurface';
import '@/components/admin/admin.css';
import './auth.css';

/** The account screens' frame: the product mark, a title, an optional lead line and the content. */
export function AuthCard({title, lead, children}: {title: string; lead?: string; children: ReactNode}) {
  const {t} = useIntl();
  useSurface('admin');
  useDocumentTitle(t('auth.documentTitle', {title}));
  return (
    <main className="auth">
      <section className="card auth-card" aria-labelledby="auth-title">
        <div className="brand">
          <AdminLogo />
          <span>
            <b>{t('explorer.brand.name')}</b>
            <small>{t('explorer.brand.tagline')}</small>
          </span>
        </div>
        <h1 id="auth-title">{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
        {children}
      </section>
    </main>
  );
}
