"""CAPTCHA Amazon → SearchApi engine amazon_product. Sem API real. Sem CAPTCHA como PDP."""
from __future__ import annotations

import copy

import garimpo_jds as jds
import jds_searchapi as sap

from tests.test_amazon_captcha_audit import (
    ASIN_OK,
    ASIN_OUTRO,
    HTML_CAPTCHA_AMZ,
    PDP_AMZ,
    PRECO_TV,
    TITULO_TV,
    _amz,
    _captcha,
    _http_amz_prod,
)
from tests.test_lab_search_logic import _html_pdp_ok

IPHONE = "Apple iPhone 15 128GB Preto"
PDP_IPHONE = "https://www.amazon.com.br/dp/B0CQKLS4RP"


def _iphone(**kwargs):
    item = _amz(
        titulo=IPHONE,
        consulta="iphone 15 128gb",
        url=PDP_IPHONE,
        original_url=PDP_IPHONE,
        preco_num=1849.0,
        listing={
            "titulo": IPHONE,
            "url": PDP_IPHONE,
            "consulta": "iphone 15 128gb",
            "preco_num": 1849.0,
            "extracted_price": 1849.0,
        },
    )
    for k, v in kwargs.items():
        if k == "listing":
            item["listing_source"].update(v)
        else:
            item[k] = v
    return item


def test_asin_somente_pdp_amazon():
    assert jds._asin_de_pdp_amazon(PDP_AMZ) == ASIN_OK
    assert jds._asin_de_pdp_amazon(f"https://www.amazon.com.br/gp/product/{ASIN_OK}") == ASIN_OK
    assert jds._asin_de_pdp_amazon(
        "https://www.google.com/search?ibp=oshop&prds=catalogid:B0GSH89DG4"
    ) == ""
    assert jds._asin_de_pdp_amazon("https://www.amazon.com.br/s?k=tv") == ""
    assert jds._asin_de_pdp_amazon("https://www.amazon.com.br/") == ""


def test_a_captcha_asin_amazon_product_valido_aceita():
    sap._reset_amazon_product_diag()
    ok, motivos = _captcha(_amz())
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert ok["original_url"] == PDP_AMZ
    assert motivos.get("pagina_bloqueada", 0) == 0
    assert sap._AMZ_PROD_DIAG["amazon_product_confirmed"] >= 1
    assert sap._AMZ_PROD_DIAG["amazon_product_requests"] >= 1


def test_b_captcha_amazon_product_asin_diferente_rejeita():
    item = _amz()
    ok, motivos = _captcha(
        item,
        http_get=_http_amz_prod(ASIN_OUTRO, TITULO_TV, PRECO_TV),
        produto=False,
    )
    assert ok is None
    assert motivos.get("id_nao_encontrado", 0) >= 1


def test_c_preco_1849_vs_1849_aceita():
    item = _amz(preco_num=1849.0, listing={"preco_num": 1849.0, "extracted_price": 1849.0})
    ok, _motivos = _captcha(
        item,
        http_get=_http_amz_prod(ASIN_OK, TITULO_TV, 1849.0),
        produto=False,
    )
    assert ok is not None
    assert ok["preco_num"] == 1849.0


def test_d_preco_1849_vs_1999_rejeita():
    item = _amz(preco_num=1849.0, listing={"preco_num": 1849.0, "extracted_price": 1849.0})
    ok, motivos = _captcha(
        item,
        http_get=_http_amz_prod(ASIN_OK, TITULO_TV, 1999.0),
        produto=False,
    )
    assert ok is None
    assert motivos.get("preco_nao_confere", 0) >= 1


def test_e_iphone_15_128_amazon_product_128_aceita():
    item = _iphone()
    extra = {"specifications": [{"name": "Capacidade", "value": "128GB"}]}
    ok, _motivos = _captcha(
        item,
        http_get=_http_amz_prod("B0CQKLS4RP", IPHONE, 1849.0, extra=extra),
        produto=False,
    )
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"


def test_f_iphone_15_128_amazon_product_256_rejeita():
    item = _iphone()
    extra = {"specifications": [{"name": "Capacidade", "value": "256GB"}]}
    ok, motivos = _captcha(
        item,
        http_get=_http_amz_prod("B0CQKLS4RP", IPHONE, 1849.0, extra=extra),
        produto=False,
    )
    assert ok is None
    assert motivos.get("variante_nao_bate", 0) >= 1 or motivos.get("matcher_rejeitou", 0) >= 1


