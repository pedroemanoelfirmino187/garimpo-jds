"""Parser e pipeline SearchApi sem chamar a API real."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import garimpo_jds as jds
import jds_searchapi as sap

FIX = Path(__file__).resolve().parent / "fixtures" / "searchapi"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _http_get_mapa(mapa):
    def _get(params):
        engine = params.get("engine")
        if engine == "google_shopping":
            q = params.get("q") or ""
            gl = params.get("gl")
            if gl == "us":
                dados = _load("shopping_us_dualsense.json")
            else:
                dados = _load("shopping_br_controle_ps5.json")
            dados = dict(dados)
            dados.setdefault("search_parameters", {})
            dados["search_parameters"] = {
                "engine": "google_shopping",
                "q": q,
                "gl": gl,
                "hl": params.get("hl"),
            }
            return 200, dados, "{}"
        tok = params.get("product_token")
        if tok not in mapa:
            return 200, {"offers": []}, "{}"
        return 200, mapa[tok], "{}"

    return _get


def _html(titulo, preco, ident, pais="BR"):
    extra = "x" * 80
    return (
        f"<html><body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco}</span>{ident}{extra}</body></html>"
    )


def _baixar_br(url):
    u = url.lower()
    if "amazon.com.br" in u:
        return _html("Controle sem fio DualSense Sony PS5 Branco", "R$ 404,27", "B0CQKLS4RP")
    if "mercadolivre" in u:
        return _html("Controle DualSense Sony PlayStation 5", "R$ 419,00", "MLB-1234567890 /p/ MLB")
    if "shopee" in u:
        return _html("Controle Compatível com PS5 sem fio", "R$ 89,90", "-i.1608031728.2309811123")
    return ""


def _baixar_us(url):
    u = url.lower()
    if "amazon.com/" in u and "amazon.com.br" not in u:
        return _html("Sony DualSense Wireless Controller for PS5", "$74.99", "B08H99BPJN", pais="US")
    if "walmart.com" in u:
        return _html("Sony DualSense PS5 Wireless Controller", "$69.00", "123456789", pais="US")
    if "ebay.com" in u and "/itm/" in u:
        return _html("Sony DualSense Wireless Controller for PS5", "$74.99", "123456789012", pais="US")
    return ""


def test_chave_cache_separa_br_e_us():
    br = sap.chave_cache_searchapi("controle ps5 sony", "BR")
    us = sap.chave_cache_searchapi("controle ps5 sony", "US")
    assert br.startswith("BR:pt:")
    assert us.startswith("US:en:")
    assert br != us


def test_cfg_pais():
    br = sap._cfg_pais("BR")
    us = sap._cfg_pais("US")
    assert br == {"pais": "BR", "gl": "br", "hl": "pt", "currency": "BRL", "symbol": "R$"}
    assert us == {"pais": "US", "gl": "us", "hl": "en", "currency": "USD", "symbol": "$"}


def test_max_product_offers_padrao_3(monkeypatch):
    monkeypatch.delenv("SEARCHAPI_MAX_PRODUCT_OFFERS", raising=False)
    assert sap._max_product_offers() == 3
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "40")
    assert sap._max_product_offers() == 5
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    assert sap._max_product_offers() == 5


def test_max_requests_per_query_padrao_5(monkeypatch):
    monkeypatch.delenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", raising=False)
    assert sap._max_requests_per_query() == 5
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "99")
    assert sap._max_requests_per_query() == 8
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    assert sap._max_requests_per_query() == 5


def test_nao_inventa_product_token():
    shopping = _load("shopping_br_controle_ps5.json")["shopping_results"]
    shopping.append({"title": "Sony DualSense", "seller": "Amazon.com.br", "extracted_price": 400})
    cands = sap.selecionar_candidatos_token("controle ps5 sony", shopping, "BR", limite=5)
    assert all(c.get("product_token") for c in cands)


def test_shopping_preserva_ids_sem_inventar():
    query = "controle ps5 sony"
    com_ids = sap.shopping_para_candidato(
        query,
        {
            "title": "Sony DualSense PS5",
            "seller": "Amazon.com.br",
            "extracted_price": 404.27,
            "product_token": "tok-real",
            "product_id": "111",
            "merchant_id": "m-9",
            "immersive_product_page_token": "imm-abc",
        },
        "BR",
    )
    assert com_ids["product_id"] == "111"
    assert com_ids["merchant_id"] == "m-9"
    assert com_ids["immersive_product_page_token"] == "imm-abc"
    sem_ids = sap.shopping_para_candidato(
        query,
        {
            "title": "Sony DualSense PS5",
            "seller": "Amazon.com.br",
            "extracted_price": 404.27,
            "product_token": "tok-real",
        },
        "BR",
    )
    assert "product_id" not in sem_ids
    assert "merchant_id" not in sem_ids
    assert "immersive_product_page_token" not in sem_ids
    assert sem_ids["product_token"] == "tok-real"


def test_diagnostico_candidatos_antes_da_fila_po():
    visto = []
    shopping_results = [
        {
            "position": 1,
            "title": "Sony DualSense PS5",
            "seller": "Amazon.com.br",
            "extracted_price": 404.27,
            "product_token": "tok-a",
            "product_id": "pid-1",
            "merchant_id": "mer-1",
            "link": "https://www.google.com/search?ibp=oshop",
        },
        {
            "position": 2,
            "title": "Sony DualSense PS5",
            "seller": "Mercado Livre",
            "extracted_price": 419.0,
            "product_token": "tok-a",
            "product_id": "pid-1",
            "link": "https://www.google.com/search?ibp=oshop",
        },
        {
            "position": 3,
            "title": "Sony DualSense PS5",
            "seller": "Shopee",
            "extracted_price": 89.9,
            "product_id": "pid-2",
            "immersive_product_page_token": "imm-x",
            "link": "https://www.google.com/search?ibp=oshop",
        },
        {
            "position": 4,
            "title": "Sony DualSense PS5",
            "seller": "Amazon.com.br",
            "extracted_price": 410.0,
            "product_token": "tok-b",
            "product_id": "pid-3",
            "link": "https://www.google.com/search?ibp=oshop",
        },
    ]

    def _get(params):
        visto.append(dict(params))
        if params.get("engine") == "google_shopping":
            return 200, {"shopping_results": shopping_results}, "{}"
        if params.get("engine") == "google_product_page":
            assert params.get("product_id") == "pid-2"
            assert "product_token" not in params
            return 200, {"product": {}}, "{}"
        assert "product_id" not in params
        assert params.get("engine") == "google_product_offers"
        assert params.get("product_token") in {"tok-a", "tok-b"}
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        "controle ps5 sony",
        pais="BR",
        usar_cache=False,
        http_get=_get,
        confirmar=False,
    )
    diag = sap.ultimo_diag_searchapi()
    assert diag["candidates"] == 4
    assert diag["candidatos_com_product_token"] == 3
    assert diag["candidatos_sem_product_token"] == 1
    assert diag["product_token_distintos"] == 2
    assert diag["product_token_duplicados"] == 1
    assert diag["candidatos_com_product_id"] == 4
    assert diag["product_id_distintos"] == 3
    assert diag["candidatos_com_merchant_id"] == 1
    assert diag["candidatos_com_immersive_product_page_token"] == 1
    assert diag["po_fila_candidatos"] == 2
    assert diag["po_fila_tokens_distintos"] == 2
    dump = json.dumps(diag)
    for cru in ("tok-a", "tok-b", "pid-1", "pid-2", "pid-3", "mer-1", "imm-x"):
        assert cru not in dump
    po = [p for p in visto if p.get("engine") == "google_product_offers"]
    assert {p.get("product_token") for p in po} <= {"tok-a", "tok-b"}
    assert all("product_id" not in p for p in po)


def test_parser_rejeita_google_search():
    offer = {
        "title": "Sony DualSense PS5",
        "extracted_price": 404.27,
        "link": "https://www.google.com/search?q=controle+ps5",
        "merchant": {"name": "Amazon.com.br"},
    }
    assert sap.offer_para_item("controle ps5 sony", offer, "BR") is None


@pytest.mark.parametrize(
    "query,title,ok",
    [
        ("controle ps5", "Controle Sem Fio Compatível com PS5", False),
        ("controle ps5 sony", "Controle Sem Fio Compatível com PS5", False),
        ("controle ps5 sony", "Sony DualSense PS5", True),
        ("controle ps5 sony branco", "Sony DualSense PS5 Preto", False),
        ("controle ps5 sony branco", "Sony DualSense PS5 Branco", True),
        ("controle dualsense", "Sony DualSense PS5", True),
        ("controle dualsense", "Sony DualSense Edge PS5", False),
        ("controle dualsense edge", "Sony DualSense Edge PS5", True),
        ("iphone 15 128gb", "Apple iPhone 15 128GB", True),
        ("iphone 15 128gb", "Apple iPhone 15 256GB", False),
        ("iphone 15 256gb", "Apple iPhone 15 256GB", True),
        ("iphone 15 128gb usado", "Apple iPhone 15 128GB usado", True),
        ("iphone 15 128gb", "Apple iPhone 15 128GB seminovo", False),
        ("ps5 slim", "Sony PlayStation 5 Slim", True),
        ("ps5 slim", "Sony PlayStation 5", False),
        ("ps5 digital", "Sony PlayStation 5 Digital Edition", True),
    ],
)
def test_consultas_obrigatorias_matcher(query, title, ok):
    assert jds._jds_mesmo_produto(title, title, query) is ok


@pytest.mark.parametrize(
    "query,a,b",
    [
        ("controle ps5 sony", "Sony DualSense PS5", "Controle Compatível com PS5"),
        ("iphone 15 128gb", "Apple iPhone 15 128GB", "Apple iPhone 15 256GB"),
        ("ps5", "Sony PlayStation 5", "Sony PlayStation 5 Slim"),
        ("controle dualsense", "Sony DualSense PS5", "Sony DualSense Edge PS5"),
        ("iphone 15 128gb", "Apple iPhone 15 128GB novo", "Apple iPhone 15 128GB seminovo"),
    ],
)
def test_falsos_positivos_searchapi(query, a, b):
    assert jds._jds_mesmo_produto(a, b, query) is False


def test_pipeline_br_sem_rede():
    mapa = {
        "token-ps5-amazon": _load("offers_br_amazon.json"),
        "token-ps5-ml": _load("offers_br_ml.json"),
        "token-ps5-shopee": _load("offers_br_shopee.json"),
    }
    ofertas, status = sap.buscar_ofertas_searchapi(
        "controle ps5",
        pais="BR",
        usar_cache=False,
        http_get=_http_get_mapa(mapa),
        baixar=_baixar_br,
        confirmar=True,
    )
    assert status == "SEARCHAPI_SUCCESS"
    assert ofertas
    diag = sap.ultimo_diag_searchapi()
    assert diag["gl"] == "br"
    assert diag["hl"] == "pt"
    assert diag["product_offers_requests"] <= 3
    for o in ofertas:
        assert o.get("original_url")
        assert o.get("affiliate_url") or o.get("url")
        assert sap.validar_integridade_listing(o)
        plat = o["plataforma"]
        assert jds._url_anuncio_exato(o.get("original_url") or o.get("url"), plat)


def test_pipeline_sony_rejeita_compativel():
    mapa = {
        "token-ps5-amazon": _load("offers_br_amazon.json"),
        "token-ps5-ml": _load("offers_br_ml.json"),
        "token-ps5-shopee": _load("offers_br_shopee.json"),
    }
    ofertas, _status = sap.buscar_ofertas_searchapi(
        "controle ps5 sony",
        pais="BR",
        usar_cache=False,
        http_get=_http_get_mapa(mapa),
        baixar=_baixar_br,
        confirmar=True,
    )
    for o in ofertas:
        assert "compativel" not in jds._sem_acento(o["titulo"])
        assert "sony" in jds._sem_acento(o["titulo"]) or "dualsense" in jds._sem_acento(o["titulo"])


def test_pipeline_us_gl_hl_usd():
    mapa = {
        "token-us-amazon": _load("offers_us_amazon.json"),
        "token-us-walmart": _load("offers_us_walmart.json"),
        "token-us-ebay": _load("offers_us_ebay.json"),
    }
    ofertas, status = sap.buscar_ofertas_searchapi(
        "sony dualsense ps5",
        pais="US",
        usar_cache=False,
        http_get=_http_get_mapa(mapa),
        baixar=_baixar_us,
        confirmar=True,
    )
    diag = sap.ultimo_diag_searchapi()
    assert diag["gl"] == "us"
    assert diag["hl"] == "en"
    assert diag["currency"] == "USD"
    assert status in {"SEARCHAPI_SUCCESS", "SEARCHAPI_EMPTY"}
    for o in ofertas:
        assert o.get("pais") == "US"
        url = o.get("original_url") or o.get("url")
        assert "amazon.com.br" not in url.lower()
        assert jds._url_anuncio_exato(url, o["plataforma"])
        assert str(o.get("preco") or "").startswith("$")


def test_credito_nao_chama_40_offers(monkeypatch):
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "3")
    chamadas = {"offers": 0}

    def _get(params):
        if params.get("engine") == "google_shopping":
            results = []
            for i in range(12):
                results.append({
                    "position": i + 1,
                    "product_token": f"tok-{i}",
                    "title": "Sony DualSense PS5 Branco",
                    "seller": "Amazon.com.br",
                    "extracted_price": 404.27,
                    "link": "https://www.google.com/search?ibp=oshop",
                })
            return 200, {"shopping_results": results}, "{}"
        chamadas["offers"] += 1
        return 200, _load("offers_br_amazon.json"), "{}"

    sap.buscar_ofertas_searchapi(
        "controle ps5 sony branco",
        pais="BR",
        usar_cache=False,
        http_get=_get,
        baixar=_baixar_br,
        confirmar=False,
    )
    assert chamadas["offers"] <= 3


def test_health_tem_searchapi():
    from fastapi.testclient import TestClient
    from api.main import app

    data = TestClient(app).get("/health").json()
    assert "searchapi" in data["chaves"]
    assert data["deploy"] == "v44"
    assert "searchapi" in data["fonte"]
    assert data["afiliados"]["ebay"]


def test_admin_searchapi_sem_token_nao_expoe():
    from fastapi.testclient import TestClient
    from api.main import app
    import os

    old = os.environ.get("JDS_API_TOKEN")
    os.environ.pop("JDS_API_TOKEN", None)
    try:
        resp = TestClient(app).get("/admin/searchapi")
        assert resp.status_code == 404
    finally:
        if old is not None:
            os.environ["JDS_API_TOKEN"] = old


def test_garimpar_pais_us_assinatura():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from api.main import app

    fake = [{
        "titulo": "Sony DualSense Wireless Controller for PS5",
        "preco": "$74.99",
        "preco_numerico": 74.99,
        "link": "https://www.amazon.com/dp/B08H99BPJN",
        "imagem": "https://m.media-amazon.com/images/I/xx.jpg",
        "plataforma": "amazon",
        "loja": "Amazon",
        "pais": "US",
        "original_url": "https://www.amazon.com/dp/B08H99BPJN",
    }]
    with patch("api.main._buscar_serper_pais", return_value=fake):
        resp = TestClient(app).get("/garimpar", params={"q": "sony dualsense ps5", "pais": "US"})
    assert resp.status_code == 200
    assert resp.json()["pais"] == "US"
    assert resp.json()["total"] == 1


def _item_amazon_searchapi():
    ofe = _load("offers_br_amazon.json")["offers"][0]
    item = sap.offer_para_item("controle ps5 sony", ofe, "BR")
    assert item is not None
    item["url"] = item["original_url"] + "?tag=jdseconomiz0e-20"
    return item


def test_pdp_valida_confirma_uma():
    item = _item_amazon_searchapi()
    titulo, preco, orig = item["titulo"], item["preco_num"], item["original_url"]
    foto = item.get("foto")
    html = _html(titulo, "R$ 404,27", "B0CQKLS4RP")
    ok = jds._jds_confirmar_listings([item], pais="BR", baixar=lambda u: html)
    assert len(ok) == 1
    assert ok[0]["preco_num"] == pytest.approx(preco)
    assert ok[0]["titulo"] == titulo
    assert ok[0]["original_url"] == orig
    assert "tag=" in (ok[0].get("affiliate_url") or ok[0].get("url") or "")
    if foto:
        assert ok[0].get("foto") == foto


def test_html_vazio_rejeita():
    item = _item_amazon_searchapi()
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(item, baixar=lambda u: "", motivos=motivos) is None
    assert motivos["html_vazio"] == 1


def test_pagina_bloqueada_rejeita():
    item = _item_amazon_searchapi()
    motivos = sap._motivos_zerados()
    html = "sorry, we just need to make sure you're not a robot " + ("x" * 80)
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html, motivos=motivos) is None
    assert motivos["pagina_bloqueada"] == 1


def test_preco_divergente_rejeita():
    item = _item_amazon_searchapi()
    motivos = sap._motivos_zerados()
    html = _html(item["titulo"], "R$ 12,00", "B0CQKLS4RP")
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html, motivos=motivos) is None
    assert motivos["preco_nao_confere"] == 1


def test_titulo_modelo_divergente_rejeita():
    item = _item_amazon_searchapi()
    motivos = sap._motivos_zerados()
    html = _html("Apple iPhone 15 256GB Preto", "R$ 404,27", "B0CQKLS4RP")
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html, motivos=motivos) is None
    assert motivos["variante_nao_bate"] + motivos["matcher_rejeitou"] + motivos["condicao_nao_bate"] >= 1


def test_url_generica_rejeita():
    ofe = {
        "title": "Sony DualSense PS5",
        "extracted_price": 404.27,
        "link": "https://www.amazon.com.br/s?k=dualsense",
        "merchant": {"name": "Amazon.com.br"},
    }
    motivos = sap._motivos_zerados()
    assert sap.offer_para_item("controle ps5 sony", ofe, "BR", motivos=motivos) is None
    assert motivos["url_busca"] + motivos["url_nao_exata"] >= 1
    item = {
        "titulo": "Sony DualSense PS5",
        "preco_num": 404.27,
        "url": "https://www.amazon.com.br/s?k=dualsense",
        "original_url": "https://www.amazon.com.br/s?k=dualsense",
        "plataforma": "amazon",
        "pais": "BR",
    }
    assert jds._jds_confirmar_oferta_na_pagina(item, html=_html("Sony DualSense PS5", "R$ 404,27", "B0CQKLS4RP")) is None


def test_compativel_rejeitado_quando_consulta_pede_sony():
    ofe = _load("offers_br_shopee.json")["offers"][0]
    motivos = sap._motivos_zerados()
    assert sap.offer_para_item("controle ps5 sony", ofe, "BR", motivos=motivos) is None
    assert motivos["matcher_rejeitou"] + motivos["titulo_rejeitado"] >= 1


def test_confirmer_baixa_original_url_nao_afiliada():
    item = _item_amazon_searchapi()
    original = item["original_url"]
    item["url"] = original + "?tag=jdseconomiz0e-20"
    visto = []

    def baixar(url):
        visto.append(url)
        return _html(item["titulo"], "R$ 404,27", "B0CQKLS4RP")

    ok = jds._jds_confirmar_listings([item], pais="BR", baixar=baixar)
    assert visto == [original]
    assert "tag=" not in visto[0]
    assert len(ok) == 1
    assert ok[0]["original_url"] == original
    assert "tag=" in (ok[0].get("affiliate_url") or ok[0].get("url") or "")
    assert ok[0]["titulo"] == item["titulo"]
    assert ok[0]["preco_num"] == pytest.approx(404.27)


def test_url_google_shopping_rejeitada():
    ofe = {
        "title": "Sony DualSense PS5",
        "extracted_price": 404.27,
        "link": "https://www.google.com/search?ibp=oshop&q=controle+ps5+sony",
        "merchant": {"name": "Amazon.com.br"},
    }
    motivos = sap._motivos_zerados()
    amostras = []
    assert sap.offer_para_item("controle ps5 sony", ofe, "BR", motivos=motivos, amostras=amostras) is None
    assert motivos["url_google"] == 1
    assert amostras[0]["motivo"] == "url_google"


def test_mesma_oferta_apos_confirmacao():
    item = _item_amazon_searchapi()
    titulo, preco, foto, orig = item["titulo"], item["preco_num"], item.get("foto"), item["original_url"]
    html = _html(titulo, "R$ 404,27", "B0CQKLS4RP")
    ok = jds._jds_confirmar_listings([item], pais="BR", baixar=lambda u: html)
    assert len(ok) == 1
    assert ok[0]["titulo"] == titulo
    assert ok[0]["preco_num"] == pytest.approx(preco)
    assert ok[0]["original_url"] == orig
    if foto:
        assert ok[0].get("foto") == foto
    assert sap.validar_integridade_listing(ok[0])


def test_onze_ofertas_diagnostico_sem_rede():
    offers = _load("offers_br_11_diagnostico.json")
    shopping = _load("shopping_br_sony_token.json")

    def http_get(params):
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        return 200, offers, "{}"

    def baixar(url):
        assert "google." not in url.lower()
        assert "/s?" not in url
        assert "tag=" not in url
        return _html("Controle sem fio DualSense Sony PS5 Branco", "R$ 404,27", "B0CQKLS4RP")

    result, status = sap.buscar_ofertas_searchapi(
        "controle ps5 sony",
        pais="BR",
        usar_cache=False,
        http_get=http_get,
        baixar=baixar,
        confirmar=True,
    )
    diag = sap.ultimo_diag_searchapi()
    assert diag["offers_received"] == 11
    assert diag["offers_rejected"] == 10
    assert diag["etapas"]["apos_parser"] == 1
    assert diag["etapas"]["apos_matcher"] == 1
    assert diag["etapas"]["confirmer_entrada"] == 1
    assert status == "SEARCHAPI_SUCCESS"
    assert len(result) == 1
    assert result[0]["original_url"].endswith("/dp/B0CQKLS4RP")
    assert result[0]["preco_num"] == pytest.approx(404.27)
    assert result[0]["titulo"] == "Controle sem fio DualSense Sony PS5 Branco"
    assert result[0].get("foto") == "https://m.media-amazon.com/images/I/dualsense-white.jpg"
    amostras = diag.get("rejeicoes_ofertas") or []
    assert len(amostras) == 10
    for am in amostras:
        assert am.get("motivo")
        assert "titulo" in am
        assert "loja" in am
        assert "original_url" in am


ITEM_ID_ORC = "226994069950"
PDP_ORC = f"https://www.ebay.com/itm/{ITEM_ID_ORC}"
TITULO_ORC = "Sony DualSense Wireless Controller for PS5"
QUERY_ORC = "Sony DualSense PS5 controller"


def _html_orc(titulo, preco, item_id):
    extra = "x" * 80
    return (
        f"<html><head><meta property=\"og:title\" content=\"{titulo}\"></head>"
        f"<body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco}</span> item {item_id} {extra}</body></html>"
    )


def _baixar_us_orc(url):
    u = (url or "").lower()
    if "ebay.com/itm" not in u:
        return ""
    eid = jds._id_ebay(url) or "123456789012"
    preco = "$35.00" if eid == ITEM_ID_ORC else "$74.99"
    return _html_orc(TITULO_ORC, preco, eid)


def _product_orc(item_id=ITEM_ID_ORC, title=None, price=35.0):
    return {
        "item": {
            "item_id": item_id,
            "title": title or TITULO_ORC,
            "price": f"${price}",
            "extracted_price": price,
            "link": f"https://www.ebay.com/itm/{item_id}",
            "condition": "New",
            "main_image": "https://i.ebayimg.com/images/g/dualsense/s-l1600.jpg",
        }
    }


def _organic_orc(**kwargs):
    row = {
        "title": TITULO_ORC,
        "price": "$35.00",
        "extracted_price": 35.0,
        "link": PDP_ORC,
        "item_id": ITEM_ID_ORC,
        "thumbnail": "https://i.ebayimg.com/images/g/dualsense/s-l1600.jpg",
        "seller": "eBay",
    }
    row.update(kwargs)
    return row


@pytest.fixture
def cache_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_GARIMPO_DB", str(tmp_path / "orcamento.db"))
    sap._MEM.clear()
    jds._MEM_CACHE.clear()
    yield
    sap._MEM.clear()
    jds._MEM_CACHE.clear()


def test_1_us_sem_ebay_shopping_max_5_chega_ebay_product(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    shopping["shopping_results"] = [
        x for x in shopping["shopping_results"] if x.get("seller") != "eBay"
    ]

    def http_get(params):
        visto.append(dict(params))
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, shopping, "{}"
        if engine == "google_product_offers":
            return 200, {"offers": []}, "{}"
        if engine == "ebay_search":
            return 200, {"organic_results": [_organic_orc()]}, "{}"
        if engine == "ebay_product":
            assert params.get("item_id") == ITEM_ID_ORC
            return 200, _product_orc(), "{}"
        return 200, {}, "{}"

    result, status = sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=True,
    )
    engines = [p.get("engine") for p in visto]
    assert len(engines) <= 5
    assert "ebay_search" in engines
    assert "ebay_product" in engines
    ebay = [p for p in result if p.get("plataforma") == "ebay"]
    assert status == "SEARCHAPI_SUCCESS"
    assert ebay
    assert jds._id_ebay(ebay[0]["original_url"]) == ITEM_ID_ORC
    assert jds._id_ebay(ebay[0].get("affiliate_url") or "") == ITEM_ID_ORC
    assert "/itm/" + ITEM_ID_ORC in ebay[0]["original_url"]
    assert ebay[0].get("confirmacao") == "ebay_product"


def test_2_us_ebay_pdp_nao_chama_po_nem_ebay_search(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    rows = []
    for x in shopping["shopping_results"]:
        row = dict(x)
        if row.get("seller") == "eBay":
            row["link"] = PDP_ORC
            row["extracted_price"] = 35.0
            row["price"] = "$35.00"
        rows.append(row)
    shopping["shopping_results"] = rows

    def http_get(params):
        visto.append(dict(params))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("engine") == "ebay_search":
            raise AssertionError("ebay_search nao deveria ser chamado")
        if params.get("engine") == "ebay_product":
            raise AssertionError("ebay_product nao deveria ser chamado")
        if params.get("engine") == "google_product_offers":
            assert params.get("product_token") != "token-us-ebay"
            return 200, {"offers": []}, "{}"
        return 200, {}, "{}"

    result, status = sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=True,
    )
    engines = [p.get("engine") for p in visto]
    po_toks = [p.get("product_token") for p in visto if p.get("engine") == "google_product_offers"]
    assert "ebay_search" not in engines
    assert "token-us-ebay" not in po_toks
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("ebay_search_skip") == "ebay_ja_confirmado"
    ebay = next(p for p in result if p.get("plataforma") == "ebay")
    assert status == "SEARCHAPI_SUCCESS"
    assert jds._id_ebay(ebay["original_url"]) == ITEM_ID_ORC


def test_3_matcher_rejeita_sem_ebay_product(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    shopping["shopping_results"] = [
        x for x in shopping["shopping_results"] if x.get("seller") != "eBay"
    ]

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("engine") == "google_product_offers":
            return 200, {"offers": []}, "{}"
        if params.get("engine") == "ebay_search":
            return 200, {"organic_results": [_organic_orc(
                title="Sony DualSense Edge Wireless Controller for PS5",
            )]}, "{}"
        if params.get("engine") == "ebay_product":
            raise AssertionError("ebay_product nao para candidato rejeitado")
        return 200, {}, "{}"

    result, _status = sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=True,
    )
    diag = sap.ultimo_diag_searchapi()
    assert diag.get("ebay_product_requests") == 0
    assert "ebay_product" not in visto
    assert not [p for p in result if p.get("plataforma") == "ebay"]


def test_4_dez_iguais_usam_cache(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("engine") == "google_product_offers":
            tok = params.get("product_token")
            mapa = {
                "token-us-amazon": _load("offers_us_amazon.json"),
                "token-us-walmart": _load("offers_us_walmart.json"),
                "token-us-ebay": _load("offers_us_ebay.json"),
            }
            return 200, mapa.get(tok, {"offers": []}), "{}"
        if params.get("engine") == "ebay_search":
            return 200, {"organic_results": [_organic_orc()]}, "{}"
        if params.get("engine") == "ebay_product":
            return 200, _product_orc(), "{}"
        return 200, {}, "{}"

    por = []
    for _i in range(10):
        antes = len(visto)
        sap.buscar_ofertas_searchapi(
            QUERY_ORC, pais="US", usar_cache=True, http_get=http_get,
            baixar=_baixar_us_orc, confirmar=True,
        )
        por.append(len(visto) - antes)
    assert por[0] >= 1
    assert por[0] <= 5
    assert all(n == 0 for n in por[1:])
    assert sum(por) == por[0]


def test_5_consultas_diferentes_cache_separado(cache_isolado):
    visto = []

    def http_get(params):
        visto.append((params.get("engine"), params.get("q") or params.get("product_token")))
        if params.get("engine") == "google_shopping":
            return 200, _load("shopping_us_dualsense.json"), "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=True, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=False,
    )
    n1 = len(visto)
    sap.buscar_ofertas_searchapi(
        "Sony DualSense Edge PS5 controller", pais="US", usar_cache=True, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=False,
    )
    assert len(visto) > n1
    shops = [q for eng, q in visto if eng == "google_shopping"]
    assert len(shops) == 2
    assert shops[0] != shops[1]


def test_6_us_e_br_caches_separados_br_sem_ebay(cache_isolado):
    visto = []

    def http_get(params):
        visto.append((params.get("engine"), params.get("gl") or params.get("country")))
        if params.get("engine") == "ebay_search":
            raise AssertionError("BR nao chama ebay_search")
        if params.get("engine") == "ebay_product":
            raise AssertionError("BR nao chama ebay_product")
        if params.get("engine") == "google_shopping":
            if params.get("gl") == "br":
                return 200, _load("shopping_br_controle_ps5.json"), "{}"
            return 200, _load("shopping_us_dualsense.json"), "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=True, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=False,
    )
    n_us = len(visto)
    sap.buscar_ofertas_searchapi(
        "controle ps5", pais="BR", usar_cache=True, http_get=http_get,
        baixar=_baixar_br, confirmar=False,
    )
    br_engines = [e for e, _g in visto[n_us:]]
    assert "google_shopping" in br_engines
    assert "ebay_search" not in br_engines
    assert "ebay_product" not in br_engines
    gls = [g for e, g in visto if e == "google_shopping"]
    assert "us" in gls and "br" in gls
    chave_us = "shop:" + sap.chave_cache_searchapi(QUERY_ORC, "US")
    chave_br = "shop:" + sap.chave_cache_searchapi("controle ps5", "BR")
    assert chave_us != chave_br
    assert sap._ler_cache(chave_us, 900) is not None
    assert sap._ler_cache(chave_br, 900) is not None


def test_7_timeout_uma_tentativa(cache_isolado):
    visto = []

    def http_get(params):
        visto.append(params.get("engine"))
        raise TimeoutError("timed out")

    result, status = sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=True,
    )
    assert status == "SEARCHAPI_ERROR"
    assert result == []
    assert visto == ["google_shopping"]
    diag = sap.ultimo_diag_searchapi()
    assert "timed out" in str(diag.get("erro") or "")


def test_8_product_token_duplicado_uma_po(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    rows = list(shopping["shopping_results"])
    rows.append(dict(rows[0]))
    shopping["shopping_results"] = rows

    def http_get(params):
        visto.append(dict(params))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=False,
    )
    po = [p.get("product_token") for p in visto if p.get("engine") == "google_product_offers"]
    assert po.count("token-us-amazon") <= 1
    assert len(po) == len(set(po))


def test_9_economia_nao_altera_identidade_ebay(cache_isolado):
    visto = []
    shopping = _load("shopping_us_dualsense.json")
    shopping = dict(shopping)
    shopping["shopping_results"] = [
        x for x in shopping["shopping_results"] if x.get("seller") != "eBay"
    ]

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "google_shopping":
            return 200, shopping, "{}"
        if params.get("engine") == "google_product_offers":
            return 200, {"offers": []}, "{}"
        if params.get("engine") == "ebay_search":
            return 200, {"organic_results": [_organic_orc()]}, "{}"
        if params.get("engine") == "ebay_product":
            return 200, _product_orc(), "{}"
        return 200, {}, "{}"

    result, _status = sap.buscar_ofertas_searchapi(
        QUERY_ORC, pais="US", usar_cache=False, http_get=http_get,
        baixar=_baixar_us_orc, confirmar=True,
    )
    ebay = [p for p in result if p.get("plataforma") == "ebay"][0]
    assert ebay["titulo"] == TITULO_ORC
    assert ebay["preco_num"] == pytest.approx(35.0)
    assert ebay["plataforma"] == "ebay"
    assert ebay["original_url"] == PDP_ORC
    assert jds._id_ebay(ebay["original_url"]) == ITEM_ID_ORC
    assert jds._id_ebay(ebay.get("affiliate_url") or "") == ITEM_ID_ORC
    assert ebay.get("confirmacao") == "ebay_product"
    assert "rover.ebay.com" in (ebay.get("affiliate_url") or "")
    assert f"campid={jds.ID_EBAY_CAMPAIGN}" in (ebay.get("affiliate_url") or "")
    assert len(visto) <= 5


def _br_shop_row(**kwargs):
    row = {
        "title": "Apple iPhone 15 128GB",
        "seller": "Amazon.com.br",
        "extracted_price": 4999.0,
        "link": "https://www.google.com/search?ibp=oshop",
    }
    row.update(kwargs)
    return row


def test_product_page_recupera_token_e_chama_po(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    visto = []
    shopping = [
        _br_shop_row(position=1, product_token="tok-amz", seller="Amazon.com.br"),
        _br_shop_row(position=2, product_token="tok-ml", seller="Mercado Livre"),
        _br_shop_row(position=3, product_id="pid-sem-tok", seller="Shopee"),
    ]

    def http_get(params):
        visto.append(dict(params))
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_page":
            assert params.get("product_id") == "pid-sem-tok"
            assert params.get("gl") == "br"
            assert params.get("hl") == "pt"
            assert not params.get("product_token")
            return 200, {"product": {"product_token": "tok-recuperado"}}, "{}"
        if engine == "google_product_offers":
            assert "product_id" not in params
            assert params.get("product_token")
            return 200, {"offers": []}, "{}"
        raise AssertionError(engine)

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    engines = [p.get("engine") for p in visto]
    assert engines[0] == "google_shopping"
    assert engines.count("google_product_page") == 1
    po = [p.get("product_token") for p in visto if p.get("engine") == "google_product_offers"]
    assert "tok-recuperado" in po
    assert "pid-sem-tok" not in po
    assert all("product_id" not in p for p in visto if p.get("engine") == "google_product_offers")
    assert len(visto) <= 5
    diag = sap.ultimo_diag_searchapi()
    assert diag["product_page_requests"] == 1
    assert diag["product_page_recovered"] == 1
    assert diag["product_page_failed"] == 0
    assert diag["product_page_product_tokens_recovered"] == 1
    dump = json.dumps(diag)
    assert "tok-recuperado" not in dump
    assert "tok-amz" not in dump
    assert "pid-sem-tok" not in dump


def test_product_page_sem_token_nao_chama_po_invalido(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    visto = []
    shopping = [
        _br_shop_row(position=1, product_token="tok-amz", seller="Amazon.com.br"),
        _br_shop_row(position=2, product_id="pid-x", seller="Shopee"),
    ]

    def http_get(params):
        visto.append(dict(params))
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_page":
            return 200, {"product": {"title": "Apple iPhone 15 128GB"}}, "{}"
        if engine == "google_product_offers":
            assert params.get("product_token") == "tok-amz"
            assert "product_id" not in params
            return 200, {"offers": []}, "{}"
        raise AssertionError(engine)

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    po = [p for p in visto if p.get("engine") == "google_product_offers"]
    assert all(p.get("product_token") == "tok-amz" for p in po)
    diag = sap.ultimo_diag_searchapi()
    assert diag["product_page_failed"] == 1
    assert diag["product_page_recovered"] == 0
    assert diag["product_page_product_tokens_recovered"] == 0
    assert len(visto) <= 5


def test_sem_product_id_nao_chama_product_page(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    visto = []
    shopping = [
        _br_shop_row(position=1, product_token="tok-amz", seller="Amazon.com.br"),
        _br_shop_row(position=2, product_token="tok-ml", seller="Mercado Livre"),
        _br_shop_row(position=3, product_token="tok-sh", seller="Shopee"),
    ]

    def http_get(params):
        visto.append(dict(params))
        if params.get("engine") == "google_product_page":
            raise AssertionError("nao chama product_page sem product_id")
        if params.get("engine") == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    assert "google_product_page" not in [p.get("engine") for p in visto]
    diag = sap.ultimo_diag_searchapi()
    assert diag["product_page_skipped"] == 1
    assert diag["product_page_requests"] == 0


def test_orcamento_nunca_ultrapassa_5_com_product_page(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    visto = []
    shopping = [
        _br_shop_row(position=i + 1, product_token=f"tok-{i}", seller="Amazon.com.br")
        for i in range(6)
    ]
    shopping.append(_br_shop_row(position=7, product_id="pid-7", seller="Shopee"))

    def http_get(params):
        visto.append(dict(params))
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_page":
            return 200, {"product": {"product_token": "tok-novo"}}, "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    assert len(visto) <= 5
    diag = sap.ultimo_diag_searchapi()
    assert diag["searchapi_requests"] <= 5
    assert diag["searchapi_budget"] == 5


def test_cenario_br_shopping_po_page_po_max_5(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "5")
    visto = []
    shopping = [
        _br_shop_row(position=1, product_token="tok-1", seller="Amazon.com.br"),
        _br_shop_row(position=2, product_token="tok-2", seller="Mercado Livre"),
        _br_shop_row(position=3, product_token="tok-3", seller="Shopee"),
        _br_shop_row(position=4, product_id="pid-a", seller="Amazon.com.br"),
        _br_shop_row(position=5, product_id="pid-b", seller="Mercado Livre"),
        _br_shop_row(position=6, seller="Shopee"),
        _br_shop_row(position=7, product_token="tok-1", seller="Amazon.com.br"),
    ]

    def http_get(params):
        visto.append(dict(params))
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_page":
            assert params.get("product_id") in {"pid-a", "pid-b"}
            return 200, {"product": {"product_token": "tok-page"}}, "{}"
        if engine == "google_product_offers":
            assert "product_id" not in params
            return 200, {"offers": []}, "{}"
        raise AssertionError(engine)

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    engines = [p.get("engine") for p in visto]
    assert engines[0] == "google_shopping"
    assert engines.count("google_shopping") == 1
    assert engines.count("google_product_page") == 1
    assert engines.count("google_product_offers") <= 3
    assert len(visto) == 5
    assert engines == [
        "google_shopping",
        "google_product_offers",
        "google_product_offers",
        "google_product_page",
        "google_product_offers",
    ]
    assert visto[-1].get("product_token") == "tok-page"
    diag = sap.ultimo_diag_searchapi()
    assert diag["searchapi_engines"] == engines
    assert diag["searchapi_requests"] == 5
    assert diag["searchapi_budget_atingido"] is True
    dump = json.dumps(diag)
    assert "tok-page" not in dump
    assert "pid-a" not in dump


def test_sem_candidato_elegivel_page_comportamento_anterior(monkeypatch, cache_isolado):
    monkeypatch.setenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", "5")
    monkeypatch.setenv("SEARCHAPI_MAX_PRODUCT_OFFERS", "3")
    visto = []
    shopping = [
        _br_shop_row(position=1, product_token="tok-1", seller="Amazon.com.br"),
        _br_shop_row(position=2, product_token="tok-2", seller="Mercado Livre"),
        _br_shop_row(position=3, product_token="tok-3", seller="Shopee"),
    ]

    def http_get(params):
        visto.append(dict(params))
        if params.get("engine") == "google_product_page":
            raise AssertionError("sem candidato page")
        if params.get("engine") == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        return 200, {"offers": []}, "{}"

    sap.buscar_ofertas_searchapi(
        "iphone 15 128gb", pais="BR", usar_cache=False, http_get=http_get, confirmar=False,
    )
    engines = [p.get("engine") for p in visto]
    assert engines == [
        "google_shopping",
        "google_product_offers",
        "google_product_offers",
        "google_product_offers",
    ]
    diag = sap.ultimo_diag_searchapi()
    assert diag["product_page_skipped"] == 1
    assert diag["product_offers_requests"] == 3


def test_product_page_nao_altera_allowlist_usado_matcher_confirmer():
    assert jds._lojas_do_pais("BR") == ("amazon", "mercado_livre", "shopee")
    assert "magazine_luiza" not in jds._lojas_do_pais("BR")
    assert jds._titulo_usado("iPhone 15 128GB seminovo") is True
    assert jds._titulo_usado("iPhone 15 128GB") is False
    assert jds._jds_mesmo_produto(
        "Apple iPhone 15 128GB", "Apple iPhone 15 128GB", "iphone 15 128gb"
    ) is True
    assert jds._jds_mesmo_produto(
        "Apple iPhone 15 128GB", "Apple iPhone 15 256GB", "iphone 15 128gb"
    ) is False
    assert hasattr(jds, "_jds_confirmar_listings")
