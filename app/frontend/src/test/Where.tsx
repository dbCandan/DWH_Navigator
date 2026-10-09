import {useLocation} from 'react-router';

/** The current address, for tests that follow a navigation. */
export function Where() {
  const location = useLocation();
  return <span data-testid="where">{location.pathname}</span>;
}
