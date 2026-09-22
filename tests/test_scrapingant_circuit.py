"""GET direto só — ZenRows/ScrapingAnt nunca são chamados."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import garimpo_jds as jds


AMZ = "https://www.amazon.com.br/dp/B0CQKLS4RP"
HTML_AMZ_OK = (
    "<html><body><span id=\"productTitle\">Sony DualSense PS5</span>"
    "<span class=\"a-offscreen\">R$404,27</span> B0CQKLS4RP"
    + ("x" * 80)
    + "</body></html>"
)


def _resp(status, html=""):
    return SimpleNamespace(status_code=status, text=html, headers={})


def _urls_proibidas(hits):
    blob = " ".join(str(u) for u in hits).lower()
    return "zenrows.com" in blob or "scrapingant.com" in blob


def test_fonte_sem_url_zenrows_ou_scrapingant():
    src = inspect.getsource(jds)
    assert "api.zenrows.com" not in src
    assert "api.scrapingant.com" not in src
    assert "scrapingant.com/v2" not in src
    baixar = inspect.getsource(jds._baixar_url_loja)
    assert "zenrows" not in baixar.lower()
    assert "scrapingant" not in baixar.lower()
    assert "_zenrows_baixar" not in src
    assert "_scrapingant_baixar" not in src
    assert "usar_scrapingant" not in inspect.getsource(jds._baixar_url_loja)


def test_zenrows_nunca_e_chamado_mesmo_com_chave(monkeypatch):
    hits = []

    def fake_requests_get(url, *args, **kwargs):
        hits.append(url)
        raise AssertionError("requests.get não deve ir ao proxy")

    class Sess:
        def get(self, url, headers=None, timeout=None):
            hits.append(url)
            return _resp(200, HTML_AMZ_OK)

    monkeypatch.setenv("ZENROWS_API_KEY", "chave-zenrows")
    monkeypatch.setenv("ZENROWS_KEY", "chave-zenrows-2")
    monkeypatch.setattr(jds.requests, "get", fake_requests_get)
    monkeypatch.setattr(jds, "_sessao_http", lambda: Sess())
    html, origem = jds._baixar_url_loja(AMZ, timeout=8)
    assert origem == "direto"
    assert "DualSense" in html
    assert not _urls_proibidas(hits)


def test_scrapingant_nunca_e_chamado_mesmo_com_chave(monkeypatch):
    hits = []

    def fake_requests_get(url, *args, **kwargs):
        hits.append(url)
        raise AssertionError("requests.get não deve ir ao proxy")

    class Sess:
        def get(self, url, headers=None, timeout=None):
            hits.append(url)
            return _resp(200, "")

    monkeypatch.setenv("SCRAPINGANT_API_KEY", "chave-ant")
    monkeypatch.setenv("SCRAPING_ANT_KEY", "chave-ant-2")
    monkeypatch.setenv("SCRAPINGANT_API_KEY_2", "chave-ant-3")
    monkeypatch.setattr(jds.requests, "get", fake_requests_get)
    monkeypatch.setattr(jds, "_sessao_http", lambda: Sess())
    html, origem = jds._baixar_url_loja(AMZ, timeout=8)
    assert html == ""
    assert origem == ""
    assert hits == [AMZ]
    assert not _urls_proibidas(hits)
    html2 = jds._jds_html_anuncio(AMZ)
    assert html2 == ""
    assert not _urls_proibidas(hits)


def test_get_direto_continua_funcionando(monkeypatch):
    class Sess:
        def get(self, url, headers=None, timeout=None):
            assert url == AMZ
            return _resp(200, HTML_AMZ_OK)

    monkeypatch.setattr(jds, "_sessao_http", lambda: Sess())
    html, origem = jds._baixar_url_loja(AMZ, timeout=8)
    assert origem == "direto"
    assert "productTitle" in html
    html2 = jds._jds_html_anuncio(AMZ)
    assert "B0CQKLS4RP" in html2


def test_html_vazio_continua_rejeitado():
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


def test_allowlist_br_e_matcher_intactos():
    assert jds._lojas_do_pais("BR") == ("amazon", "mercado_livre", "shopee")
    assert jds._titulo_shopping_ok("iPhone 15 128GB", "Apple iPhone 15 128GB Preto")
    assert jds._jds_mesmo_produto(
        "Apple iPhone 15 128GB Preto",
        "Apple iPhone 15 128GB Preto",
        "iPhone 15 128GB",
    )
