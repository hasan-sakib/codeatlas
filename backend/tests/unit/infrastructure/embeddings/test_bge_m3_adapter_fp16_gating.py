"""Separate from test_bge_m3_adapter.py deliberately: that file's autouse
fixture stubs out `_load_model` entirely (so no test there ever triggers a
real model load), which would defeat testing `_load_model` itself here.

Regression coverage for a real bug found via Docker Compose verification
(Module 19): `EMBEDDING__USE_FP16=true` was passed straight through to
`BGEM3FlagModel` regardless of hardware, and fp16 matmul on a CPU-only
container silently produced an all-NaN embedding for every query — no
exception, just garbage that only surfaced downstream as a confusing
Qdrant "Format error in JSON body" (NaN isn't valid JSON).
"""

from unittest.mock import MagicMock

import pytest

from app.core.config import EmbeddingSettings
from app.infrastructure.embeddings import bge_m3_adapter as bma
from app.infrastructure.embeddings.bge_m3_adapter import BgeM3Adapter


def _settings(*, use_fp16: bool) -> EmbeddingSettings:
    return EmbeddingSettings(  # type: ignore[call-arg]
        model_id="fake-model:v1",
        use_fp16=use_fp16,
        batch_size=2,
        cache_ttl_seconds=100,
    )


def test_fp16_setting_is_honored_when_cuda_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_model_cls = MagicMock()
    monkeypatch.setattr(bma, "BGEM3FlagModel", mock_model_cls)
    monkeypatch.setattr(bma.torch.cuda, "is_available", lambda: True)

    adapter = BgeM3Adapter(cache=MagicMock(), settings=_settings(use_fp16=True))
    adapter._load_model()

    mock_model_cls.assert_called_once_with("BAAI/bge-m3", use_fp16=True)


def test_fp16_is_force_disabled_without_cuda_even_if_configured_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_model_cls = MagicMock()
    monkeypatch.setattr(bma, "BGEM3FlagModel", mock_model_cls)
    monkeypatch.setattr(bma.torch.cuda, "is_available", lambda: False)

    adapter = BgeM3Adapter(cache=MagicMock(), settings=_settings(use_fp16=True))
    adapter._load_model()

    mock_model_cls.assert_called_once_with("BAAI/bge-m3", use_fp16=False)


def test_fp16_stays_disabled_without_cuda_when_configured_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_model_cls = MagicMock()
    monkeypatch.setattr(bma, "BGEM3FlagModel", mock_model_cls)
    monkeypatch.setattr(bma.torch.cuda, "is_available", lambda: False)

    adapter = BgeM3Adapter(cache=MagicMock(), settings=_settings(use_fp16=False))
    adapter._load_model()

    mock_model_cls.assert_called_once_with("BAAI/bge-m3", use_fp16=False)
