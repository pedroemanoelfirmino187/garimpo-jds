"""Confirmer: SearchApi ML + página anti-bot → estruturado. Sem html_vazio genérico."""
from __future__ import annotations

import garimpo_jds as jds
import jds_searchapi as sap

Q = "iPhone 15 128GB"
PDP_ML = (
    "https://www.mercadolivre.com.br/"
    "iphone-15-128gb-azul-oferta-top-garantia-original/up/MLBU4780650807"
)
TITULO_NOVO = "Iphone 15 128gb Azul Oferta Top Garantia Original (Novo com caixa aberta)"
AMZ = "https://www.amazon.com.br/dp/B0CQKLS4RP"
SHOPEE = "https://shopee.com.br/Apple-iPhone-15-128GB-i.1608031728.2309811123"
GSHOP = (
    "https://www.google.com/search?ibp=oshop&q=iPhone+15+128GB"
    "&prds=localAnnotatedOfferId:1,catalogid:1"
)


def _html_desafio_ml():
    return (
        '<!DOCTYPE html><html lang="pt-BR" '
        'data-assets-prefix="https://http2.mlstatic.com/frontend-assets/'
        'suspicious-traffic-frontend/"><head><meta charSet="utf-8"/></head>'
        "<body>account-verification para continuar, acesse sua conta"
        + ("x" * 280)
        + "</body></html>"
    )


def _item_ml(
    titulo=TITULO_NOVO,
    preco=4628.92,
    url=PDP_ML,
    fonte="searchapi",
    token="tok-ml-antibot",
    consulta=Q,
    usado_listing=None,
):
    tit = titulo
    item = {
        "titulo": tit,
        "preco_num": preco,
        "url": url,
        "original_url": url,
        "plataforma": "mercado_livre",
        "loja": "Mercado Livre",
        "fonte": fonte,
        "pais": "BR",
        "consulta": consulta,
        "foto": "https://http2.mlstatic.com/x.jpg",
        "imagem": "https://http2.mlstatic.com/x.jpg",
        "listing_source": {
            "titulo": tit if usado_listing is None else usado_listing,
            "preco_num": preco,
            "extracted_price": preco,
            "vendedor": "mercadolivre.com.br",
            "url": url,
            "imagem": "https://http2.mlstatic.com/x.jpg",
            "product_token": token,
            "product_id": "",
            "consulta": consulta,
        },
    }
    return item


def _item_amazon():
    return {
        "titulo": "Apple iPhone 15 128GB Preto",
        "preco_num": 4776.77,
        "url": AMZ,
        "original_url": AMZ,
        "plataforma": "amazon",
        "loja": "Amazon",
        "fonte": "searchapi",
        "pais": "BR",
        "consulta": Q,
        "foto": "https://m.media-amazon.com/x.jpg",
        "listing_source": {
            "titulo": "Apple iPhone 15 128GB Preto",
            "preco_num": 4776.77,
            "extracted_price": 4776.77,
            "vendedor": "Amazon.com.br",
            "url": AMZ,
            "product_token": "tok-amz",
            "product_id": "",
        },
    }


def _item_shopee():
    return {
        "titulo": "Apple iPhone 15 128GB",
        "preco_num": 3553.04,
        "url": SHOPEE,
        "original_url": SHOPEE,
        "plataforma": "shopee",
        "loja": "Shopee",
        "fonte": "searchapi",
        "pais": "BR",
        "consulta": Q,
        "foto": "https://cf.shopee.com.br/x.jpg",
        "listing_source": {
            "titulo": "Apple iPhone 15 128GB",
            "preco_num": 3553.04,
            "extracted_price": 3553.04,
            "vendedor": "Shopee",
            "url": SHOPEE,
            "product_token": "tok-shp",
            "product_id": "",
        },
    }


def test_a_ml_estruturado_pagina_antibot_confirma():
    item = _item_ml()
    assert jds._titulo_shopping_ok(Q, item["titulo"])
    assert jds._jds_anuncio_bate_consulta(Q, item["titulo"])
    assert not jds._titulo_usado(item["titulo"])
    motivos = sap._motivos_zerados()
    ok = jds._jds_confirmar_oferta_na_pagina(
        item, html=_html_desafio_ml(), motivos=motivos,
    )
    assert ok is not None
    assert ok["confirmada_pagina"] is True
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert ok["preco_num"] == 4628.92
    assert ok["original_url"] == PDP_ML
    assert "MLBU4780650807" in ok["original_url"]
    assert motivos.get("html_vazio", 0) == 0
    assert motivos.get("pagina_bloqueada", 0) == 0


