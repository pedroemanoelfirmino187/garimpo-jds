"""Hard matcher: conflito de cor só se ambos informam cores disjuntas."""
from __future__ import annotations

import garimpo_jds as jds

QUERY = "sony dualsense ps5"
TITULO = "Sony DualSense Wireless Controller for PS5"
FOTO = "https://example.com/dual.jpg"


def _card(plat, titulo, url):
    return {
        "titulo": titulo,
        "plataforma": plat,
        "original_url": url,
        "url": url,
        "preco_num": 74.99,
        "foto": FOTO,
        "fonte": "searchapi",
        "pais": "US" if plat in {"amazon", "walmart", "ebay"} else "BR",
    }


def test_white_vs_white_mesmo_grupo():
    a = "Sony DualSense Wireless Controller for PS5 White"
    b = "Sony DualSense Wireless Controller for PS5 White"
    assert jds._jds_mesmo_produto(a, b, QUERY) is True
    grupo = jds._jds_maior_grupo_identico(QUERY, [
        _card("amazon", a, "https://www.amazon.com/dp/B08H99BPJN"),
        _card("ebay", b, "https://www.ebay.com/itm/123456789012"),
    ])
    assert {p["plataforma"] for p in grupo} == {"amazon", "ebay"}


def test_white_vs_black_grupos_diferentes():
    a = "Sony DualSense Wireless Controller for PS5 White"
    b = "Sony DualSense Wireless Controller for PS5 Black"
    assert jds._jds_mesmo_produto(a, b, QUERY) is False
    grupo = jds._jds_maior_grupo_identico(QUERY, [
        _card("amazon", a, "https://www.amazon.com/dp/B08H99BPJN"),
        _card("ebay", b, "https://www.ebay.com/itm/123456789012"),
    ])
    assert len(grupo) == 1


def test_sem_cor_vs_white_mesmo_grupo_query_sem_cor():
    assert jds._jds_mesmo_produto(TITULO, TITULO + " White", QUERY) is True
    assert jds._jds_mesmo_produto(TITULO + " White", TITULO, QUERY) is True


def test_query_white_rejeita_oferta_sem_white():
    q = "sony dualsense ps5 white"
    assert jds._jds_mesmo_produto(TITULO, TITULO, q) is False
    assert jds._jds_mesmo_produto(TITULO + " White", TITULO, q) is False
    assert jds._jds_mesmo_produto(TITULO + " White", TITULO + " White", q) is True


def test_1tb_vs_2tb_diferentes():
    a = "Samsung T7 Portable SSD 1TB"
    b = "Samsung T7 Portable SSD 2TB"
    assert jds._jds_mesmo_produto(a, b, "samsung t7 ssd") is False


def test_1tb_vs_omitido_preserva_diferentes():
    a = "Samsung T7 Portable SSD 1TB"
    b = "Samsung T7 Portable SSD"
    assert jds._jds_mesmo_produto(a, b, "samsung t7 ssd") is False


def test_dualsense_vs_dualsense_edge_diferentes():
    edge = "Sony DualSense Edge Wireless Controller for PS5"
    assert jds._jds_mesmo_produto(TITULO, edge, QUERY) is False


def test_palavras_comerciais_mesmo_produto():
    b = "Sony DualSense Official Wireless Controller for PS5"
    assert jds._jds_mesmo_produto(TITULO, b, QUERY) is True


def test_amazon_walmart_ebay_mesmo_grupo_cor_omitida():
    xs = [
        _card("amazon", TITULO, "https://www.amazon.com/dp/B08H99BPJN"),
        _card(
            "walmart",
            TITULO,
            "https://www.walmart.com/ip/Sony-DualSense/188140087",
        ),
        _card("ebay", TITULO + " White", "https://www.ebay.com/itm/123456789012"),
    ]
    grupo = jds._jds_maior_grupo_identico(QUERY, xs)
    comparar = jds._jds_comparar_mesmo_produto(QUERY, xs, pais="US")
    assert {p["plataforma"] for p in grupo} == {"amazon", "walmart", "ebay"}
    assert {p["plataforma"] for p in comparar} == {"amazon", "walmart", "ebay"}


def test_regressao_amazon_ml_shopee_dualsense_br():
    consulta = "controle dualsense ps5"
    amazon = "Controle DualSense Sony PS5"
    ml = "Controle Sony DualSense PS5 Branco"
    shopee = "Controle DualSense Wireless PS5 Sony"
    assert jds._jds_mesmo_produto(amazon, ml, consulta) is True
    assert jds._jds_mesmo_produto(amazon, shopee, consulta) is True
    assert jds._jds_mesmo_produto(ml, shopee, consulta) is True
    preto = "Controle DualSense Sony PS5 Preto"
    assert jds._jds_mesmo_produto(ml, preto, consulta) is False
    xs = [
        _card("amazon", amazon, "https://www.amazon.com.br/dp/B08H99BPJN"),
        _card("mercado_livre", ml, "https://www.mercadolivre.com.br/p/MLB123"),
        _card("shopee", shopee, "https://shopee.com.br/controle-i.1.2"),
    ]
    grupo = jds._jds_maior_grupo_identico(consulta, xs)
    assert {p["plataforma"] for p in grupo} == {"amazon", "mercado_livre", "shopee"}
