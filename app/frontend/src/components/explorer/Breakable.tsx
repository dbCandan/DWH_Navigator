import {Fragment} from 'react';
import {breakParts} from '@/lib/answerText';

/** "vCustomer<wbr>Info": a long identifier that may wrap only at its word joints (index.html breakable). */
export function Breakable({name}: {name: string}) {
  return (
    <>
      {breakParts(name).map((part, i) => (
        <Fragment key={i}>
          {i ? <wbr /> : null}
          {part}
        </Fragment>
      ))}
    </>
  );
}
