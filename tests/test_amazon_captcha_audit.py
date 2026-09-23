"""Auditoria do atalho Amazon CAPTCHA. Sem APIs reais. Sem alterar o matcher."""
from __future__ import annotations

import copy

import garimpo_jds as jds
import jds_searchapi as sap

from tests.test_lab_search_logic import (
    HTML_CAPTCHA_AMZ,
    HTML_ML_ANTIBOT,
    PDP_AMZ,
    PDP_ML,
    PRECO_TV,
    Q_TV,
    TITULO_TV,
    _html_pdp_ok,
    _item_tv,
)

ASIN_OK = "B0GSH89DG4"
ASIN_OUTRO = "B0CQKLS4RP"
PDP_OUTRO = f"https://www.amazon.com.br/dp/{ASIN_OUTRO}"
GSHOP = (
    "https://www.google.com/search?ibp=oshop&q=smart+tv+50"
    "&prds=localAnnotatedOfferId:1,catalogid:1"
)


def _amz(**kwargs):
    item = _item_tv("amazon")
    item["vendedor_oferta"] = "Amazon.com.br"
    for k, v in kwargs.items():
        if k == "listing":
            item["listing_source"].update(v)
        else:
            item[k] = v
    return item


def _http_amz_prod(asin, title, price, extra=None, http=200, domain="amazon.com.br"):
    extra = extra or {}

    def http_get(params):
        assert params.get("engine") == "amazon_product"
        assert "api_key" not in params
        assert "key" not in params
        assert params.get("amazon_domain") == domain
        if http >= 400:
            return http, {}, "{}"
        prod = {
            "asin": asin,
            "title": title,
            "extracted_price": price,
            "condition": "Novo",
        }
        prod.update(extra)
        return 200, {"product": prod}, "{}"

    return http_get


def _captcha(item, html=HTML_CAPTCHA_AMZ, http_get=None, produto="auto"):
    motivos = sap._motivos_zerados()
    if http_get is None and produto == "auto":
        asin = jds._asin_de_pdp_amazon(item.get("original_url") or item.get("url") or "")
        if asin:
            http_get = _http_amz_prod(asin, item.get("titulo"), item.get("preco_num"))
    ok = jds._jds_confirmar_oferta_na_pagina(
        item, html=html, motivos=motivos, http_get=http_get, usar_cache=False,
    )
    return ok, motivos


def test_inversao_a_asin_listing_diferente_da_url():
    item = _amz()
    item["listing_source"]["url"] = PDP_OUTRO
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1
    assert jds._asin_amazon(item["original_url"]) != jds._asin_amazon(item["listing_source"]["url"])


def test_inversao_b_product_id_ausente_nao_e_identidade():
    """product_id Google não prova ASIN. Sem ele a rota amazon_product ainda vale."""
    item = _amz(listing={"product_id": ""})
    ok, motivos = _captcha(item)
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert jds._searchapi_amazon_captcha_estruturado_ok(
        item, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is True


def test_inversao_c_preco_diferente():
    item = _amz(preco_num=1849.0, listing={"preco_num": 2999.0, "extracted_price": 2999.0})
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_inversao_d_url_amazon_outro_asin():
    item = _amz(url=PDP_OUTRO, original_url=PDP_OUTRO)
    item["listing_source"]["url"] = PDP_AMZ
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1 or motivos["url_nao_exata"] >= 1


def test_inversao_e_url_google_shopping():
    item = _amz(url=GSHOP, original_url=GSHOP)
    item["listing_source"]["url"] = GSHOP
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["url_nao_exata"] >= 1
    assert ok is None or "google.com/search" not in (ok.get("original_url") or "")


def test_inversao_f_consulta_128_oferta_256():
    tit = "Apple iPhone 15 256GB Preto"
    item = _amz(
        titulo=tit,
        consulta="iphone 15 128gb",
        url="https://www.amazon.com.br/dp/B0CQKLS4RP",
        original_url="https://www.amazon.com.br/dp/B0CQKLS4RP",
        listing={
            "titulo": tit,
            "url": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "consulta": "iphone 15 128gb",
        },
    )
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos.get("pagina_bloqueada", 0) >= 1 or motivos.get("variante_nao_bate", 0) >= 1


def test_inversao_g_ps5_vs_ps5_slim():
    tit = "Console PlayStation 5 Slim"
    item = _amz(
        titulo=tit,
        consulta="playstation 5",
        listing={"titulo": tit, "consulta": "playstation 5"},
    )
    ok, _motivos = _captcha(item)
    assert ok is None
    assert jds._jds_anuncio_bate_consulta("playstation 5", tit) is False or (
        jds._searchapi_amazon_captcha_estruturado_ok(item, PDP_AMZ, tit, PRECO_TV, pais="BR") is False
    )


def test_inversao_h_dualsense_branco_vs_preto():
    tit = "Sony DualSense Wireless Controller Black"
    item = _amz(
        titulo=tit,
        consulta="sony dualsense ps5 white",
        listing={"titulo": tit, "consulta": "sony dualsense ps5 white"},
    )
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_inversao_i_compativel_quando_consulta_original():
    tit = "Controle DualSense compatível PS5 original"
    item = _amz(
        titulo=tit,
        consulta="controle dualsense ps5 original",
        listing={"titulo": tit, "consulta": "controle dualsense ps5 original"},
    )
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_inversao_j_usado_quando_consulta_novo():
    tit = TITULO_TV + " usado"
    item = _amz(
        titulo=tit,
        consulta="smart tv 50",
        listing={"titulo": tit, "consulta": "smart tv 50"},
    )
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1
    assert jds._titulo_usado(tit) is True


def test_inversao_k_html_util_titulo_preco_asin_divergentes():
    item = _amz()
    html = _html_pdp_ok(
        "Geladeira Frost Free 400L",
        "R$ 9.999,00",
        ASIN_OUTRO,
    )
    assert jds._html_e_captcha_amazon(html) is False
    motivos = sap._motivos_zerados()
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=html, motivos=motivos)
    assert ok is None
    assert motivos.get("preco_nao_confere", 0) >= 1 or motivos.get("matcher_rejeitou", 0) >= 1 or motivos.get("variante_nao_bate", 0) >= 1