def test_a_ml_antibot_via_download_direto_quando_html_anuncio_vazio(monkeypatch):
    item = _item_ml()
    monkeypatch.setattr(jds, "_jds_html_anuncio", lambda u: "")
    monkeypatch.setattr(jds, "_jds_baixar_html_direto", lambda u, timeout=12: _html_desafio_ml())
    ok = jds._jds_confirmar_oferta_na_pagina(item)
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"


def test_b_ml_html_vazio_generico_rejeita():
    item = _item_ml()
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(item, html="", motivos=motivos) is None
    assert motivos["html_vazio"] == 1
    motivos2 = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        item, baixar=lambda u: "", motivos=motivos2,
    ) is None
    assert motivos2["html_vazio"] == 1
    assert motivos2.get("pagina_bloqueada", 0) == 0


def test_c_ml_antibot_usado_rejeita():
    tit = "Apple Iphone 15 (128 Gb) - Preto (Usado)"
    item = _item_ml(titulo=tit)
    motivos = sap._motivos_zerados()
    assert jds._titulo_usado(tit)
    assert jds._jds_confirmar_oferta_na_pagina(
        item, html=_html_desafio_ml(), motivos=motivos,
    ) is None
    assert motivos.get("html_vazio", 0) == 0
    assert motivos["titulo_rejeitado"] >= 1


def test_d_ml_antibot_256gb_quando_consulta_128_rejeita():
    tit = "Apple iPhone 15 256GB Preto"
    item = _item_ml(titulo=tit, consulta=Q)
    motivos = sap._motivos_zerados()
    assert 256 in jds._jds_armazenamento_gb(tit)
    assert 128 in jds._jds_armazenamento_gb(Q)
    assert jds._jds_confirmar_oferta_na_pagina(
        item, html=_html_desafio_ml(), motivos=motivos,
    ) is None
    assert motivos.get("html_vazio", 0) == 0
    assert motivos["variante_nao_bate"] >= 1 or motivos["pagina_bloqueada"] >= 1


def test_e_amazon_html_vazio_permanece_rejeitado():
    item = _item_amazon()
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(item, html="", motivos=motivos) is None
    assert motivos["html_vazio"] == 1
    motivos2 = sap._motivos_zerados()
    html_amz_block = "<html>account-verification acesse sua conta</html>"
    assert jds._jds_confirmar_oferta_na_pagina(
        item, html=html_amz_block, motivos=motivos2,
    ) is None
    assert motivos2.get("html_vazio", 0) == 0
    assert motivos2["pagina_bloqueada"] >= 1


def test_f_shopee_html_vazio_permanece_rejeitado():
    item = _item_shopee()
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(item, html="", motivos=motivos) is None
    assert motivos["html_vazio"] == 1


def test_g_url_google_shopping_rejeita():
    item = _item_ml(url=GSHOP)
    item["original_url"] = GSHOP
    item["listing_source"]["url"] = GSHOP
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        item, html=_html_desafio_ml(), motivos=motivos,
    ) is None
    assert motivos["url_nao_exata"] >= 1


def test_h_pdp_ml_real_antibot_so_com_estrutura_completa():
    item = _item_ml()
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=_html_desafio_ml())
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    sem_token = _item_ml(token="")
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        sem_token, html=_html_desafio_ml(), motivos=motivos,
    ) is None
    assert motivos["pagina_bloqueada"] >= 1
    sem_fonte = _item_ml()
    sem_fonte["fonte"] = "serper"
    assert jds._jds_confirmar_oferta_na_pagina(
        sem_fonte, html=_html_desafio_ml(),
    ) is None


def test_html_util_ml_continua_confirmando_pela_pagina():
    item = _item_ml()
    html = (
        f"<html><head><meta property=\"og:title\" content=\"{TITULO_NOVO}\"></head>"
        f"<body>/up/MLBU4780650807 "
        f"<span class=\"andes-money-amount__fraction\">4628</span>"
        f"<span>R$ 4.628,92</span>"
        + ("x" * 80)
        + "</body></html>"
    )
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=html)
    assert ok is not None
    assert ok.get("confirmacao") != "searchapi_structured_offer" or ok["confirmada_pagina"] is True


def test_detecta_verificacao_ml_e_ignora_html_curto():
    assert jds._html_e_verificacao_mercadolivre(_html_desafio_ml()) is True
    assert jds._html_e_verificacao_mercadolivre("") is False
    assert jds._html_e_verificacao_mercadolivre("<html>erro</html>") is False
    assert jds._html_e_verificacao_mercadolivre(
        "<html>account-verification acesse sua conta</html>"
    ) is False
