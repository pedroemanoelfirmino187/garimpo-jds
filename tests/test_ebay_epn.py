"""eBay/EPN sem rede. Matcher V4 e lojas BR não são relaxados."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import garimpo_jds as jds
import jds_searchapi as sap

FIX = Path(__file__).resolve().parent / "fixtures" / "searchapi"
ITEM_ID = "123456789012"
PDP = f"https://www.ebay.com/itm/{ITEM_ID}"
FOTO = "https://i.ebayimg.com/images/g/dualsense/s-l1600.jpg"
TITULO = "Sony DualSense Wireless Controller for PS5"
QUERY = "sony dualsense ps5"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _html_ebay(titulo=TITULO, preco="$74.99", item_id=ITEM_ID):
    extra = "x" * 80
    return (
        f"<html><head><meta property=\"og:title\" content=\"{titulo}\"></head>"
        f"<body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco}</span> item {item_id} {extra}</body></html>"
    )


def _offer(**kwargs):
    ofe = {
        "title": TITULO,
        "price": "$74.99",
        "extracted_price": 74.99,
        "link": PDP,
        "merchant": {"name": "eBay"},
        "thumbnail": FOTO,
    }
    ofe.update(kwargs)
    return ofe


def _item_ok():
    item = sap.offer_para_item(QUERY, _offer(), "US")
    assert item is not None
    return item


def test_a_ebay_itm_valido_aceita():
    item = _item_ok()
    assert item["original_url"] == PDP
    assert item["preco_num"] == pytest.approx(74.99)
    assert item["foto"] == FOTO
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    assert len(ok) == 1
    assert ok[0]["original_url"] == PDP
    assert ITEM_ID in (ok[0].get("affiliate_url") or "")


def test_b_preco_divergente_rejeita():
    item = _item_ok()
    html = _html_ebay(preco="$12.00")
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None


def test_c_titulo_divergente_rejeita():
    item = _item_ok()
    html = _html_ebay(titulo="Apple iPhone 15 256GB Black")
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None


def test_d_imagem_divergente_rejeita():
    item = _item_ok()
    item["foto"] = "https://i.ebayimg.com/images/g/outra/s-l1600.jpg"
    item["imagem"] = item["foto"]
    html = _html_ebay()
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None
    assert sap.validar_integridade_listing(item) is False


def test_e_condicao_divergente_rejeita():
    item = _item_ok()
    html = _html_ebay(titulo=TITULO + " refurbished open box")
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None


def test_f_sch_rejeita():
    motivos = sap._motivos_zerados()
    ofe = _offer(link="https://www.ebay.com/sch/i.html?_nkw=dualsense")
    assert sap.offer_para_item(QUERY, ofe, "US", motivos=motivos) is None
    assert motivos["url_busca"] + motivos["url_nao_exata"] >= 1
    assert jds._url_anuncio_exato(ofe["link"], "ebay") is False
    card = {"plataforma": "ebay", "url": ofe["link"], "titulo": TITULO, "pais": "US"}
    href = jds._link_compra_do_card(card)
    assert "/sch/" not in (href or "")
    assert not href or jds._id_ebay(href)


def test_g_google_shopping_rejeita():
    motivos = sap._motivos_zerados()
    ofe = _offer(link="https://www.google.com/search?ibp=oshop&q=dualsense")
    assert sap.offer_para_item(QUERY, ofe, "US", motivos=motivos) is None
    assert motivos["url_google"] == 1


def test_h_affiliate_item_id_diferente_rejeita():
    item = _item_ok()
    html = _html_ebay()
    item["url"] = jds._aplicar_afiliado_ebay("https://www.ebay.com/itm/999999999999")
    item["affiliate_url"] = item["url"]
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    assert ok == []


def test_i_original_url_sem_tracking():
    item = _item_ok()
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    orig = ok[0]["original_url"]
    assert orig == PDP
    assert "campid=" not in orig
    assert "rover.ebay" not in orig
    assert "customid=" not in orig


def test_j_affiliate_url_recebe_epn():
    item = _item_ok()
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    aff = ok[0]["affiliate_url"]
    assert "rover.ebay.com" in aff
    assert f"campid={jds.ID_EBAY_CAMPAIGN}" in aff
    assert f"customid={jds.ID_EBAY_CUSTOM}" in aff
    assert "ebay.us/GAuuZC" not in aff
    ser = jds.serializar_oferta_app(ok[0], pais="US")
    assert ser["affiliate_url"] == aff or jds._id_ebay(ser["affiliate_url"]) == ITEM_ID
    assert ser["link_afiliado"]
    assert jds._link_ver_oferta(ok[0])
    assert jds._id_ebay(jds._link_ver_oferta(ok[0])) == ITEM_ID


def test_k_mesmo_item_id_original_e_afiliado():
    item = _item_ok()
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    assert jds._ebay_afiliado_mesmo_item(ok[0]["original_url"], ok[0]["affiliate_url"])
    assert jds._id_ebay(ok[0]["original_url"]) == jds._id_ebay(ok[0]["affiliate_url"]) == ITEM_ID


def test_l_br_nao_retorna_ebay():
    motivos = sap._motivos_zerados()
    assert sap.offer_para_item(QUERY, _offer(), "BR", motivos=motivos) is None
    assert motivos["loja_fora"] == 1
    assert "ebay" not in jds._lojas_do_pais("BR")


def test_m_us_pode_retornar_ebay():
    assert "ebay" in jds._lojas_do_pais("US")
    shopping = _load("shopping_us_dualsense.json")
    offers = _load("offers_us_ebay.json")

    def http_get(params):
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("product_token") == "token-us-ebay":
            return 200, offers, "{}"
        return 200, {"offers": []}, "{}"

    def baixar(url):
        assert "rover.ebay" not in url
        assert "/sch/" not in url
        if "/itm/" in url:
            return _html_ebay()
        return ""

    result, status = sap.buscar_ofertas_searchapi(
        QUERY, pais="US", usar_cache=False, http_get=http_get, baixar=baixar, confirmar=True,
    )
    ebay = [p for p in result if p.get("plataforma") == "ebay"]
    assert status == "SEARCHAPI_SUCCESS"
    assert ebay
    assert ebay[0]["original_url"] == PDP
    assert jds._id_ebay(ebay[0]["affiliate_url"]) == ITEM_ID


def test_n_usado_seminovo_segue_regra_atual():
    ofe = _offer(title="Sony DualSense PS5 seminovo refurbished")
    assert sap.offer_para_item(QUERY, ofe, "US") is None
    assert jds._titulo_usado(ofe["title"]) is True
    assert jds._titulo_shopping_ok(QUERY, ofe["title"]) is False


def test_p_titulo_imagem_preco_url_mesma_oferta():
    item = _item_ok()
    assert sap.validar_integridade_listing(item)
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)[0]
    assert ok["titulo"] == TITULO
    assert ok["foto"] == FOTO
    assert ok["preco_num"] == pytest.approx(74.99)
    assert ok["original_url"] == PDP
    assert sap.validar_integridade_listing({
        **ok,
        "original_url": PDP,
        "listing_source": item["listing_source"],
        "titulo": TITULO,
        "preco_num": 74.99,
        "foto": FOTO,
    })


def test_confirmer_baixa_pdp_nao_rover():
    item = _item_ok()
    visto = []

    def baixar(url):
        visto.append(url)
        return _html_ebay()

    jds._jds_confirmar_listings([item], pais="US", baixar=baixar)
    assert visto == [PDP]


def test_montar_item_ebay_nao_vira_busca():
    item = jds._montar_item_oferta(
        TITULO, 74.99, "https://www.ebay.com/sch/i.html?_nkw=dualsense",
        FOTO, "ebay", pais="US",
    )
    assert "/sch/" not in (item.get("url") or "")
    assert not item.get("url") or jds._id_ebay(item["url"])


def test_montar_preserva_itm_ate_confirmer():
    item = jds._montar_item_oferta(TITULO, 74.99, PDP, FOTO, "ebay", pais="US")
    assert item["url"] == PDP
    assert "rover.ebay" not in (item["url"] or "")
    assert jds._url_anuncio_exato(item["url"], "ebay")


def test_chave_anuncio_exato_ebay():
    assert jds._jds_chave_anuncio_exato(PDP, "ebay") == f"ebay:{ITEM_ID}"
    rover = jds._aplicar_afiliado_ebay(PDP)
    assert jds._jds_chave_anuncio_exato(rover, "ebay") == ""
    assert jds._jds_chave_anuncio_exato("https://www.ebay.com/sch/i.html?_nkw=x", "ebay") == ""


def test_rover_sozinho_nao_e_pdp():
    rover = jds._aplicar_afiliado_ebay(PDP)
    assert jds._url_anuncio_exato(rover, "ebay") is False
    motivos = sap._motivos_zerados()
    assert sap.offer_para_item(QUERY, _offer(link=rover), "US", motivos=motivos) is None
    assert motivos["url_nao_exata"] >= 1


def test_ebay_us_encurtador_rejeitado():
    motivos = sap._motivos_zerados()
    ofe = _offer(link="https://ebay.us/GAuuZC")
    assert sap.offer_para_item(QUERY, ofe, "US", motivos=motivos) is None
    assert motivos["url_nao_exata"] + motivos["url_google"] >= 1
    assert jds._id_ebay(ofe["link"]) == ""


def test_serper_item_ebay_mantem_itm():
    bruto = {
        "title": TITULO,
        "source": "eBay",
        "price": "$74.99",
        "extracted_price": 74.99,
        "link": PDP,
        "imageUrl": FOTO,
    }
    item = jds._jds_item_serper(QUERY, bruto, pais="US")
    assert item is not None
    assert item["original_url"] == PDP
    assert item["url"] == PDP
    assert "rover.ebay" not in item["url"]
    html = _html_ebay()
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    assert len(ok) == 1
    assert ok[0]["original_url"] == PDP
    aff = ok[0]["affiliate_url"]
    assert f"campid={jds.ID_EBAY_CAMPAIGN}" in aff
    assert f"customid={jds.ID_EBAY_CUSTOM}" in aff
    assert jds._id_ebay(aff) == ITEM_ID


def test_searchapi_reserva_candidato_ebay_no_limite():
    def card(pos, token, seller):
        return {
            "position": pos,
            "product_token": token,
            "title": TITULO,
            "seller": seller,
            "extracted_price": 74.99,
            "link": "https://www.google.com/search?ibp=oshop",
        }

    shopping = [
        card(1, "tok-amazon", "Amazon.com"),
        card(2, "tok-walmart", "Walmart"),
        card(3, "tok-target", "Target"),
        card(4, "tok-bestbuy", "Best Buy"),
        card(5, "tok-ebay", "eBay"),
    ]
    escolhidos = sap.selecionar_candidatos_token(QUERY, shopping, pais="US", limite=3)
    assert len(escolhidos) == 3
    assert any(c.get("plataforma") == "ebay" for c in escolhidos)
    assert {c["product_token"] for c in escolhidos if c.get("plataforma") == "ebay"} == {"tok-ebay"}
    br = sap.selecionar_candidatos_token(QUERY, shopping, pais="BR", limite=3)
    assert all(c.get("plataforma") != "ebay" for c in br)


def test_host_desconhecido_nao_vira_mercado_livre():
    assert jds._detectar_plataforma("https://www.exemplo.com/produto/1") == ""
    assert jds._detectar_plataforma("https://www.ebay.com/itm/123456789012") == "ebay"
    assert jds._detectar_plataforma("https://www.mercadolivre.com.br/p/MLB1") == "mercado_livre"


def test_health_tem_ebay():
    from fastapi.testclient import TestClient
    from api.main import app

    data = TestClient(app).get("/health").json()
    assert data["afiliados"]["ebay"] == jds.ID_EBAY_CAMPAIGN


def test_garimpar_assinatura_inalterada():
    from fastapi.testclient import TestClient
    from api.main import app

    fake = [_item_ok()]
    with patch("api.main._buscar_serper_pais", return_value=fake):
        resp = TestClient(app).get("/garimpar", params={"q": QUERY, "pais": "US"})
    assert resp.status_code == 200
    corpo = resp.json()
    assert "ofertas" in corpo
    assert "pais" in corpo
    assert "total" in corpo
