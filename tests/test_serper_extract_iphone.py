"""Extração Serper: amostra real de Apple iPhone 15 128GB (apos_extrair=0)."""
from __future__ import annotations

import garimpo_jds as jds

Q = "Apple iPhone 15 128GB"
OSHOP = (
    "https://www.google.com/search?ibp=oshop&q=iphone+15+128gb"
    "&prds=localAnnotatedOfferId:1,catalogid:871091021334399569"
)
IMG = "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:iphone15"
DP = "https://www.amazon.com.br/dp/B0C76P138X"

AMAZON_RETAIL = {
    "title": "Apple iPhone 15",
    "source": "Amazon.com.br - Retail",
    "price": "R$ 4.776,77 agora",
    "link": OSHOP,
    "imageUrl": IMG,
}
AMAZON_SEMINOVO = {
    "title": "Apple iPhone 15 (128 GB) — Preto (Seminovo)",
    "source": "Amazon.com.br - Seller",
    "price": "R$ 3.742,99 agora",
    "link": OSHOP,
    "imageUrl": IMG,
}
CARREFOUR = {
    "title": "Apple Iphone 15 128Gb E-Sim 5G Tela 6.1 Preto A2846",
    "source": "Carrefour",
    "price": "R$ 4.139,10 agora",
    "link": OSHOP,
    "imageUrl": IMG,
}
HORIZON = {
    "title": "Apple iPhone 15 128GB 5G - Vitrine...",
    "source": "Horizon Play",
    "price": "R$ 3.205,83 agora",
    "link": OSHOP,
    "imageUrl": IMG,
}


def _sem_rede(card):
    return jds._jds_item_serper(
        Q, card, pais="BR", baixar=lambda u: "", organic=lambda *a, **k: [],
    )


def test_preco_agora_parseia():
    assert jds._limpar_preco_serper("R$ 4.776,77 agora", "BR") == 4776.77
    assert jds._preco_item_serper(AMAZON_RETAIL, "BR") == 4776.77


def test_amazon_source_e_allowlist_ok():
    assert jds._source_loja_oficial("Amazon.com.br - Retail", "BR")
    assert jds._loja_do_texto("Amazon.com.br - Retail") == "amazon"
    assert jds._source_loja_oficial("Amazon.com.br - Seller", "BR")
    assert jds._loja_do_texto("Amazon.com.br - Seller") == "amazon"


def test_amazon_retail_titulo_sem_128gb_nao_e_shopping_ok():
    assert jds._tokens_busca(Q) == ["apple", "iphone", "15", "128gb"]
    assert jds._titulo_shopping_ok(Q, "Apple iPhone 15") is False
    assert jds._token_no_titulo("128gb", "apple iphone 15") is False


def test_amazon_retail_nao_extrai_nem_com_dp():
    assert _sem_rede(AMAZON_RETAIL) is None
    card = dict(AMAZON_RETAIL, link=DP)
    assert _sem_rede(card) is None


def test_amazon_seminovo_nao_extrai():
    assert jds._titulo_usado(AMAZON_SEMINOVO["title"]) is True
    assert jds._titulo_shopping_ok(Q, AMAZON_SEMINOVO["title"]) is False
    assert _sem_rede(AMAZON_SEMINOVO) is None
    assert _sem_rede(dict(AMAZON_SEMINOVO, link=DP)) is None


def test_carrefour_e_horizon_fora_da_allowlist():
    assert jds._source_loja_oficial("Carrefour", "BR") is False
    assert jds._loja_do_texto("Carrefour") == ""
    assert jds._source_loja_oficial("Horizon Play", "BR") is False
    assert jds._loja_do_texto("Horizon Play") == ""
    assert _sem_rede(CARREFOUR) is None
    assert _sem_rede(HORIZON) is None


def test_amostra_producao_apos_extrair_zero():
    cands = jds._jds_extrair_candidatos(
        Q,
        [AMAZON_RETAIL, AMAZON_SEMINOVO, CARREFOUR, HORIZON],
        pais="BR",
        baixar=lambda u: "",
        organic=lambda *a, **k: [],
    )
    assert cands == []


def _html_pdp(titulo, preco="R$ 4.776,77", asin=None):
    from tests.test_google_shopping_url import ASIN_RETAIL
    asin = asin or ASIN_RETAIL
    return (
        f"<html><body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco}</span>"
        f"<input name=\"ASIN\" value=\"{asin}\">{asin}{'x' * 80}</body></html>"
    )


def _baixar_ponte_e_pdp(titulo_pdp, preco="R$ 4.776,77"):
    from tests.test_google_shopping_url import ASIN_RETAIL, _html_amazon_dois_cards
    google_html = _html_amazon_dois_cards()
    pdp_html = _html_pdp(titulo_pdp, preco=preco, asin=ASIN_RETAIL)

    def _fn(url):
        u = (url or "").lower()
        if "google." in u:
            return google_html
        if ASIN_RETAIL.lower() in u:
            return pdp_html
        return ""
    return _fn


def test_card_curto_pdp_128gb_avanca():
    from tests.test_google_shopping_url import ASIN_RETAIL
    item = jds._jds_item_serper(
        Q, AMAZON_RETAIL, pais="BR",
        baixar=_baixar_ponte_e_pdp("Apple iPhone 15 128GB Preto"),
        organic=lambda *a, **k: [],
    )
    assert item is not None
    assert item["plataforma"] == "amazon"
    assert ASIN_RETAIL in (item.get("url") or "")
    assert "128" in (item.get("titulo") or "")
    assert jds._titulo_shopping_ok(Q, AMAZON_RETAIL["title"]) is False


def test_card_curto_pdp_256gb_rejeita():
    assert jds._jds_item_serper(
        Q, AMAZON_RETAIL, pais="BR",
        baixar=_baixar_ponte_e_pdp("Apple iPhone 15 256GB Preto"),
        organic=lambda *a, **k: [],
    ) is None


def test_card_curto_pdp_sem_capacidade_rejeita():
    assert jds._jds_item_serper(
        Q, AMAZON_RETAIL, pais="BR",
        baixar=_baixar_ponte_e_pdp("Apple iPhone 15 Preto"),
        organic=lambda *a, **k: [],
    ) is None


def test_seminovo_rejeita_mesmo_com_pdp_128gb():
    from tests.test_google_shopping_url import ASIN_RETAIL, ASIN_SELLER, _html_amazon_dois_cards
    google_html = _html_amazon_dois_cards()
    pdp = _html_pdp("Apple iPhone 15 128GB Preto", asin=ASIN_SELLER)

    def baixar(url):
        u = (url or "").lower()
        if "google." in u:
            return google_html
        if ASIN_SELLER.lower() in u or ASIN_RETAIL.lower() in u:
            return pdp if ASIN_SELLER.lower() in u else _html_pdp(
                "Apple iPhone 15 128GB Preto", asin=ASIN_RETAIL,
            )
        return ""

    assert jds._jds_item_serper(
        Q, AMAZON_SEMINOVO, pais="BR", baixar=baixar, organic=lambda *a, **k: [],
    ) is None


def test_carrefour_horizon_rejeitam_mesmo_com_pdp():
    baixar = _baixar_ponte_e_pdp("Apple iPhone 15 128GB Preto")
    assert jds._jds_item_serper(Q, CARREFOUR, pais="BR", baixar=baixar, organic=lambda *a, **k: []) is None
    assert jds._jds_item_serper(Q, HORIZON, pais="BR", baixar=baixar, organic=lambda *a, **k: []) is None
