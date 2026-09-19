"""Fallback Serper Organic quando a ponte Google Shopping não devolve PDP."""
from __future__ import annotations

import garimpo_jds as jds
from tests.test_google_shopping_url import IMG, PONTE, _card


ASIN = "B0CP6CVJSG"
PDP = f"https://www.amazon.com.br/dp/{ASIN}"
BUSCA = "https://www.amazon.com.br/s?k=iphone+15+128gb"
TERMO = "iphone 15 128gb"
TITULO = "Apple iPhone 15 128GB Preto"
PRECO = "R$ 4.776,77"


def _html_pdp(titulo=TITULO, preco="R$ 4.776,77", asin=ASIN):
    return f"""
    <html>
      <span id="productTitle">{titulo}</span>
      <span class="a-offscreen">{preco}</span>
      <input name="ASIN" value="{asin}">
      {asin}
    </html>
    """


def _baixar(google_html, pdp_html):
    def _fn(url):
        u = (url or "").lower()
        if "google." in u:
            return google_html
        if "/dp/" in u or "/p/" in u or "-i." in u:
            return pdp_html
        return ""
    return _fn


def _organic(links):
    def _fn(q, pais="BR"):
        assert "site:amazon.com.br" in q
        assert TITULO.split()[0] in q or "iPhone" in q or "iphone" in q.lower()
        return [{"link": link, "title": TITULO} for link in links]
    return _fn


def _item(card=None, google_html="<html></html>", pdp_html="", links=None):
    card = card or _card(title=TITULO, price=PRECO, link=PONTE)
    return jds._jds_item_serper(
        TERMO,
        card,
        pais="BR",
        baixar=_baixar(google_html, pdp_html),
        organic=_organic(links or []),
    )


def test_fallback_encontra_pdp_exata_quando_ponte_falha():
    item = _item(pdp_html=_html_pdp(), links=[PDP])
    assert item is not None
    assert ASIN in item["url"]
    assert jds._url_anuncio_exato(item["url"], "amazon")
    assert "google." not in item["url"].lower()
    assert "/s?" not in item["url"]
    assert abs(item["preco_num"] - 4776.77) < 0.01
    assert "iPhone 15" in item["titulo"] or "iphone 15" in item["titulo"].lower()
    assert item["foto"] == IMG


def test_fallback_pagina_de_busca_rejeita():
    assert _item(pdp_html=_html_pdp(), links=[BUSCA]) is None
    assert _item(
        pdp_html=_html_pdp(),
        links=["https://www.mercadolivre.com.br/ofertas"],
    ) is None
    assert _item(
        pdp_html=_html_pdp(),
        links=["https://shopee.com.br/search?keyword=iphone"],
    ) is None


def test_fallback_titulo_diferente_rejeita():
    html = _html_pdp(titulo="Samsung Galaxy S24 128GB Preto")
    assert _item(pdp_html=html, links=[PDP]) is None


def test_fallback_preco_diferente_rejeita():
    html = _html_pdp(preco="R$ 9.999,00")
    assert _item(pdp_html=html, links=[PDP]) is None


def test_fallback_sem_pagina_acessivel_rejeita():
    assert _item(pdp_html="", links=[PDP]) is None
    assert _item(pdp_html="<html></html>", links=[PDP]) is None


def test_fallback_usado_seminovo_rejeita():
    html = _html_pdp(titulo="Apple iPhone 15 128GB Preto Seminovo")
    assert _item(pdp_html=html, links=[PDP]) is None
    card = _card(title="Apple iPhone 15 128GB Preto Usado", price=PRECO, link=PONTE)
    assert _item(card=card, pdp_html=_html_pdp(), links=[PDP]) is None


def test_fallback_nao_roda_quando_ponte_html_ja_resolve():
    from tests.test_google_shopping_url import _html_amazon_dois_cards, ASIN_RETAIL

    def organic_boom(*_a, **_k):
        raise AssertionError("organic nao deve rodar se a ponte HTML resolveu")

    item = jds._jds_item_serper(
        TERMO,
        _card(title=TITULO, price=PRECO),
        pais="BR",
        baixar=lambda url: _html_amazon_dois_cards() if "google." in url else "",
        organic=organic_boom,
    )
    assert item is not None
    assert ASIN_RETAIL in item["url"]


def test_fallback_preco_final_e_o_da_pagina_quando_confirma():
    html = _html_pdp(preco="R$ 4.780,00")
    item = _item(pdp_html=html, links=[PDP])
    assert item is not None
    assert abs(item["preco_num"] - 4780.00) < 0.01


def test_fallback_alimenta_matcher_e_confirmer_com_pdp():
    card = _card(title=TITULO, price=PRECO, link=PONTE)
    html_pdp = _html_pdp()
    cands = jds._jds_extrair_candidatos(
        TERMO,
        [card],
        pais="BR",
        baixar=_baixar("<html>bloqueado</html>", html_pdp),
        organic=_organic([PDP]),
    )
    assert len(cands) == 1
    assert ASIN in cands[0]["url"]
    matched = jds._jds_comparar_mesmo_produto(TERMO, cands, pais="BR")
    assert matched
    ok = jds._jds_confirmar_listings(
        matched, pais="BR", baixar=_baixar("<html></html>", html_pdp),
    )
    assert ok
    assert ASIN in ok[0]["url"]
    assert "google." not in ok[0]["url"].lower()
