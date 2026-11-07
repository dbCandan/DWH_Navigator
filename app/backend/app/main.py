"""FastAPI application factory."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import database_readiness
from app.api.router import router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry
from app.db.readiness import packaged_schema
from app.db.session import async_session_factory, engine
from app.infrastructure.dictionary_source.sqlserver import SqlServerDictionarySource
from app.middleware.cross_site import CrossSiteRequestMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.services.analysis.jobs import AnalysisJobs
from app.services.analysis.saved_answers import SavedAnswers
from app.services.answer_feedback import AnswerVotes
from app.services.dictionary_sync import DictionarySync, SourceKeys
from app.services.explorer import ExplorerIndex
from app.services.llm_call_log import LlmCallLogWriter
from app.services.llm_connections import llm_gateway, shared_adapter
from app.services.search_index import SearchIndex
from app.services.super_admin_service import run_super_admin_bootstrap
from app.services.term_lists import TermLists


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Readiness compares the database with the migration head shipped in this image; reading
        # it at startup stops an image without its migrations before it serves.
        packaged_schema()
        telemetry_export = configure_telemetry(settings)
        # application-foundation 001 Requirement 17: creates the configured super admin once; it
        # retries in the background while a first installation is still migrating.
        bootstrap = asyncio.create_task(run_super_admin_bootstrap(async_session_factory, settings))
        # data-dictionary 009-search-settings Requirement 10: the process listens at once; the
        # first search index is built in the background once the database is ready.
        search_index: SearchIndex = application.state.search_index
        index_startup = asyncio.create_task(search_index.run_startup(database_readiness.is_ready))
        # data-dictionary 004-question-analysis Requirement 12: records an earlier process left
        # queued or running are interrupted; at the end queued and running jobs are interrupted.
        analysis_jobs: AnalysisJobs = application.state.analysis_jobs
        jobs_startup = asyncio.create_task(analysis_jobs.run_startup(database_readiness.is_ready))
        # data-dictionary 005-list-search Requirement 10: lists an earlier process left running
        # are interrupted, then a minute check; at the end running lists are interrupted.
        term_lists: TermLists = application.state.term_lists
        lists_startup = asyncio.create_task(term_lists.run_startup(database_readiness.is_ready))
        # 011-dictionary-sync: runs an earlier process left are interrupted, old versions go.
        dictionary_sync: DictionarySync = application.state.dictionary_sync
        sync_startup = asyncio.create_task(dictionary_sync.run_startup(database_readiness.is_ready))
        try:
            yield
        finally:
            term_lists.closing = True
            await dictionary_sync.shutdown()
            await analysis_jobs.shutdown()
            await term_lists.shutdown()
            for task in (bootstrap, index_startup, jobs_startup, lists_startup, sync_startup):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await engine.dispose()
            if telemetry_export is not None:
                telemetry_export.shutdown()

    return lifespan


def create_application(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Platform API for dwhnavigator",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan(settings),
    )
    if settings.llm_call_log_days:
        shared_adapter(settings).set_call_log(
            LlmCallLogWriter(async_session_factory, days=settings.llm_call_log_days)
        )
    application.state.search_index = SearchIndex(async_session_factory)
    application.state.explorer_index = ExplorerIndex()
    saved_answers = SavedAnswers(async_session_factory)
    application.state.answer_votes = AnswerVotes(
        index=application.state.search_index,
        session_factory=async_session_factory,
        saved_answers=saved_answers,
    )
    application.state.analysis_jobs = AnalysisJobs(
        index=application.state.search_index,
        models=llm_gateway(settings, async_session_factory),
        session_factory=async_session_factory,
        saved_answers=saved_answers,
        overlay=application.state.answer_votes,
        concurrency=settings.analysis_concurrency,
        queue_limit=settings.analysis_queue_limit,
    )
    application.state.term_lists = TermLists(
        jobs=application.state.analysis_jobs, session_factory=async_session_factory
    )
    ignored_databases = tuple(
        name.strip() for name in settings.dictionary_ignored_databases.split(",") if name.strip()
    )
    application.state.dictionary_sync = DictionarySync(
        index=application.state.search_index,
        models=llm_gateway(settings, async_session_factory),
        source=SqlServerDictionarySource(
            ignored_databases=ignored_databases,
            aliases=dict(
                pair.strip().split("=", 1)
                for pair in settings.dictionary_object_aliases.split(";")
                if "=" in pair
            ),
        ),
        kept_databases=ignored_databases,
        keys=lambda: SourceKeys(settings),
        session_factory=async_session_factory,
    )
    # Starlette makes the middleware added last the outermost. From the outside in: security
    # headers and the 500 envelope, request logging and tracing, CORS, the cross-site guard (before
    # any tenant or session check) and the tenant context.
    application.add_middleware(TenantContextMiddleware)
    application.add_middleware(CrossSiteRequestMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["WWW-Authenticate", "X-Request-ID", "Retry-After"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    install_error_handlers(application)
    application.include_router(router)
    return application


app = create_application()
