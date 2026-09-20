"""User Product MLBU e allowlist BR. Sem SearchApi real."""
from __future__ import annotations

import garimpo_jds as jds
import jds_searchapi as sap

QUERY = "iPhone 15 128GB"
TITULO_NOVO = "Apple iPhone 15 128GB Preto"
MLB = "https://produto.mercadolivre.com.br/MLB-12345678"
PDP_P = "https://www.mercadolivre.com.br/apple-iphone-15-128-gb-preto/p/MLB12345678"
UP = (
    "https://www.mercadolivre.com.br/apple-iphone-15-128-gb-preto"
    "-12-meses-de-gar-com-nf/up/MLBU3827311044"
)
AMZ = "https://www.amazon.com.br/dp/B0CHX3QB9Y"
SHOPEE = "https://shopee.com.br/Apple-iPhone-15-128GB-i.1608031728.2309811123"


def _ofe(link, merchant, title=TITULO_NOVO):
    return {
        "title": title,
        "link": link,
        "extracted_price": 3599.0,
        "price": "R$ 3.599,00",
        "merchant": {"name": merchant},
        "thumbnail": "https://http2.mlstatic.com/x.jpg",
    }


def test_mlb_tradicional_aceita():
    assert jds._id_mlb(MLB) == "12345678"
    assert jds._id_mlbu(MLB) == ""
    assert jds._url_anuncio_exato(MLB, "mercado_livre") is True


def test_pdp_p_aceita():
    assert jds._url_anuncio_exato(PDP_P, "mercado_livre") is True
    assert jds._id_mlb(PDP_P) == "12345678"


def test_up_mlbu_aceita_user_product():
    assert jds._id_mlbu(UP) == "MLBU3827311044"
    assert jds._id_mlb(UP) == ""
    assert jds._url_anuncio_exato(UP, "mercado_livre") is True
    motivos = sap._motivos_zerados()
    item = sap.offer_para_item(QUERY, _ofe(UP, "mercadolivre.com.br"), "BR", motivos=motivos)
    assert item is not None
    assert item["plataforma"] == "mercado_livre"
    assert motivos["url_nao_exata"] == 0
    assert motivos["loja_fora"] == 0


def test_busca_ml_rejeita():
    busca = "https://lista.mercadolivre.com.br/iphone-15-128gb"
    assert jds._url_e_busca_loja(busca) is True
    assert jds._url_anuncio_exato(busca, "mercado_livre") is False
    assert jds._id_mlbu(busca) == ""


def test_categoria_ml_rejeita():
    cat = "https://www.mercadolivre.com.br/c/celulares-e-telefones"
    assert jds._url_anuncio_exato(cat, "mercado_livre") is False
    assert jds._id_mlbu(cat) == ""


def test_dominio_falso_com_mlbu_rejeita():
    fake = "https://trocafy.com.br/iphone/up/MLBU3827311044"
    assert jds._id_mlbu(fake) == ""
    assert jds._url_anuncio_exato(fake, "mercado_livre") is False
    qs = "https://www.mercadolivre.com.br/busca?q=MLBU3827311044"
    assert jds._id_mlbu(qs) == ""
    texto = "https://www.mercadolivre.com.br/iphone-15?ref=MLBU3827311044"
    assert jds._id_mlbu(texto) == ""


def test_trocafy_continua_loja_fora():
    motivos = sap._motivos_zerados()
    link = "https://www.trocafy.com.br/iphone-15-128gb-preto-p1973"
    assert sap.offer_para_item(QUERY, _ofe(link, "Trocafy"), "BR", motivos=motivos) is None
    assert motivos["loja_fora"] == 1


def test_magalu_continua_loja_fora():
    motivos = sap._motivos_zerados()
    link = "https://www.magazineluiza.com.br/usado-iphone-15-128gb/p/ghaeb9fceb/te/i15p/"
    assert sap.offer_para_item(QUERY, _ofe(link, "Magalu"), "BR", motivos=motivos) is None
    assert motivos["loja_fora"] == 1


def test_carrefour_continua_loja_fora():
    motivos = sap._motivos_zerados()
    link = "https://www.carrefour.com.br/iphone-15-128gb-pink-vitrine-apple-mp958227485/p"
    assert sap.offer_para_item(QUERY, _ofe(link, "Carrefour"), "BR", motivos=motivos) is None
    assert motivos["loja_fora"] == 1


def test_amazon_continua_permitida():
    assert "amazon" in jds._lojas_do_pais("BR")
    assert jds._url_anuncio_exato(AMZ, "amazon") is True


def test_shopee_continua_permitida():
    assert "shopee" in jds._lojas_do_pais("BR")
    assert jds._url_anuncio_exato(SHOPEE, "shopee") is True


def test_allowlist_br_inalterada():
    assert jds._lojas_do_pais("BR") == ("amazon", "mercado_livre", "shopee")


def test_confirmer_exige_mlbu_no_html():
    url = UP
    html_ok = "<html><body>/up/MLBU3827311044 Apple iPhone 15</body></html>"
    html_vazio = "<html><body>ofertas do dia</body></html>"
    assert jds._jds_id_anuncio_na_pagina(url, "mercado_livre", html_ok) is True
    assert jds._jds_id_anuncio_na_pagina(url, "mercado_livre", html_vazio) is False
