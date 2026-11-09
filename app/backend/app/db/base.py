"""Complete SQLAlchemy model registry imported by Alembic and operational scripts."""

from app.db.base_class import Base  # noqa: F401

# Alembic imports this module to populate Base.metadata. Keep the imports here.
from app.domain.models.analysis_record import AnalysisRecord  # noqa: F401
from app.domain.models.answer_vote import AnswerVote  # noqa: F401
from app.domain.models.dictionary import (  # noqa: F401
    DictionaryColumnRecord,
    DictionaryObjectRecord,
    DictionaryVersion,
)
from app.domain.models.dictionary_sync import (  # noqa: F401
    DictionarySource,
    DictionarySyncChange,
    DictionarySyncRun,
    DictionarySyncSuggestion,
)
from app.domain.models.llm_call_log import LlmCallLog  # noqa: F401
from app.domain.models.llm_integration import LlmIntegration  # noqa: F401
from app.domain.models.permission import Permission, RolePermission  # noqa: F401
from app.domain.models.refresh_session import RefreshSession  # noqa: F401
from app.domain.models.role import Role, UserRole  # noqa: F401
from app.domain.models.saved_answer import SavedAnswer  # noqa: F401
from app.domain.models.search_setting import SearchSetting  # noqa: F401
from app.domain.models.tenant import Tenant  # noqa: F401
from app.domain.models.term_list import TermList, TermListItem  # noqa: F401
from app.domain.models.user import User  # noqa: F401
from app.domain.models.user_change import UserChange  # noqa: F401
from app.domain.models.visitor import Visitor  # noqa: F401
from app.domain.models.vocabulary import (  # noqa: F401
    VocabularyListHeader,
    VocabularyStopword,
    VocabularyTerm,
)

# kt-scaffold:model-registry
