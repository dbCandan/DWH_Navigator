"""question-analysis Requirement 5: the "Analiz yapılamadı" reasons come from the failure
class and never carry the server's address, its error body or an exception text. These are
the reason texts the parity test leaves out of the comparison on purpose."""

from __future__ import annotations

import pytest

from app.services.analysis.llm.port import FailureCode, ModelFailure
from app.services.analysis.pipeline import fallback_reason, health_reason

pytestmark = pytest.mark.unit

UNREACHABLE = "Model sunucusuna ulaşılamadı."
CONTEXT = (
    "Modelin bağlam penceresi tablo kataloğu için küçük (~70k token gerekir). Model sunucusunda "
    "daha geniş bağlam açın (vLLM: --max-model-len) veya Yönetim → Yapay zekâ'dan daha geniş "
    "bağlamlı bir sohbet modeli seçin."
)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (ModelFailure(FailureCode.NETWORK_POLICY_DENIED), UNREACHABLE),
        (ModelFailure(FailureCode.NAME_UNRESOLVED), UNREACHABLE),
        (ModelFailure(FailureCode.CONNECT_REFUSED), UNREACHABLE),
        (ModelFailure(FailureCode.CONNECT_ERROR), UNREACHABLE),
        (ModelFailure(FailureCode.TLS_ERROR), UNREACHABLE),
        (ModelFailure(FailureCode.TIMEOUT), UNREACHABLE),
        (
            ModelFailure(FailureCode.UNAUTHORIZED, 401),
            (
                "Model sunucusu yanıt vermedi: Sunucu HTTP 401 döndürdü "
                "(API anahtarı eksik veya geçersiz)"
            ),
        ),
        (
            ModelFailure(FailureCode.UNAUTHORIZED, 403),
            (
                "Model sunucusu yanıt vermedi: Sunucu HTTP 403 döndürdü "
                "(API anahtarı eksik veya geçersiz)"
            ),
        ),
        (
            ModelFailure(FailureCode.UPSTREAM_STATUS, 502),
            "Model sunucusu yanıt vermedi: Sunucu HTTP 502 döndürdü",
        ),
        (
            ModelFailure(FailureCode.INVALID_RESPONSE),
            "Model sunucusu yanıt vermedi: Sunucu beklenmeyen bir yanıt döndürdü",
        ),
    ],
)
def test_server_check_reasons(failure: ModelFailure, reason: str) -> None:
    assert health_reason(failure) == reason


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (ModelFailure(FailureCode.CONTEXT_EXCEEDED, 400), CONTEXT),
        (ModelFailure(FailureCode.TIMEOUT), "Model zamanında yanıt vermedi (zaman aşımı)."),
        (
            ModelFailure(FailureCode.UPSTREAM_STATUS, 504),
            "Model zamanında yanıt vermedi (zaman aşımı).",
        ),
        (ModelFailure(FailureCode.CONNECT_REFUSED), UNREACHABLE),
        (ModelFailure(FailureCode.NAME_UNRESOLVED), UNREACHABLE),
        (ModelFailure(FailureCode.TLS_ERROR), UNREACHABLE),
        (ModelFailure(FailureCode.NETWORK_POLICY_DENIED), UNREACHABLE),
        (ModelFailure(FailureCode.CONNECT_ERROR), UNREACHABLE),
        (ModelFailure(FailureCode.INVALID_JSON), "Model hatası: model geçerli JSON üretmedi"),
        (ModelFailure(FailureCode.INVALID_RESPONSE), "Model hatası: beklenmeyen yanıt"),
        (ModelFailure(FailureCode.UPSTREAM_STATUS, 500), "Model hatası: HTTP 500"),
        (ModelFailure(FailureCode.UNAUTHORIZED, 401), "Model hatası: HTTP 401"),
        (None, "Model yanıt vermedi."),
    ],
)
def test_analyst_failure_reasons(failure: ModelFailure | None, reason: str) -> None:
    assert fallback_reason(failure) == reason


def test_no_reason_carries_a_server_text() -> None:
    texts = {health_reason(ModelFailure(c, 500)) for c in FailureCode}
    texts |= {fallback_reason(ModelFailure(c, 500)) for c in FailureCode}
    assert not any("http://" in t or "https://" in t or "{" in t for t in texts)