def test_g_ps5_amazon_product_slim_rejeita():
    tit = "Sony PlayStation 5"
    item = _amz(
        titulo=tit,
        consulta="playstation 5",
        listing={"titulo": tit, "consulta": "playstation 5"},
    )
    ok, motivos = _captcha(
        item,
        http_get=_http_amz_prod(ASIN_OK, "Sony PlayStation 5 Slim", PRECO_TV),
        produto=False,
    )
    assert ok is None
    assert motivos.get("variante_nao_bate", 0) >= 1 or motivos.get("matcher_rejeitou", 0) >= 1


def test_h_captcha_sem_asin_rejeita():
    item = _amz(
        url="https://www.amazon.com.br/s?k=tv",
        original_url="https://www.amazon.com.br/s?k=tv",
        listing={"url": "https://www.amazon.com.br/s?k=tv"},
    )
    ok, motivos = _captcha(item, produto=False)
    assert ok is None
    assert motivos.get("url_nao_exata", 0) >= 1 or motivos.get("id_nao_encontrado", 0) >= 1
    assert jds._asin_de_pdp_amazon(item["original_url"]) == ""


def test_i_amazon_product_indisponivel_rejeita_sem_inventar():
    item = _amz()
    ok, motivos = _captcha(
        item, http_get=_http_amz_prod(ASIN_OK, TITULO_TV, PRECO_TV, http=503), produto=False,
    )
    assert ok is None
    assert motivos.get("confirmer_rejeitou", 0) >= 1
    assert sap._AMZ_PROD_DIAG["amazon_product_rejection_reason"] == "confirmer_rejeitou"


def test_j_html_amazon_normal_nao_chama_amazon_product():
    item = _amz()
    html = _html_pdp_ok(TITULO_TV, "R$ 1.849,00", ASIN_OK)
    sap._reset_amazon_product_diag()
    called = []

    def http_get(params):
        called.append(copy.deepcopy(params))
        raise AssertionError("amazon_product nao deve ser chamado no HTML util")

    ok = jds._jds_confirmar_oferta_na_pagina(
        item, html=html, http_get=http_get, usar_cache=False,
    )
    assert ok is not None
    assert ok.get("confirmacao") != "searchapi_structured_offer"
    assert called == []
    assert sap._AMZ_PROD_DIAG["amazon_product_requests"] == 0


def test_k_seller_nao_inventa_asin():
    item = _amz(vendedor_oferta="Amazon.com.br - Seller", listing={"vendedor": "Amazon.com.br - Seller"})
    ok, motivos = _captcha(
        item,
        http_get=_http_amz_prod(ASIN_OUTRO, TITULO_TV, PRECO_TV),
        produto=False,
    )
    assert ok is None
    assert motivos.get("id_nao_encontrado", 0) >= 1
    assert jds._asin_de_pdp_amazon(item["original_url"]) == ASIN_OK


def test_l_captcha_nunca_e_html_valido():
    assert jds._html_e_captcha_amazon(HTML_CAPTCHA_AMZ) is True
    assert jds._resposta_util_loja(PDP_AMZ, HTML_CAPTCHA_AMZ) is False
    assert jds._jds_titulo_html_anuncio(HTML_CAPTCHA_AMZ) in ("", None)
    titulo = jds._jds_titulo_html_anuncio(HTML_CAPTCHA_AMZ) or ""
    assert "productTitle" not in HTML_CAPTCHA_AMZ
    assert TITULO_TV not in titulo


def test_diag_amazon_product_sem_api_key():
    sap._reset_amazon_product_diag()
    _captcha(_amz())
    diag = dict(sap._AMZ_PROD_DIAG)
    for chave in (
        "amazon_product_requests",
        "amazon_product_cache_hits",
        "amazon_product_confirmed",
        "amazon_product_rejected",
        "amazon_product_rejection_reason",
    ):
        assert chave in diag
    blob = str(diag)
    assert "api_key" not in blob.lower()
    assert "SEARCHAPI" not in blob
