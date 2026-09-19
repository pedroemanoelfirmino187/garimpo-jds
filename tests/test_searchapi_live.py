"""Único teste opcional contra SearchApi real. Não roda no CI."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    (os.environ.get("JDS_LIVE_SEARCHAPI") or "").strip() != "1"
    or not (os.environ.get("SEARCHAPI_API_KEY") or "").strip(),
    reason="live SearchApi desligado",
)


def test_live_searchapi_uma_consulta():
    import jds_searchapi as sap

    ofertas, status = sap.buscar_ofertas_searchapi(
        "controle ps5 sony",
        pais="BR",
        usar_cache=True,
        confirmar=False,
    )
    assert status in {"SEARCHAPI_SUCCESS", "SEARCHAPI_EMPTY", "SEARCHAPI_ERROR"}
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("product_offers_requests", 0) <= 3
    assert "api_key" not in str(diag).lower()
    if ofertas:
        assert ofertas[0].get("original_url")
