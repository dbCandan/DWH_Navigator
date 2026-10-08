"""AI page endpoints: model server connections (data-dictionary/PRDs/003-llm-connection).

Every endpoint needs a session and the ``yonetici`` role (the super admin passes centrally); the
service re-reads the account and checks the role again (Requirement 21).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.infrastructure.llm.openai_adapter import OpenAICompatibleAdapter
from app.schemas.errors import error_responses
from app.schemas.llm.integrations import (
    LlmActiveChange,
    LlmIntegrationCreate,
    LlmIntegrationCreated,
    LlmIntegrationsState,
    LlmIntegrationUpdate,
    LlmIntegrationUpdated,
    LlmInventory,
    LlmModelsRequest,
    LlmModelsResult,
    LlmTestRequest,
    LlmTestResult,
)
from app.services.llm_connections import shared_adapter
from app.services.llm_integration_service import LlmIntegrationService

_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
        422: "invalid_request: bozuk gövde ya da bilinmeyen alan",
    }
)
_NOT_FOUND = {404: "llm_integration_not_found: entegrasyon yok ya da silinmiş"}
_SAVE_CONFLICTS = (
    "llm_integration_name_taken: aynı ad; llm_integration_limit: en çok 50 entegrasyon; "
    "llm_chat_role_taken: başka bir entegrasyon aktif"
)
_SAVE_INVALID = (
    "llm_integration_invalid: alan biçimi; llm_endpoint_unresolved: ad çözülemedi; "
    "llm_endpoint_not_private: kurum ağı dışı; llm_chat_model_required: sohbet modeli yok; "
    "llm_key_storage_unavailable: şifreleme anahtarı yok; invalid_request: bozuk gövde"
)

router = APIRouter(
    prefix="/llm-integrations",
    tags=["llm-integrations"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=_ERRORS,
)


def get_llm_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OpenAICompatibleAdapter:
    return shared_adapter(settings)


def get_llm_integration_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[OpenAICompatibleAdapter, Depends(get_llm_adapter)],
) -> LlmIntegrationService:
    return LlmIntegrationService(session, settings=settings, adapter=adapter)


Service = Annotated[LlmIntegrationService, Depends(get_llm_integration_service)]


@router.get("", response_model=LlmIntegrationsState)
async def list_integrations(context: CurrentContext, service: Service) -> LlmIntegrationsState:
    """Integrations in creation order, the active chat model and its state."""

    return await service.state(context)


@router.post(
    "",
    response_model=LlmIntegrationCreated,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses({409: _SAVE_CONFLICTS, 422: _SAVE_INVALID}),
)
async def create_integration(
    body: LlmIntegrationCreate, context: CurrentContext, service: Service
) -> LlmIntegrationCreated:
    """Add an integration; it stays inactive unless ``activate`` is true."""

    return await service.create(context, body)


@router.get("/inventory", response_model=LlmInventory)
async def inventory(context: CurrentContext, service: Service) -> LlmInventory:
    """Every integration's models, at most eight servers at once and 50 seconds in total."""

    return await service.inventory(context)


@router.post(
    "/models",
    response_model=LlmModelsResult,
    responses=error_responses(
        {**_NOT_FOUND, 422: "llm_integration_invalid: adres yok ya da biçimi geçersiz"}
    ),
)
async def list_models(
    body: LlmModelsRequest, context: CurrentContext, service: Service
) -> LlmModelsResult:
    """The models of one server; a server failure is ``ok: false`` with its class."""

    return await service.models(context, body)


@router.post(
    "/test",
    response_model=LlmTestResult,
    responses=error_responses(
        {
            **_NOT_FOUND,
            422: "llm_integration_invalid: alan biçimi; invalid_request: record başka alanla",
        }
    ),
)
async def test_connection(
    body: LlmTestRequest, context: CurrentContext, service: Service
) -> LlmTestResult:
    """Server and chat-model steps with the form's values; nothing is saved but ``record``."""

    return await service.test(context, body)


@router.put(
    "/{public_id}",
    response_model=LlmIntegrationUpdated,
    responses=error_responses({**_NOT_FOUND, 409: _SAVE_CONFLICTS, 422: _SAVE_INVALID}),
)
async def update_integration(
    public_id: UUID, body: LlmIntegrationUpdate, context: CurrentContext, service: Service
) -> LlmIntegrationUpdated:
    """Change the given fields; repeating the same body changes nothing."""

    return await service.update(context, public_id, body)


@router.put(
    "/{public_id}/active",
    response_model=LlmIntegrationsState,
    responses=error_responses(
        {
            **_NOT_FOUND,
            409: "llm_chat_role_taken: başka bir entegrasyon aktif",
            422: "llm_chat_model_required: sohbet modeli yok",
        }
    ),
)
async def set_active(
    public_id: UUID, body: LlmActiveChange, context: CurrentContext, service: Service
) -> LlmIntegrationsState:
    """Make the integration the chat model or turn it off; ``replace`` takes over the role."""

    return await service.set_active(context, public_id, body)


@router.delete(
    "/{public_id}",
    response_model=LlmIntegrationsState,
    responses=error_responses(_NOT_FOUND),
)
async def delete_integration(
    public_id: UUID, context: CurrentContext, service: Service
) -> LlmIntegrationsState:
    """Soft-delete the integration and empty its stored key."""

    return await service.delete(context, public_id)
