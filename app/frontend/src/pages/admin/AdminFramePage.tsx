import {PageHead} from '@/components/admin/PageHead';
import type {AdminPageId} from '@/components/admin/nav';
import {useIntl} from '@/contexts/IntlContext';

/**
 * A page's frame in the admin shell: its section and heading (search-settings Requirement 20).
 * The content belongs to the page's owner capability and arrives with it.
 */
export default function AdminFramePage({page}: {page: AdminPageId}) {
  const {t} = useIntl();
  const label = t(`admin.page.${page}.label`);
  return (
    <section className="page on" id={'p-' + page} aria-label={label}>
      <PageHead title={label} description={t(`admin.page.${page}.description`)} />
    </section>
  );
}
