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


def test_nao_inventa_product_token():
    shopping = _load("shopping_br_controle_ps5.json")["shopping_results"]
    shopping.append({"title": "Sony DualSense", "seller": "Amazon.com.br", "extracted_price": 400})
    cands = sap.selecionar_candidatos_token("controle ps5 sony", shopping, "BR", limite=5)
    assert all(c.get("product_token") for c in cands)


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
