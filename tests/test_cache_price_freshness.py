"""Garantias de frescor do cache final de ofertas.

O cache da busca existe para reduzir chamadas repetidas, mas não pode manter
preços de marketplace por horas.
"""
from __future__ import annotations

from unittest.mock import patch

import garimpo_jds as jds


def test_cache_final_expira_em_15_minutos(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_GARIMPO_DB", str(tmp_path / "cache.db"))
    termo = "controle de ps5"
    pais = "BR"
    agora = 1_000_000.0
    chave = (jds._termo_cache_norm(termo), pais)
    produto = {
        "titulo": "DualSense PS5",
        "preco_num": 439.90,
        "plataforma": "amazon",
        "original_url": "https://www.amazon.com.br/dp/B096SJTF8F",
    }

    monkeypatch.setitem(
        jds._MEM_CACHE,
        chave,
        {"quando": agora, "produtos": [produto]},
    )

    with patch.object(jds.time, "time", return_value=agora + 14 * 60 + 59):
        assert jds._ler_cache_garimpo(termo, pais=pais)

    with patch.object(jds.time, "time", return_value=agora + 15 * 60 + 1):
        assert jds._ler_cache_garimpo(termo, pais=pais) is None


def test_cache_ttl_nao_e_mais_duas_horas():
    assert jds.CACHE_TTL_SEG == 15 * 60