def test_inversao_l_identidade_e_asin_nao_seller():
    """Seller Magazine Luiza + PDP Amazon é sintético: Magalu cai na allowlist BR
    antes do confirmer. Identidade Amazon é ASIN, não o texto do seller.
    """
    item = _amz(
        vendedor_oferta="Amazon.com.br",
        loja="Amazon",
        listing={"vendedor": "Amazon.com.br"},
    )
    http_get = _http_amz_prod(ASIN_OUTRO, TITULO_TV, PRECO_TV)
    ok, motivos = _captcha(item, http_get=http_get, produto=False)
    assert ok is None
    assert motivos.get("id_nao_encontrado", 0) >= 1
    assert jds._asin_de_pdp_amazon(item["original_url"]) == ASIN_OK
    assert jds._asin_de_pdp_amazon(item["original_url"]) != ASIN_OUTRO


def test_inversao_fonte_nao_searchapi():
    item = _amz(fonte="serper")
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_prova_a_amazon_captcha_completo():
    item = _amz()
    assert jds._resposta_util_loja(PDP_AMZ, HTML_CAPTCHA_AMZ) is False
    ok, motivos = _captcha(item)
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert ok["original_url"] == PDP_AMZ
    assert ok["preco_num"] == PRECO_TV
    assert ok["titulo"] == TITULO_TV
    assert motivos.get("pagina_bloqueada", 0) == 0
    assert jds._url_anuncio_exato(ok["original_url"], "amazon")
    assert "google.com" not in ok["original_url"]


def test_prova_b_mercado_livre_antibot():
    item = _item_tv("mercado_livre")
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=HTML_ML_ANTIBOT)
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert "MLBU4780650807" in ok["original_url"]


def test_prova_c_amazon_html_util_tradicional():
    item = _amz()
    html = _html_pdp_ok(TITULO_TV, "R$ 1.849,00", ASIN_OK)
    assert jds._html_e_captcha_amazon(html) is False
    sap._reset_amazon_product_diag()
    called = []

    def http_get(params):
        called.append(params.get("engine"))
        return 500, {}, "{}"

    ok = jds._jds_confirmar_oferta_na_pagina(
        item, html=html, http_get=http_get, usar_cache=False,
    )
    assert ok is not None
    assert ok.get("confirmacao") != "searchapi_structured_offer"
    assert ok["confirmada_pagina"] is True
    assert ok["original_url"] == PDP_AMZ
    assert called == []
    assert sap._AMZ_PROD_DIAG["amazon_product_requests"] == 0


def test_duplicidade_uma_amazon_por_loja():
    a = _amz()
    b = copy.deepcopy(a)
    b["preco_num"] = 1900.0
    b["listing_source"]["preco_num"] = 1900.0
    b["listing_source"]["extracted_price"] = 1900.0
    b["original_url"] = PDP_OUTRO
    b["url"] = PDP_OUTRO
    b["listing_source"]["url"] = PDP_OUTRO

    def http_get(params):
        asin = str(params.get("asin") or "")
        preco = PRECO_TV if asin == ASIN_OK else 1900.0
        return 200, {
            "product": {
                "asin": asin,
                "title": TITULO_TV,
                "extracted_price": preco,
                "condition": "Novo",
            }
        }, "{}"

    grupo = jds._jds_confirmar_listings(
        [a, b],
        pais="BR",
        baixar=lambda u: HTML_CAPTCHA_AMZ,
        http_get=http_get,
        usar_cache=False,
    )
    amazons = [p for p in grupo if p.get("plataforma") == "amazon"]
    assert len(amazons) == 1


def test_url_final_nunca_google_nem_busca():
    for url in (GSHOP, "https://www.google.com/search?q=tv", "https://www.amazon.com.br/s?k=tv"):
        item = _amz(url=url, original_url=url)
        item["listing_source"]["url"] = url
        ok, _ = _captcha(item)
        assert ok is None


def test_captcha_nunca_e_pdp_util():
    assert jds._resposta_util_loja(PDP_AMZ, HTML_CAPTCHA_AMZ) is False
    assert jds._html_e_captcha_amazon(HTML_CAPTCHA_AMZ) is True
    assert jds._lojas_do_pais("BR") == ("amazon", "mercado_livre", "shopee")
