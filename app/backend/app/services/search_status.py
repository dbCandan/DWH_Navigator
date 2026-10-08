"""The ``GET /search-index`` answer (search-settings Requirement 15), shared by every change.

Dictionary imports, list saves, settings saves and rebuilds return it as their ``index`` field.
"""

from app.schemas.search.settings import IndexChange, SearchIndexState
from app.services.search_index import ChangeMark, SearchIndex


def _change(mark: ChangeMark | None) -> IndexChange | None:
    return None if mark is None else IndexChange(trigger=mark.trigger.value, at=mark.at)


async def index_state(index: SearchIndex) -> SearchIndexState:
    status = await index.status()
    return SearchIndexState(
        state=status.state.value,
        stale_inputs=list(status.stale_inputs),  # type: ignore[arg-type]
        columns=status.columns,
        objects=status.objects,
        dictionary_version=status.dictionary_version,
        built_at=status.built_at,
        build_ms=status.build_ms,
        trigger=status.trigger.value if status.trigger else None,
        running=_change(status.running),
        last_failure=_change(status.last_failure),
    )
