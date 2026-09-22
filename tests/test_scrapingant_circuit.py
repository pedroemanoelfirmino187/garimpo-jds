"""Circuit breaker e teto ScrapingAnt — não relaxa confirmer nem matcher."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import garimpo_jds as jds


AMZ = "https://www.amazon.com.br/dp/B0CQKLS4RP"
HTML_AMZ_OK = (
    "<html><body><span id=\"productTitle\">Sony DualSense PS5</span>"
    "<span class=\"a-offscreen\">R$404,27</span> B0CQKLS4RP"
    + ("x" * 80)
    + "</body></html>"
)


@pytest.fixture(autouse=True)
def _reset_ant():
    jds._scrapingant_reset_busca()
    yield
    jds._scrapingant_reset_busca()


def _resp(status, html="", json_data=None):
    def _json():
        if json_data is None:
            raise ValueError("not json")
        return json_data

    return SimpleNamespace(status_code=status, text=html, json=_json)


def test_a_http_409_marca_indisponivel_e_nao_repete(monkeypatch):
    chamadas = []

    def fake_get(url, params=None, headers=None, timeout=None):
        chamadas.append(params.get("url") if params else url)
        return _resp(409, "concurrent")

    monkeypatch.setattr(jds, "_chaves_env", lambda *n: ["k1", "k2"])
    monkeypatch.setattr(jds.requests, "get", fake_get)

    assert jds._scrapingant_baixar("https://exemplo.com/a") == ""
    assert jds._scrapingant_st().indisponivel is True
    assert len(chamadas) == 1
    assert jds._scrapingant_baixar("https://exemplo.com/b") == ""
    assert jds._scrapingant_baixar("https://exemplo.com/c") == ""
    assert chamadas == ["https://exemplo.com/a"]


def test_b_http_429_marca_indisponivel_e_nao_repete(monkeypatch):
    chamadas = []

    def fake_get(url, params=None, headers=None, timeout=None):
        chamadas.append(params.get("url") if params else url)
        return _resp(429, "rate")

    monkeypatch.setattr(jds, "_chaves_env", lambda *n: ["k1", "k2"])
    monkeypatch.setattr(jds.requests, "get", fake_get)

    assert jds._scrapingant_baixar("https://exemplo.com/a") == ""
    assert jds._scrapingant_st().indisponivel is True
    assert jds._scrapingant_baixar("https://exemplo.com/b") == ""
    assert chamadas == ["https://exemplo.com/a"]


def test_c_teto_global_3_chamadas_por_busca(monkeypatch):
    chamadas = []

    def fake_get(url, params=None, headers=None, timeout=None):
        chamadas.append(params.get("url") if params else url)
        return _resp(200, json_data={"html": "<html>ok</html>"})

    monkeypatch.setattr(jds, "_chaves_env", lambda *n: ["k1"])
    monkeypatch.setattr(jds.requests, "get", fake_get)

    for i in range(5):
        jds._scrapingant_baixar(f"https://exemplo.com/{i}")
    assert len(chamadas) == 3
    assert jds._scrapingant_st().chamadas == 3
    assert jds._scrapingant_pode_usar() is False


def test_d_depois_indisponivel_get_direto_segue(monkeypatch):
    ant_urls = []

    def fake_ant(url, params=None, headers=None, timeout=None):
        ant_urls.append(params.get("url") if params else url)
        return _resp(409, "busy")

    class Sess:
        def get(self, url, headers=None, timeout=None):
            return _resp(200, HTML_AMZ_OK)

    monkeypatch.setattr(jds, "_chaves_env", lambda *n: ["k1"])
    monkeypatch.setattr(jds.requests, "get", fake_ant)
    jds._scrapingant_baixar("https://exemplo.com/bloqueado")
    assert jds._scrapingant_st().indisponivel is True
    monkeypatch.setattr(jds, "_sessao_http", lambda: Sess())

    html, origem = jds._baixar_url_loja(AMZ, timeout=8, usar_scrapingant=True)
    assert origem == "direto"
    assert "DualSense" in html
    assert ant_urls == ["https://exemplo.com/bloqueado"]


def test_e_confirmer_html_vazio_ou_bloqueado_nao_vira_oferta():
    item = {
        "titulo": "Sony DualSense PS5",
        "preco_num": 404.27,
        "url": AMZ,
        "original_url": AMZ,
        "plataforma": "amazon",
        "loja": "Amazon",
        "fonte": "google",
        "pais": "BR",
        "foto": "https://m.media-amazon.com/x.jpg",
        "imagem": "https://m.media-amazon.com/x.jpg",
    }
    motivos = {}
    assert jds._jds_confirmar_oferta_na_pagina(item, html="", motivos=motivos) is None
    assert motivos.get("html_vazio") == 1
    motivos = {}
    bloqueado = "<html>account-verification acesse sua conta unusual traffic</html>" + ("x" * 80)
    assert jds._jds_confirmar_oferta_na_pagina(item, html=bloqueado, motivos=motivos) is None
    assert motivos.get("pagina_bloqueada") == 1


def test_e_confirmer_nao_chama_scrapingant(monkeypatch):
    visto = []

    def spy(url, browser=True):
        visto.append(url)
        return HTML_AMZ_OK

    class Sess:
        def get(self, url, headers=None, timeout=None):
            return _resp(200, "")

    monkeypatch.setattr(jds, "_scrapingant_baixar", spy)
    monkeypatch.setattr(
        jds,
        "_chaves_env",
        lambda *n: ["k1"] if any("SCRAPING" in str(x).upper() for x in n) else [],
    )
    monkeypatch.setattr(jds, "_sessao_http", lambda: Sess())
    html = jds._jds_html_anuncio(AMZ)
    assert html == ""
    assert visto == []
    item = {
        "titulo": "Sony DualSense PS5",
        "preco_num": 404.27,
        "url": AMZ,
        "original_url": AMZ,
        "plataforma": "amazon",
        "loja": "Amazon",
        "fonte": "google",
        "pais": "BR",
        "foto": "https://m.media-amazon.com/x.jpg",
        "imagem": "https://m.media-amazon.com/x.jpg",
    }
    assert jds._jds_confirmar_oferta_na_pagina(item, baixar=lambda u: "") is None
    assert visto == []
