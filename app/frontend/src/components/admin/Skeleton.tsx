import {useIntl} from '@/contexts/IntlContext';

/** The loading placeholder of a page or a drawer (admin.html skeleton()). */
export function Skeleton() {
  const {t} = useIntl();
  return (
    <div className="card" role="status" aria-label={t('admin.loading')}>
      <div className="skel" />
      <div className="skel" />
      <div className="skel" />
    </div>
  );
}
