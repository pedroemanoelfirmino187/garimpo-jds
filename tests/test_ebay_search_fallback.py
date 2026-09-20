"""Fallback US ebay_search: matcher existente, PDP /itm/, sem segundo motor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import garimpo_jds as jds
import jds_searchapi as sap

FIX = Path(__file__).resolve().parent / "fixtures" / "searchapi"
ITEM_ID = "226994069950"
PDP = f"https://www.ebay.com/itm/{ITEM_ID}"
FOTO = "https://i.ebayimg.com/images/g/dualsense/s-l1600.jpg"
TITULO = "Sony DualSense Wireless Controller for PS5"
QUERY_A = "Sony DualSense PS5 controller"
QUERY_B = "Sony DualSense White PS5 controller"
QUERY_C = "Sony DualSense Edge PS5 controller"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _html(titulo, preco, item_id):
    extra = "x" * 80
    return (
        f"<html><head><meta property=\"og:title\" content=\"{titulo}\"></head>"
        f"<body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco}</span> item {item_id} {extra}</body></html>"
    )


def _org(**kwargs):
    row = {
        "title": TITULO,
        "price": "$74.99",
        "extracted_price": 74.99,
        "link": PDP,
        "item_id": ITEM_ID,
        "thumbnail": FOTO,
        "seller": "eBay",
    }
    row.update(kwargs)
    return row


def _product_payload(item_id=ITEM_ID, title=None, price=74.99, **kwargs):
    item = {
        "item_id": item_id,
        "title": title or TITULO,
        "price": f"${price}",
        "extracted_price": price,
        "link": f"https://www.ebay.com/itm/{item_id}",
        "condition": "New",
        "main_image": FOTO,
    }
    item.update(kwargs)
    return {"item": item}


def _http_ebay(organic, products=None, visto=None):
    products = products or {}
    visto = visto if visto is not None else []

    def http_get(params):
        visto.append(params.get("engine"))
        engine = params.get("engine")
        if engine == "ebay_search":
            return 200, {"organic_results": organic}, "{}"
        if engine == "ebay_product":
            iid = str(params.get("item_id") or "")
            payload = products.get(iid)
            if payload is None:
                return 200, {}, "{}"
            return 200, payload, "{}"
        return 200, {}, "{}"

    return http_get, visto


def _baixar_proibido_ebay(url):
    if "ebay.com/itm" in (url or "").lower():
        raise AssertionError("ebay_search nao confirma via HTML")
    return ""


def _item(query, **org_kw):
    ofe = sap.organic_ebay_para_offer(_org(**org_kw))
    if ofe is None:
        return None
    return sap.offer_para_item(query, ofe, "US")


def test_a_dualsense_qualquer_cor_ok_edge_rejeitado():
    assert _item(QUERY_A, title=TITULO + " White") is not None
    assert _item(QUERY_A, title=TITULO + " Black") is not None
    assert _item(QUERY_A, title="Sony DualSense Wireless Controller for PS5 Purple") is not None
    assert _item(QUERY_A, title="Sony DualSense Edge Wireless Controller for PS5") is None
    motivos = sap._motivos_zerados()
    ofe = sap.organic_ebay_para_offer(_org(title="Sony DualSense Edge Wireless Controller for PS5"))
    assert sap.offer_para_item(QUERY_A, ofe, "US", motivos=motivos) is None
    assert motivos["matcher_rejeitou"] >= 1


def test_b_consulta_white_rejeita_outras_cores_e_edge():
    assert _item(QUERY_B, title=TITULO + " White") is not None
    assert _item(QUERY_B, title=TITULO + " Black") is None
    assert _item(QUERY_B, title=TITULO + " Purple") is None
    assert _item(QUERY_B, title="Sony DualSense Wireless Controller Sterling Silver PS5") is None
    assert _item(QUERY_B, title="Sony DualSense Edge Wireless Controller White PS5") is None
    assert _item(QUERY_B, title=TITULO) is None


def test_c_consulta_edge_aceita_edge_rejeita_normal():
    assert _item(QUERY_C, title="Sony DualSense Edge Wireless Controller for PS5") is not None
    assert _item(QUERY_C, title=TITULO) is None
    assert _item(QUERY_C, title=TITULO + " White") is None


def test_d_item_id_exato_nao_substitui_e_epn_mesmo_id():
    ofe = sap.organic_ebay_para_offer(_org())
    assert ofe["link"] == PDP
    item = sap.offer_para_item(QUERY_A, ofe, "US")
    assert item is not None
    assert jds._id_ebay(item["original_url"]) == ITEM_ID
    html = _html(TITULO, "$74.99", ITEM_ID)
    ok = jds._jds_confirmar_listings([item], pais="US", baixar=lambda u: html)
    assert len(ok) == 1
    assert jds._id_ebay(ok[0]["original_url"]) == ITEM_ID
    assert jds._id_ebay(ok[0]["affiliate_url"]) == ITEM_ID
    assert jds._ebay_afiliado_mesmo_item(ok[0]["original_url"], ok[0]["affiliate_url"])
    outro = sap.organic_ebay_para_offer(_org(
        link="https://www.ebay.com/itm/999999999999",
        item_id=ITEM_ID,
    ))
    assert outro is None


def test_e_url_nao_itm_rejeita():
    assert sap.organic_ebay_para_offer(_org(
        link="https://www.ebay.com/sch/i.html?_nkw=dualsense",
        item_id=ITEM_ID,
    )) is None
    assert sap.organic_ebay_para_offer(_org(
        link="https://www.google.com/search?ibp=oshop",
        item_id=ITEM_ID,
    )) is None
    rover = jds._aplicar_afiliado_ebay(PDP)
    assert sap.organic_ebay_para_offer(_org(link=rover, item_id=ITEM_ID)) is None


def test_f_sem_item_id_rejeita():
    assert sap.organic_ebay_para_offer(_org(link="https://www.ebay.com/", item_id="")) is None
    assert sap.organic_ebay_para_offer(_org(link="https://www.ebay.com/itm/", item_id="")) is None
    assert sap.organic_ebay_para_offer(_org(item_id="")) is None
    ofe = sap.organic_ebay_para_offer(_org())
    item = sap.offer_para_item(QUERY_A, ofe, "US")
    item.pop("ebay_item_id", None)
    ok, nreq = sap.confirmar_item_ebay_product(QUERY_A, item, pais="US", usar_cache=False, http_get=lambda p: (200, {"item": {"item_id": ITEM_ID, "title": TITULO, "extracted_price": 74.99}}, "{}"))
    assert ok is None
    assert nreq == 0


def test_g_us_sem_ebay_shopping_chama_ebay_search():
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    shopping["shopping_results"] = [
        x for x in shopping["shopping_results"] if x.get("seller") != "eBay"
    ]
    organic = [
        _org(
            title="Sony DualSense Edge Wireless Controller for PS5",
            link="https://www.ebay.com/itm/235990271882",
            item_id="235990271882",
            extracted_price=159.99,
            price="$159.99",
        ),
        _org(title="Sony DualSense Wireless Controller NEW - Sterling Silver - Playstation 5"),
    ]

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("engine") == "google_product_offers":
            return 200, {"offers": []}, "{}"
        if params.get("engine") == "ebay_search":
            assert params.get("ebay_domain") == "ebay.com"
            assert params.get("country") == "us"
            return 200, {"organic_results": organic}, "{}"
        if params.get("engine") == "ebay_product":
            assert params.get("item_id") == ITEM_ID
            return 200, _product_payload(
                title="Sony DualSense Wireless Controller NEW - Sterling Silver - Playstation 5",
            ), "{}"
        return 200, {}, "{}"

    def baixar(url):
        if "ebay.com/itm" in (url or "").lower():
            raise AssertionError("ebay_search nao confirma via HTML")
        return ""

    result, status = sap.buscar_ofertas_searchapi(
        QUERY_A, pais="US", usar_cache=False, http_get=http_get, baixar=baixar, confirmar=True,
    )
    assert "ebay_search" in visto
    assert "ebay_product" in visto
    assert visto.count("ebay_product") == 1
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("ebay_search_requests") == 1
    assert diag.get("ebay_search_skip") == ""
    assert diag.get("ebay_product_requests") == 1
    ebay = [p for p in result if p.get("plataforma") == "ebay"]
    assert status == "SEARCHAPI_SUCCESS"
    assert ebay
    assert jds._id_ebay(ebay[0]["original_url"]) == ITEM_ID
    assert "edge" not in jds._sem_acento(ebay[0]["titulo"])
    assert jds._id_ebay(ebay[0].get("affiliate_url") or "") == ITEM_ID


def test_h_us_com_ebay_confirmado_nao_chama_ebay_search():
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    offers = _load("offers_us_ebay.json")

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("product_token") == "token-us-ebay":
            return 200, offers, "{}"
        if params.get("engine") == "ebay_search":
            raise AssertionError("ebay_search nao deveria ser chamado")
        if params.get("engine") == "ebay_product":
            raise AssertionError("ebay_product nao deveria ser chamado")
        return 200, {"offers": []}, "{}"

    def baixar(url):
        if "/itm/" in (url or ""):
            return _html(TITULO, "$74.99", "123456789012")
        return ""

    result, status = sap.buscar_ofertas_searchapi(
        "sony dualsense ps5",
        pais="US",
        usar_cache=False,
        http_get=http_get,
        baixar=baixar,
        confirmar=True,
    )
    assert "ebay_search" not in visto
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("ebay_search_skip") == "ebay_ja_confirmado"
    assert diag.get("ebay_search_requests") == 0
    assert status == "SEARCHAPI_SUCCESS"
    assert any(p.get("plataforma") == "ebay" for p in result)


def test_i_brasil_nao_chama_ebay_search():
    visto = []
    shopping = _load("shopping_br_controle_ps5.json")
    mapa = {
        "token-ps5-amazon": _load("offers_br_amazon.json"),
        "token-ps5-ml": _load("offers_br_ml.json"),
        "token-ps5-shopee": _load("offers_br_shopee.json"),
    }

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "ebay_search":
            raise AssertionError("Brasil nao chama ebay_search")
        if params.get("engine") == "ebay_product":
            raise AssertionError("Brasil nao chama ebay_product")
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        tok = params.get("product_token")
        return 200, mapa.get(tok, {"offers": []}), "{}"

    def baixar(url):
        u = (url or "").lower()
        extra = "x" * 80
        if "amazon.com.br" in u:
            return (
                "<html><body><span id=\"productTitle\">Controle sem fio DualSense Sony PS5 Branco</span>"
                f"<span class=\"a-offscreen\">R$ 404,27</span>B0CQKLS4RP{extra}</body></html>"
            )
        if "mercadolivre" in u:
            return (
                "<html><body><span id=\"productTitle\">Controle DualSense Sony PlayStation 5</span>"
                f"<span class=\"a-offscreen\">R$ 419,00</span>MLB-1234567890 /p/ MLB{extra}</body></html>"
            )
        if "shopee" in u:
            return (
                "<html><body><span id=\"productTitle\">Controle DualSense Sony PS5</span>"
                f"<span class=\"a-offscreen\">R$ 389,90</span>-i.1608031728.2309811123{extra}</body></html>"
            )
        return ""

    result, status = sap.buscar_ofertas_searchapi(
        "controle ps5",
        pais="BR",
        usar_cache=False,
        http_get=http_get,
        baixar=baixar,
        confirmar=True,
    )
    assert "ebay_search" not in visto
    assert "ebay_product" not in visto
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("ebay_search_skip") == "nao_us"
    assert diag.get("ebay_search_requests") == 0
    assert diag.get("ebay_product_requests") == 0
    plats = {p.get("plataforma") for p in result}
    assert status == "SEARCHAPI_SUCCESS"
    assert "amazon" in plats
    assert "mercado_livre" in plats
    assert "ebay" not in plats


def test_j_ebay_product_mesmo_id_confirma_epn():
    http_get, visto = _http_ebay([_org()], {ITEM_ID: _product_payload()})
    ok, _req, norg, nprod = sap.completar_ebay_via_search(
        QUERY_A,
        pais="US",
        usar_cache=False,
        http_get=http_get,
        baixar=_baixar_proibido_ebay,
        confirmar=True,
    )
    assert norg == 1
    assert nprod == 1
    assert "ebay_product" in visto
    assert len(ok) == 1
    assert ok[0]["original_url"] == PDP
    assert jds._id_ebay(ok[0]["original_url"]) == ITEM_ID
    assert jds._id_ebay(ok[0]["affiliate_url"]) == ITEM_ID
    assert jds._ebay_afiliado_mesmo_item(ok[0]["original_url"], ok[0]["affiliate_url"])
    assert "/itm/" + ITEM_ID in ok[0]["original_url"]
    assert ok[0].get("confirmacao") == "ebay_product"


def test_k_ebay_product_id_diferente_rejeita():
    http_get, visto = _http_ebay(
        [_org()],
        {ITEM_ID: _product_payload(item_id="999999999999")},
    )
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_A,
        pais="US",
        usar_cache=False,
        http_get=http_get,
        baixar=_baixar_proibido_ebay,
        confirmar=True,
    )
    assert nprod == 1
    assert "ebay_product" in visto
    assert ok == []


def test_l_ebay_product_sem_resultado_rejeita():
    http_get, visto = _http_ebay([_org()], {ITEM_ID: {}})
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_A,
        pais="US",
        usar_cache=False,
        http_get=http_get,
        baixar=_baixar_proibido_ebay,
        confirmar=True,
    )
    assert nprod == 1
    assert "ebay_product" in visto
    assert ok == []


def test_m_dualsense_normal_confirma():
    http_get, _visto = _http_ebay(
        [_org(title="Sony DualSense Wireless Controller for PS5 White")],
        {ITEM_ID: _product_payload(title="Sony DualSense Wireless Controller for PS5 White")},
    )
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_A, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_proibido_ebay, confirmar=True,
    )
    assert nprod == 1
    assert len(ok) == 1
    assert "edge" not in jds._sem_acento(ok[0]["titulo"])


def test_n_edge_query_normal_rejeita_sem_ebay_product():
    organic = [
        _org(
            title="Sony DualSense Edge Wireless Controller for PS5",
            link="https://www.ebay.com/itm/235990271882",
            item_id="235990271882",
            extracted_price=159.99,
            price="$159.99",
        )
    ]
    http_get, visto = _http_ebay(
        organic,
        {"235990271882": _product_payload(item_id="235990271882", title=organic[0]["title"], price=159.99)},
    )
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_A, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_proibido_ebay, confirmar=True,
    )
    assert ok == []
    assert nprod == 0
    assert "ebay_product" not in visto


def test_o_query_white_anuncio_black_rejeita_sem_ebay_product():
    http_get, visto = _http_ebay(
        [_org(title=TITULO + " Black")],
        {ITEM_ID: _product_payload(title=TITULO + " Black")},
    )
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_B, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_proibido_ebay, confirmar=True,
    )
    assert ok == []
    assert nprod == 0
    assert "ebay_product" not in visto


def test_p_query_white_anuncio_white_confirma():
    http_get, visto = _http_ebay(
        [_org(title=TITULO + " White")],
        {ITEM_ID: _product_payload(title=TITULO + " White")},
    )
    ok, _req, _norg, nprod = sap.completar_ebay_via_search(
        QUERY_B, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_proibido_ebay, confirmar=True,
    )
    assert nprod == 1
    assert "ebay_product" in visto
    assert len(ok) == 1
    assert ok[0]["original_url"] == PDP
    assert jds._id_ebay(ok[0]["affiliate_url"]) == ITEM_ID
    assert "white" in jds._sem_acento(ok[0]["titulo"])


def test_q_ebay_product_so_para_sobreviventes():
    organic = [_org() for _ in range(5)]
    organic.append(_org(
        title="Sony DualSense Edge Wireless Controller for PS5",
        link="https://www.ebay.com/itm/235990271882",
        item_id="235990271882",
        extracted_price=159.99,
    ))
    http_get, visto = _http_ebay(organic, {ITEM_ID: _product_payload()})
    _ok, _req, norg, nprod = sap.completar_ebay_via_search(
        QUERY_A, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_proibido_ebay, confirmar=True,
    )
    assert norg == 6
    assert nprod == 1
    assert visto.count("ebay_product") == 1
