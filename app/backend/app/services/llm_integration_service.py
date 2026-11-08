"""The AI page: integrations, the single active chat model, model lists and the connection test.

data-dictionary/PRDs/003-llm-connection Requirement 2-4, 12 and 14-16, 21. Every request re-reads
the acting account and requires ``yonetici`` (the super admin passes); the router checks the same
role. Changes need no restart: the next analysis reads the new state (Requirement 5). Every change
writes ``updated_by``/``updated_at`` and an ``llm_integration.changed`` event with field names only.
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import VALIDATION_ERROR_CODE, ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.core.secret_cipher import SecretUnreadable
from app.domain.accounts import ROLE_MANAGER
from app.domain.llm import (
    CHAT_MODEL_MAX_LENGTH,
    CHAT_STEP,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    ENDPOINT_MISSING,
    MAX_INTEGRATIONS,
    MODEL_NOT_LISTED,
    SERVER_STEP,
    TEST_ANSWER_CHARS,
    TEST_MAX_TOKENS,
    TEST_QUESTION,
    TEST_SCHEMA,
    TEST_SYSTEM_PROMPT,
    IntegrationFields,
    LlmChatRequest,
    LlmConnection,
    LlmIntegrationInvalid,
    LlmModelInfo,
    LlmOutcome,
    LlmPurpose,
    ProbeOperation,
    check_integration_fields,
    endpoint_origin,
    normalize_endpoint,
    probe_message,
    short_reason,
)
from app.domain.models.llm_integration import INHERIT, LlmIntegration
from app.domain.models.mixins import new_public_id
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.domain.turkish_text import fold
from app.infrastructure.llm.openai_adapter import OpenAICompatibleAdapter
from app.infrastructure.repositories.llm_integration_repository import (
    ChatRoleTaken,
    IntegrationNameTaken,
    LlmIntegrationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.llm.integrations import (
    LlmActiveChange,
    LlmActiveIntegration,
    LlmFailureCode,
    LlmIntegrationCreate,
    LlmIntegrationCreated,
    LlmIntegrationItem,
    LlmIntegrationsState,
    LlmIntegrationUpdate,
    LlmIntegrationUpdated,
    LlmInventory,
    LlmInventoryServer,
    LlmLastTest,
    LlmModelRow,
    LlmModelsRequest,
    LlmModelsResult,
    LlmModelState,
    LlmTestRequest,
    LlmTestResult,
    LlmTestStep,
)
from app.services.llm_connections import (
    ActiveConnection,
    ConnectionKeys,
    model_state,
    report_key_unreadable,
)
from app.services.request_scope import acting_user_with_role, active_tenant

logger = logging.getLogger("app.llm")

_CONNECTION_FIELDS = (
    "endpoint",
    "api_key",
    "chat_model",
    "temperature",
    "timeout_seconds",
    "reasoning_effort",
    "seed",
)


def _invalid(error: LlmIntegrationInvalid) -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "llm_integration_invalid", error.message
    )


def integration_not_found() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND,
        "llm_integration_not_found",
        "Entegrasyon bulunamadı.",
    )


def _name_taken(name: str) -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "llm_integration_name_taken",
        f"“{name}” adında bir entegrasyon zaten var",
    )


def _limit_reached() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "llm_integration_limit",
        f"En çok {MAX_INTEGRATIONS} entegrasyon tanımlanabilir.",
    )


def _role_taken(holder: str) -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "llm_chat_role_taken",
        f"“{holder}” (Sohbet modeli) şu an bu rolde aktif. Pasif yapılıp yerine bu entegrasyon "
        "kullanılsın mı?",
    )


def _chat_model_required() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "llm_chat_model_required",
        "Önce bu entegrasyon için bir sohbet modeli seçin",
    )


def _key_storage_unavailable() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "llm_key_storage_unavailable",
        "Bu ortamda API anahtarı saklanamıyor; şifreleme anahtarı tanımlı değil.",
    )


def _endpoint_unresolved() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "llm_endpoint_unresolved",
        "sunucu adı çözülemedi — adresi kontrol edin",
    )


def _endpoint_not_private() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "llm_endpoint_not_private",
        "Adres kurum ağı dışında; yalnız kurum içi model sunucusu bağlanabilir.",
    )


def _record_with_fields() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        VALIDATION_ERROR_CODE,
        "İstek değerleri geçersiz: record.",
    )


def _origin(endpoint: str) -> str | None:
    try:
        return endpoint_origin(endpoint)
    except ValueError:
        return None


GENERATION_EFFORTS = (INHERIT, "none", "low", "medium", "high", "")


def _generation(
    model: str | None,
    describe: str | None,
    judge: str | None,
    row: LlmIntegration | None,
) -> tuple[str, str, str]:
    """The generation role's three values; an absent one keeps the row's (or the default)."""

    values = (
        (model if model is not None else (row.generation_model if row else "")).strip(),
        describe
        if describe is not None
        else (row.generation_reasoning_effort if row else INHERIT),
        judge
        if judge is not None
        else (row.judge_reasoning_effort if row else INHERIT),
    )
    if len(values[0]) > CHAT_MODEL_MAX_LENGTH:
        raise _invalid(
            LlmIntegrationInvalid(
                f"Üretim modeli en çok {CHAT_MODEL_MAX_LENGTH} karakter olabilir."
            )
        )
    for value in values[1:]:
        if value not in GENERATION_EFFORTS:
            raise _invalid(
                LlmIntegrationInvalid(
                    "Düşünme modu: inherit, none, low, medium, high ya da boş."
                )
            )
    return values


def _given(value: object, default: object) -> object:
    return default if value is None else value


def _item(row: LlmIntegration) -> LlmIntegrationItem:
    last_test = None
    if row.last_test_at is not None and row.last_test_ok is not None:
        last_test = LlmLastTest(
            at=row.last_test_at,
            ok=row.last_test_ok,
            summary=row.last_test_summary or "",
        )
    return LlmIntegrationItem(
        public_id=UUID(row.public_id),
        name=row.name,
        endpoint=row.endpoint,
        has_key=row.api_key_ciphertext is not None,
        active=row.active,
        chat_model=row.chat_model,
        temperature=row.temperature,
        timeout_seconds=row.timeout_seconds,
        reasoning_effort=row.reasoning_effort,
        seed=row.seed,
        generation_model=row.generation_model,
        generation_reasoning_effort=row.generation_reasoning_effort,
        judge_reasoning_effort=row.judge_reasoning_effort,
        last_test=last_test,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _rows(models: Sequence[LlmModelInfo], in_use: str | None) -> list[LlmModelRow]:
    return [
        LlmModelRow(
            id=model.id,
            type=model.type,
            loaded=model.loaded,
            context=model.context,
            owner=model.owner,
            quant=model.quant,
            in_use=in_use is not None and model.id == in_use,
        )
        for model in models
    ]


def _code(outcome: LlmOutcome | None) -> LlmFailureCode | None:
    if outcome is None or outcome is LlmOutcome.OK:
        return None
    return cast(LlmFailureCode, outcome.value)


@dataclass(frozen=True, slots=True)
class _Scope:
    tenant: Tenant
    actor: User


class LlmIntegrationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        adapter: OpenAICompatibleAdapter,
    ) -> None:
        self.session = session
        self.settings = settings
        self.adapter = adapter
        self.users = UserRepository(session)
        self.integrations = LlmIntegrationRepository(session)
        self.keys = ConnectionKeys(settings)

    @property
    def environment(self) -> str:
        return self.settings.runtime_environment

    async def _scope(self, context: RequestContext) -> _Scope:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user_with_role(self.users, context, ROLE_MANAGER)
        return _Scope(tenant, actor)

    async def _row(self, tenant: Tenant, public_id: UUID) -> LlmIntegration:
        row = await self.integrations.get_live(tenant.tenant_id, str(public_id))
        if row is None:
            raise integration_not_found()
        return row

    def _changed(
        self, scope: _Scope, row: LlmIntegration, action: str, fields: Sequence[str]
    ) -> None:
        log_event(
            logger,
            "llm_integration.changed",
            action=action,
            integration_public_id=row.public_id,
            fields=",".join(fields),
            actor_public_id=scope.actor.public_id,
        )

    # --- read --------------------------------------------------------------------------------

    async def state(self, context: RequestContext) -> LlmIntegrationsState:
        scope = await self._scope(context)
        return await self._state(scope.tenant)

    async def _state(self, tenant: Tenant) -> LlmIntegrationsState:
        rows = await self.integrations.list_live(tenant.tenant_id)
        active_row = next((row for row in rows if row.active), None)
        if active_row is None or not active_row.chat_model:
            active = ActiveConnection(active_row, LlmOutcome.NOT_CONFIGURED)
        else:
            active = ActiveConnection(
                active_row,
                self.keys.connection(active_row, tenant_public_id=tenant.public_id),
            )
        state = await model_state(self.adapter, active)
        environment = self.settings.runtime_environment
        return LlmIntegrationsState(
            items=[_item(row) for row in rows],
            total=len(rows),
            active=(
                LlmActiveIntegration(
                    public_id=UUID(active_row.public_id),
                    name=active_row.name,
                    model=active_row.chat_model,
                )
                if active_row is not None
                else None
            ),
            model_state=LlmModelState(
                state=state.state,
                model=state.model,
                code=_code(state.code),
                reason=state.reason,
                name=active_row.name if active_row is not None else None,
            ),
            environment=environment,
            accepts_http=environment == "local",
            key_storage=self.keys.available,
        )

    # --- change ------------------------------------------------------------------------------

    def _fields(
        self,
        *,
        name: str,
        endpoint: str,
        chat_model: str,
        temperature: object,
        timeout_seconds: object,
        reasoning_effort: str,
        seed: object,
        api_key: str | None,
        check_name: bool = True,
    ) -> IntegrationFields:
        try:
            return check_integration_fields(
                name=name,
                endpoint=endpoint,
                chat_model=chat_model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
                seed=seed,
                api_key=api_key,
                environment=self.settings.runtime_environment,
                check_name=check_name,
            )
        except LlmIntegrationInvalid as error:
            raise _invalid(error) from None

    async def _require_private(self, endpoint: str) -> None:
        outcome = await self.adapter.check_address(endpoint)
        if outcome is LlmOutcome.NETWORK_POLICY_DENIED:
            raise _endpoint_not_private()
        if outcome is not LlmOutcome.OK:
            raise _endpoint_unresolved()

    async def _holder_name(self, tenant: Tenant) -> str:
        holder = await self.integrations.active(tenant.tenant_id)
        return holder.name if holder is not None else ""

    async def _take_chat_role(
        self, scope: _Scope, row: LlmIntegration, *, replace: bool
    ) -> list[LlmIntegration]:
        """Requirement 4: refuse while another integration is active, or turn it off first."""

        others = await self.integrations.other_active(
            scope.tenant.tenant_id, row.llm_integration_id
        )
        if others and not replace:
            raise _role_taken(others[0].name)
        for other in others:
            other.active = False
            other.updated_by = scope.actor.user_id
        if others:
            await self.integrations.flush()
        return others

    async def create(
        self, context: RequestContext, body: LlmIntegrationCreate
    ) -> LlmIntegrationCreated:
        scope = await self._scope(context)
        fields = self._fields(
            name=body.name,
            endpoint=body.endpoint,
            chat_model=body.chat_model or "",
            temperature=_given(body.temperature, DEFAULT_TEMPERATURE),
            timeout_seconds=_given(body.timeout_seconds, DEFAULT_TIMEOUT_SECONDS),
            reasoning_effort=(
                body.reasoning_effort
                if body.reasoning_effort is not None
                else DEFAULT_REASONING_EFFORT
            ),
            seed=_given(body.seed, DEFAULT_SEED),
            api_key=body.api_key,
        )
        generation = _generation(
            body.generation_model,
            body.generation_reasoning_effort,
            body.judge_reasoning_effort,
            None,
        )
        api_key = body.api_key or None
        if api_key is not None and not self.keys.available:
            raise _key_storage_unavailable()
        activate = bool(body.activate)
        if activate and not fields.chat_model:
            raise _chat_model_required()
        tenant = scope.tenant
        await self.integrations.lock_tenant(tenant.tenant_id)
        if await self.integrations.count_live(tenant.tenant_id) >= MAX_INTEGRATIONS:
            raise _limit_reached()
        name_key = fold(fields.name)
        if await self.integrations.name_key_taken(
            tenant.tenant_id, name_key, except_id=None
        ):
            raise _name_taken(fields.name)
        await self._require_private(fields.endpoint)
        row = LlmIntegration(
            public_id=new_public_id(),
            tenant_id=tenant.tenant_id,
            name=fields.name,
            name_key=name_key,
            endpoint=fields.endpoint,
            chat_model=fields.chat_model,
            temperature=fields.temperature,
            timeout_seconds=fields.timeout_seconds,
            reasoning_effort=fields.reasoning_effort,
            seed=fields.seed,
            generation_model=generation[0],
            generation_reasoning_effort=generation[1],
            judge_reasoning_effort=generation[2],
            active=False,
            created_by=scope.actor.user_id,
            updated_by=scope.actor.user_id,
        )
        if api_key is not None:
            row.api_key_ciphertext = self.keys.seal(
                api_key, tenant_public_id=tenant.public_id, row=row
            )
        replaced: list[LlmIntegration] = []
        if activate:
            replaced = await self._take_chat_role(scope, row, replace=body.replace)
            row.active = True
        self.session.add(row)
        try:
            await self.integrations.flush()
        except IntegrationNameTaken:
            raise _name_taken(fields.name) from None
        except ChatRoleTaken:
            raise _role_taken(await self._holder_name(tenant)) from None
        created = ["name", "endpoint", "chat_model", "temperature", "timeout_seconds"]
        created += ["reasoning_effort", "seed"] + (["api_key"] if api_key else [])
        self._changed(scope, row, "created", created)
        for other in replaced:
            self._changed(scope, other, "deactivated", ["active"])
        if row.active:
            self._changed(scope, row, "activated", ["active"])
        state = await self._state(tenant)
        return LlmIntegrationCreated(item=_item(row), **state.model_dump())

    async def update(
        self, context: RequestContext, public_id: UUID, body: LlmIntegrationUpdate
    ) -> LlmIntegrationUpdated:
        scope = await self._scope(context)
        tenant = scope.tenant
        row = await self._row(tenant, public_id)
        fields = self._fields(
            name=body.name if body.name is not None else row.name,
            endpoint=body.endpoint if body.endpoint is not None else row.endpoint,
            chat_model=body.chat_model
            if body.chat_model is not None
            else row.chat_model,
            temperature=_given(body.temperature, row.temperature),
            timeout_seconds=_given(body.timeout_seconds, row.timeout_seconds),
            reasoning_effort=(
                body.reasoning_effort
                if body.reasoning_effort is not None
                else row.reasoning_effort
            ),
            seed=_given(body.seed, row.seed),
            api_key=body.api_key,
        )
        generation = _generation(
            body.generation_model,
            body.generation_reasoning_effort,
            body.judge_reasoning_effort,
            row,
        )
        new_key = body.api_key or None
        if new_key is not None and not self.keys.available:
            raise _key_storage_unavailable()
        target_active = row.active if body.activate is None else body.activate
        if target_active and not fields.chat_model:
            raise _chat_model_required()

        changed = [
            name
            for name, old, new in (
                ("name", row.name, fields.name),
                ("endpoint", row.endpoint, fields.endpoint),
                ("chat_model", row.chat_model, fields.chat_model),
                ("temperature", row.temperature, fields.temperature),
                ("timeout_seconds", row.timeout_seconds, fields.timeout_seconds),
                ("reasoning_effort", row.reasoning_effort, fields.reasoning_effort),
                ("seed", row.seed, fields.seed),
                ("generation_model", row.generation_model, generation[0]),
                (
                    "generation_reasoning_effort",
                    row.generation_reasoning_effort,
                    generation[1],
                ),
                ("judge_reasoning_effort", row.judge_reasoning_effort, generation[2]),
            )
            if old != new
        ]
        origin_changed = _origin(fields.endpoint) != _origin(row.endpoint)
        key_action: str | None = None  # "seal", "delete" or "cleared"
        if body.api_key is not None and new_key is None:
            if row.api_key_ciphertext is not None:
                key_action = "delete"
        elif new_key is not None:
            try:
                current = self.keys.open(row, tenant_public_id=tenant.public_id)
            except SecretUnreadable:
                current = None
            if origin_changed or current != new_key:
                key_action = "seal"
        elif origin_changed and row.api_key_ciphertext is not None:
            # Decision 9: a saved key never follows the address to another origin.
            key_action = "cleared"
        if key_action is not None:
            changed.append("api_key")

        if (
            "name" in changed
            and fold(fields.name) != row.name_key
            and await self.integrations.name_key_taken(
                tenant.tenant_id, fold(fields.name), except_id=row.llm_integration_id
            )
        ):
            raise _name_taken(fields.name)
        if "endpoint" in changed:
            await self._require_private(fields.endpoint)

        activating = target_active and not row.active
        deactivating = row.active and not target_active
        if not changed and not activating and not deactivating:
            state = await self._state(tenant)
            return LlmIntegrationUpdated(
                item=_item(row), key_cleared=False, **state.model_dump()
            )

        replaced: list[LlmIntegration] = []
        if activating:
            replaced = await self._take_chat_role(scope, row, replace=body.replace)
        if "endpoint" in changed or "chat_model" in changed:
            # The old test result no longer describes this connection.
            row.last_test_at = None
            row.last_test_ok = None
            row.last_test_summary = None
        row.name = fields.name
        row.name_key = fold(fields.name)
        row.endpoint = fields.endpoint
        row.chat_model = fields.chat_model
        row.temperature = fields.temperature
        row.timeout_seconds = fields.timeout_seconds
        row.reasoning_effort = fields.reasoning_effort
        row.seed = fields.seed
        (
            row.generation_model,
            row.generation_reasoning_effort,
            row.judge_reasoning_effort,
        ) = generation
        if key_action == "seal" and new_key is not None:
            row.api_key_ciphertext = self.keys.seal(
                new_key, tenant_public_id=tenant.public_id, row=row
            )
        elif key_action in ("delete", "cleared"):
            row.api_key_ciphertext = None
        row.active = target_active
        row.updated_by = scope.actor.user_id
        try:
            await self.integrations.flush()
        except IntegrationNameTaken:
            raise _name_taken(fields.name) from None
        except ChatRoleTaken:
            raise _role_taken(await self._holder_name(tenant)) from None
        if changed:
            self._changed(scope, row, "updated", changed)
        if key_action == "cleared":
            self._changed(scope, row, "key_cleared", ["api_key"])
        for other in replaced:
            self._changed(scope, other, "deactivated", ["active"])
        if activating:
            self._changed(scope, row, "activated", ["active"])
        if deactivating:
            self._changed(scope, row, "deactivated", ["active"])
        state = await self._state(tenant)
        return LlmIntegrationUpdated(
            item=_item(row), key_cleared=key_action == "cleared", **state.model_dump()
        )

    async def set_active(
        self, context: RequestContext, public_id: UUID, body: LlmActiveChange
    ) -> LlmIntegrationsState:
        scope = await self._scope(context)
        tenant = scope.tenant
        row = await self._row(tenant, public_id)
        if body.active and not row.chat_model:
            raise _chat_model_required()
        if body.active != row.active:
            replaced: list[LlmIntegration] = []
            if body.active:
                replaced = await self._take_chat_role(scope, row, replace=body.replace)
            row.active = body.active
            row.updated_by = scope.actor.user_id
            try:
                await self.integrations.flush()
            except ChatRoleTaken:
                raise _role_taken(await self._holder_name(tenant)) from None
            for other in replaced:
                self._changed(scope, other, "deactivated", ["active"])
            self._changed(
                scope, row, "activated" if body.active else "deactivated", ["active"]
            )
        return await self._state(tenant)

    async def delete(
        self, context: RequestContext, public_id: UUID
    ) -> LlmIntegrationsState:
        scope = await self._scope(context)
        tenant = scope.tenant
        row = await self._row(tenant, public_id)
        row.is_deleted = True
        row.deleted_at = datetime.now(UTC)
        row.deleted_by = scope.actor.user_id
        row.api_key_ciphertext = None
        row.active = False
        row.updated_by = scope.actor.user_id
        await self.integrations.flush()
        self._changed(scope, row, "deleted", ["is_deleted"])
        return await self._state(tenant)

    # --- servers -----------------------------------------------------------------------------

    def _form_key(
        self,
        tenant: Tenant,
        row: LlmIntegration | None,
        endpoint: str,
        form_key: str | None,
    ) -> str | None | LlmOutcome:
        """Requirement 16: the form's key, or the saved key only for the address it was saved for."""

        if form_key:
            return form_key
        if row is None or row.api_key_ciphertext is None:
            return None
        if _origin(endpoint) != _origin(row.endpoint):
            return None
        try:
            return self.keys.open(row, tenant_public_id=tenant.public_id)
        except SecretUnreadable:
            report_key_unreadable(row)
            return LlmOutcome.KEY_UNREADABLE

    async def models(
        self, context: RequestContext, body: LlmModelsRequest
    ) -> LlmModelsResult:
        scope = await self._scope(context)
        row = await self._row(scope.tenant, body.public_id) if body.public_id else None
        endpoint = (
            normalize_endpoint(body.endpoint) if body.endpoint is not None else ""
        )
        if body.endpoint is None and row is not None:
            endpoint = row.endpoint
        if not endpoint:
            raise _invalid(LlmIntegrationInvalid([ENDPOINT_MISSING]))
        fields = self._fields(
            name="",
            endpoint=endpoint,
            chat_model=row.chat_model if row is not None else "",
            temperature=row.temperature if row is not None else DEFAULT_TEMPERATURE,
            timeout_seconds=row.timeout_seconds
            if row is not None
            else DEFAULT_TIMEOUT_SECONDS,
            reasoning_effort=row.reasoning_effort
            if row is not None
            else DEFAULT_REASONING_EFFORT,
            seed=row.seed if row is not None else DEFAULT_SEED,
            api_key=body.api_key,
            check_name=False,
        )
        key = self._form_key(scope.tenant, row, fields.endpoint, body.api_key)
        if isinstance(key, LlmOutcome):
            return LlmModelsResult(
                ok=False, code=_code(key), message=probe_message(key), models=[], ms=0
            )
        connection = self._connection(fields, key, row, scope.tenant.tenant_id)
        listing = await self.adapter.list_models(
            connection, operation=ProbeOperation.MODELS
        )
        probe = listing.probe
        in_use = row.chat_model if row is not None and row.active else None
        return LlmModelsResult(
            ok=probe.ok,
            code=_code(probe.outcome),
            message=probe.message,
            models=_rows(listing.models, in_use),
            ms=probe.duration_ms,
        )

    @staticmethod
    def _connection(
        fields: IntegrationFields,
        api_key: str | None,
        row: LlmIntegration | None,
        tenant_id: int,
    ) -> LlmConnection:
        return LlmConnection(
            endpoint=fields.endpoint,
            chat_model=fields.chat_model,
            temperature=fields.temperature,
            timeout_seconds=fields.timeout_seconds,
            reasoning_effort=fields.reasoning_effort,
            seed=fields.seed,
            api_key=api_key,
            public_id=row.public_id if row is not None else None,
            tenant_id=tenant_id,
        )

    async def inventory(self, context: RequestContext) -> LlmInventory:
        scope = await self._scope(context)
        rows = await self.integrations.list_live(scope.tenant.tenant_id)
        prepared = [
            self.keys.connection(row, tenant_public_id=scope.tenant.public_id)
            for row in rows
        ]
        usable = [item for item in prepared if isinstance(item, LlmConnection)]
        listings = iter(await self.adapter.list_models_of(usable))
        servers: list[LlmInventoryServer] = []
        for row, item in zip(rows, prepared, strict=True):
            in_use = row.chat_model if row.active else None
            if isinstance(item, LlmOutcome):
                servers.append(
                    LlmInventoryServer(
                        public_id=UUID(row.public_id),
                        name=row.name,
                        active=row.active,
                        ok=False,
                        code=_code(item),
                        message=probe_message(item),
                        models=[],
                    )
                )
                continue
            listing = next(listings)
            servers.append(
                LlmInventoryServer(
                    public_id=UUID(row.public_id),
                    name=row.name,
                    active=row.active,
                    ok=listing.probe.ok,
                    code=_code(listing.probe.outcome),
                    message=listing.probe.message,
                    models=_rows(listing.models, in_use),
                )
            )
        return LlmInventory(servers=servers)

    async def test(
        self, context: RequestContext, body: LlmTestRequest
    ) -> LlmTestResult:
        scope = await self._scope(context)
        given = body.model_fields_set
        if body.record and (body.public_id is None or given & set(_CONNECTION_FIELDS)):
            raise _record_with_fields()
        row = await self._row(scope.tenant, body.public_id) if body.public_id else None
        endpoint = (
            normalize_endpoint(body.endpoint) if body.endpoint is not None else ""
        )
        if body.endpoint is None and row is not None:
            endpoint = row.endpoint
        if not endpoint:
            raise _invalid(LlmIntegrationInvalid([ENDPOINT_MISSING]))
        fields = self._fields(
            name="",
            endpoint=endpoint,
            chat_model=(
                body.chat_model
                if body.chat_model is not None
                else row.chat_model
                if row is not None
                else ""
            ),
            temperature=_given(
                body.temperature,
                row.temperature if row is not None else DEFAULT_TEMPERATURE,
            ),
            timeout_seconds=_given(
                body.timeout_seconds,
                row.timeout_seconds if row is not None else DEFAULT_TIMEOUT_SECONDS,
            ),
            reasoning_effort=(
                body.reasoning_effort
                if body.reasoning_effort is not None
                else row.reasoning_effort
                if row is not None
                else DEFAULT_REASONING_EFFORT
            ),
            seed=_given(body.seed, row.seed if row is not None else DEFAULT_SEED),
            api_key=body.api_key,
            check_name=False,
        )
        key = self._form_key(scope.tenant, row, fields.endpoint, body.api_key)
        steps: list[LlmTestStep] = []
        if isinstance(key, LlmOutcome):
            steps.append(
                LlmTestStep(
                    name=SERVER_STEP,
                    ok=False,
                    code=_code(key),
                    detail=probe_message(key),
                    ms=0,
                )
            )
        else:
            connection = self._connection(fields, key, row, scope.tenant.tenant_id)
            steps.extend(await self._test_steps(connection))
        ok = all(step.ok for step in steps)
        if body.record and row is not None:
            summary = "; ".join(
                f"{step.name}: {'✓' if step.ok else '✗'}" for step in steps
            )
            await self.integrations.record_test(
                row.llm_integration_id, at=datetime.now(UTC), ok=ok, summary=summary
            )
        return LlmTestResult(ok=ok, steps=steps)

    async def _test_steps(self, connection: LlmConnection) -> list[LlmTestStep]:
        """Requirement 15: the server, then the chat model when the server answered."""

        started = time.monotonic()
        listing = await self.adapter.list_models(
            connection, operation=ProbeOperation.MODELS, details=False
        )
        offered = [model.id for model in listing.models]
        server = LlmTestStep(
            name=SERVER_STEP,
            ok=listing.probe.ok,
            code=_code(listing.probe.outcome),
            detail=(
                f"Bağlantı kuruldu; sunucuda {len(offered)} model var"
                if listing.probe.ok
                else listing.probe.message
            ),
            ms=round((time.monotonic() - started) * 1000),
        )
        steps = [server]
        if not server.ok or not connection.chat_model:
            return steps
        started = time.monotonic()
        result = await self.adapter.chat(
            connection,
            LlmChatRequest(
                system=TEST_SYSTEM_PROMPT,
                user=TEST_QUESTION,
                schema=TEST_SCHEMA,
                max_tokens=TEST_MAX_TOKENS,
                purpose=LlmPurpose.CONNECTION_TEST,
            ),
        )
        if result.ok and result.value is not None:
            answer = str(result.value.get("cevap", ""))[:TEST_ANSWER_CHARS]
            detail = f"Cevap verdi: “{answer}”"
        else:
            detail = short_reason(result.outcome, result.http_status, probe=False)
            if offered and connection.chat_model not in offered:
                detail += MODEL_NOT_LISTED
        steps.append(
            LlmTestStep(
                name=CHAT_STEP,
                ok=result.ok,
                code=_code(result.outcome),
                detail=detail,
                ms=round((time.monotonic() - started) * 1000),
            )
        )
        return steps
