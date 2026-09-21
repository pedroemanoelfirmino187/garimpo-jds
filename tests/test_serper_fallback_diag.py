"""Fallback Serper: diagnóstico da consulta atual, sem herdar a busca anterior."""
from __future__ import annotations

import garimpo_jds as jds
from api.main import _resposta_ofertas


def _diag_searchapi_iphone_vazio():
    return {
        "status": "SEARCHAPI_EMPTY",
        "q": "Apple iPhone 15 128GB",
        "shopping_results": 40,
        "candidates": 2,
        "candidatos_com_product_token": 2,
        "offers_received": 2,
        "offers_rejected": 2,
        "offers_confirmed": 0,
        "rejeicoes": {"loja_fora": 2},
    }


def _semear_diag_tv():
    jds._ULTIMO_DIAG_SERPER.clear()
    jds._ULTIMO_DIAG_SERPER.update({
        "q": "smart tv 50",
        "fonte": "searchapi",
        "SEARCHAPI_SUCCESS": True,
        "fallback": False,
        "ofertas": 1,
    })


def test_resposta_garimpar_total_segue_lista_nao_o_diag():
    item = {
        "titulo": "Apple iPhone 15 128GB Preto",
        "preco_num": 4299.0,
        "preco_numerico": 4299.0,
        "loja": "Amazon",
        "plataforma": "amazon",
        "original_url": "https://www.amazon.com.br/dp/B0C76P138X",
        "url": "https://www.amazon.com.br/dp/B0C76P138X",
        "foto": "https://m.media-amazon.com/images/I/xx.jpg",
        "pais": "BR",
        "fonte": "serper",
    }
    corpo = _resposta_ofertas("Apple iPhone 15 128GB", [item], pais="BR")
    assert corpo["total"] == 1
    assert len(corpo["ofertas"]) == 1
    vazio = _resposta_ofertas("Apple iPhone 15 128GB", [], pais="BR")
    assert vazio["total"] == 0
    assert vazio["ofertas"] == []
    assert vazio["ok"] is False
    assert vazio["status"] == "empty"


def test_fallback_vazio_nao_herda_q_nem_ofertas_da_tv(monkeypatch):
    _semear_diag_tv()
    monkeypatch.setattr(
        "jds_searchapi.buscar_ofertas_searchapi",
        lambda *a, **k: ([], "SEARCHAPI_EMPTY"),
    )
    monkeypatch.setattr("jds_searchapi.ultimo_diag_searchapi", _diag_searchapi_iphone_vazio)

    def serper_vazio(termo, usar_cache=True, limite=20, pais="BR"):
        assert termo == "Apple iPhone 15 128GB"
        assert usar_cache is False
        return []

    monkeypatch.setattr(jds, "buscar_ofertas_serper_shopping", serper_vazio)
    out = jds.buscar_ofertas_jds_shopping(
        "Apple iPhone 15 128GB", usar_cache=False, pais="BR",
    )
    assert out == []
    diag = jds.ultimo_diag_serper()
    assert diag["q"] == "Apple iPhone 15 128GB"
    assert diag["q"] != "smart tv 50"
    assert diag.get("SEARCHAPI_SUCCESS") is not True
    assert diag["SEARCHAPI_EMPTY"] is True
    assert diag["FALLBACK_SERPER"] is True
    assert diag["fallback"] is True
    assert diag["ofertas"] == 0
    corpo = _resposta_ofertas("Apple iPhone 15 128GB", out, pais="BR")
    assert corpo["total"] == 0
    assert corpo["diagnostico"]["ofertas"] == 0


def test_fallback_com_uma_oferta_preenche_total_e_diag(monkeypatch):
    _semear_diag_tv()
    item = {
        "titulo": "Apple iPhone 15 128GB Preto",
        "preco_num": 4299.0,
        "loja": "Amazon",
        "plataforma": "amazon",
        "original_url": "https://www.amazon.com.br/dp/B0C76P138X",
        "url": "https://www.amazon.com.br/dp/B0C76P138X",
        "foto": "https://m.media-amazon.com/images/I/xx.jpg",
        "pais": "BR",
        "fonte": "serper",
    }
    monkeypatch.setattr(
        "jds_searchapi.buscar_ofertas_searchapi",
        lambda *a, **k: ([], "SEARCHAPI_EMPTY"),
    )
    monkeypatch.setattr("jds_searchapi.ultimo_diag_searchapi", _diag_searchapi_iphone_vazio)
    monkeypatch.setattr(jds, "buscar_ofertas_serper_shopping", lambda *a, **k: [item])
    out = jds.buscar_ofertas_jds_shopping(
        "Apple iPhone 15 128GB", usar_cache=False, pais="BR",
    )
    assert len(out) == 1
    diag = jds.ultimo_diag_serper()
    assert diag["q"] == "Apple iPhone 15 128GB"
    assert diag["ofertas"] == 1
    assert diag.get("SEARCHAPI_SUCCESS") is not True
    corpo = _resposta_ofertas("Apple iPhone 15 128GB", out, pais="BR")
    assert corpo["total"] == 1
    assert corpo["ok"] is True
    assert corpo["ofertas"][0]["plataforma"] == "amazon"


def test_serper_shopping_registra_onde_a_oferta_cai(monkeypatch):
    cru = [{
        "title": "Apple iPhone 15 128GB Preto",
        "source": "Amazon.com.br",
        "price": "R$ 4.299,00",
        "extracted_price": 4299.0,
        "link": "https://www.amazon.com.br/dp/B0C76P138X",
        "productLink": "https://www.amazon.com.br/dp/B0C76P138X",
        "imageUrl": "https://m.media-amazon.com/images/I/xx.jpg",
    }]
    extraido = [{
        "titulo": cru[0]["title"],
        "preco_num": 4299.0,
        "plataforma": "amazon",
        "loja": "Amazon",
        "original_url": cru[0]["link"],
        "url": cru[0]["link"],
        "foto": cru[0]["imageUrl"],
        "fonte": "serper",
        "pais": "BR",
    }]
    monkeypatch.setattr(jds, "_post_serper_shopping", lambda *a, **k: (200, cru, {"gl": "br", "hl": "pt-br"}, ""))
    monkeypatch.setattr(jds, "_jds_extrair_candidatos", lambda *a, **k: extraido)
    monkeypatch.setattr(jds, "_jds_comparar_mesmo_produto", lambda *a, **k: extraido)
    monkeypatch.setattr(jds, "_jds_confirmar_listings", lambda *a, **k: [])
    out = jds.buscar_ofertas_serper_shopping(
        "Apple iPhone 15 128GB", usar_cache=False, pais="BR",
    )
    assert out == []
    diag = jds.ultimo_diag_serper()
    assert diag["q"] == "Apple iPhone 15 128GB"
    assert diag["shopping"] == 1
    assert diag["apos_extrair"] == 1
    assert diag["apos_matcher"] == 1
    assert diag["apos_confirmer"] == 0
    assert diag["ofertas"] == 0
    assert diag["amostra"][0]["source"] == "Amazon.com.br"
    assert "iPhone 15 128GB" in diag["amostra"][0]["title"]
