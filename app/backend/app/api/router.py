"""Aggregate platform router mounted under the configured API prefix."""

from fastapi import APIRouter

from app.api.admin.router import router as admin_router
from app.api.analyses.router import router as analyses_router
from app.api.analysis_records.router import router as analysis_records_router
from app.api.auth.router import router as auth_router
from app.api.dictionary.router import router as dictionary_router
from app.api.dictionary_sync.router import router as dictionary_sync_router
from app.api.explorer.router import router as explorer_router
from app.api.health import router as health_router
from app.api.llm_call_logs.router import router as llm_call_logs_router
from app.api.llm_integrations.router import router as llm_integrations_router
from app.api.search.router import router as search_router
from app.api.term_lists.router import router as term_lists_router
from app.api.vocabulary.router import router as vocabulary_router
from app.api.votes.router import router as votes_router
from app.core.config import get_settings

# kt-scaffold:router-imports

router = APIRouter(prefix=get_settings().api_prefix)
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(llm_integrations_router)
router.include_router(llm_call_logs_router)
router.include_router(dictionary_router)
router.include_router(dictionary_sync_router)
router.include_router(vocabulary_router)
router.include_router(search_router)
router.include_router(analyses_router)
router.include_router(analysis_records_router)
router.include_router(explorer_router)
router.include_router(votes_router)
router.include_router(term_lists_router)
# kt-scaffold:router-registration
