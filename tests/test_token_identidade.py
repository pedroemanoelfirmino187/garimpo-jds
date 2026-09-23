"""product_token/product_id = produto Google vs oferta Amazon. Sem APIs reais."""
from __future__ import annotations

import json
from pathlib import Path

import garimpo_jds as jds
import jds_searchapi as sap

from tests.test_amazon_captcha_audit import (
    ASIN_OK,
    ASIN_OUTRO,
    HTML_CAPTCHA_AMZ,
    PDP_AMZ,
    PDP_OUTRO,
    PRECO_TV,
    TITULO_TV,
    _amz,
    _captcha,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "searchapi"
TOKEN_PRODUTO = "tok-produto-google-tv"
PID_PRODUTO = "gpid-google-tv"
Q = "smart tv 50"


def _ofe_amz(asin, preco, token=TOKEN_PRODUTO, pid=PID_PRODUTO):
    return {
        "title": TITULO_TV,
        "extracted_price": preco,
        "price": f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "link": f"https://www.amazon.com.br/dp/{asin}",
        "merchant": {"name": "Amazon.com.br"},
        "thumbnail": "https://example.com/tv.jpg",
        "product_token": token,
        "product_id": pid,
    }


def test_mesmo_token_id_duas_ofertas_amazon_asins_diferentes():
    """Um product_token alimenta PO com duas PDPs Amazon. Token = produto Google."""
    a = sap.offer_para_item(Q, _ofe_amz(ASIN_OK, 1849.0), pais="BR")
    b = sap.offer_para_item(Q, _ofe_amz(ASIN_OUTRO, 1999.0), pais="BR")
    assert a is not None and b is not None
    assert a["listing_source"]["product_token"] == b["listing_source"]["product_token"] == TOKEN_PRODUTO
    assert a["listing_source"]["product_id"] == b["listing_source"]["product_id"] == PID_PRODUTO
    assert jds._asin_amazon(a["original_url"]) == ASIN_OK
    assert jds._asin_amazon(b["original_url"]) == ASIN_OUTRO
    assert a["preco_num"] != b["preco_num"]


def test_consumir_po_carimba_token_do_produto_em_todas_as_ofertas(monkeypatch):
    shopping = [
        {
            "title": TITULO_TV,
            "seller": "Amazon.com.br",
            "extracted_price": 1849.0,
            "link": "https://www.google.com/search?ibp=oshop&q=tv",
            "product_token": TOKEN_PRODUTO,
            "product_id": PID_PRODUTO,
            "thumbnail": "https://example.com/tv.jpg",
        }
    ]
    offers = {
        "offers": [
            _ofe_amz(ASIN_OK, 1849.0, token="", pid=""),
            _ofe_amz(ASIN_OUTRO, 1999.0, token="", pid=""),
        ]
    }

    def http_get(params):
        if params.get("engine") == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if params.get("engine") == "google_product_offers":
            assert params.get("product_token") == TOKEN_PRODUTO
            assert "product_id" not in params
            return 200, offers, "{}"
        return 200, {}, "{}"

    result, _status = sap.buscar_ofertas_searchapi(
        Q, pais="BR", usar_cache=False, http_get=http_get,
        baixar=lambda u: HTML_CAPTCHA_AMZ, confirmar=False,
    )
    diag = sap.ultimo_diag_searchapi()
    etapas = diag.get("etapas") or {}
    assert diag["offers_received"] == 2
    assert (etapas.get("apos_parser") or 0) == 2
    assert (etapas.get("apos_matcher") or 0) == 1
    assert result
    asins_parser = {ASIN_OK, ASIN_OUTRO}
    assert jds._asin_amazon(result[0]["original_url"]) in asins_parser
    for p in result:
        assert p["listing_source"]["product_token"] == TOKEN_PRODUTO
        assert p["listing_source"]["product_id"] == PID_PRODUTO


def test_shopping_com_pdp_asin_a_pula_po_nao_mistura_asin_b(monkeypatch):
    shopping = [
        {
            "title": TITULO_TV,
            "seller": "Amazon.com.br",
            "extracted_price": 1849.0,
            "link": PDP_AMZ,
            "product_token": TOKEN_PRODUTO,
            "product_id": PID_PRODUTO,
            "thumbnail": "https://example.com/tv.jpg",
        }
    ]
    visto_po = []

    def http_get(params):
        if params.get("engine") == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if params.get("engine") == "google_product_offers":
            visto_po.append(params)
            return 200, {"offers": [_ofe_amz(ASIN_OUTRO, 1999.0)]}, "{}"
        return 200, {}, "{}"

    result, _status = sap.buscar_ofertas_searchapi(
        Q, pais="BR", usar_cache=False, http_get=http_get,
        baixar=lambda u: HTML_CAPTCHA_AMZ, confirmar=False,
    )
    assert visto_po == []
    assert sap.ultimo_diag_searchapi()["product_offers_requests"] == 0
    assert result
    assert all(jds._asin_amazon(p["original_url"]) == ASIN_OK for p in result)
    assert all(jds._asin_amazon(p["original_url"]) != ASIN_OUTRO for p in result)


def test_fixtures_token_nao_carrega_catalogid_nem_asin():
    for nome in ("shopping_br_controle_ps5.json", "shopping_us_dualsense.json", "shopping_br_sony_token.json"):
        bruto = json.loads((FIX / nome).read_text(encoding="utf-8"))
        for row in bruto.get("shopping_results") or []:
            tok = str(row.get("product_token") or "")
            assert tok
            assert "catalogid" not in tok.lower()
            assert "gpcid" not in tok.lower()
            assert "B0" not in tok
            assert len(sap._hash_token(tok)) == 24


def test_identidade_a_token_id_asin_preco_titulo_aceitam():
    ok, motivos = _captcha(_amz())
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert motivos.get("pagina_bloqueada", 0) == 0


def test_identidade_b_mesmo_token_asin_diferente_rejeita():
    item = _amz()
    item["listing_source"]["url"] = PDP_OUTRO
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_identidade_c_merchant_diferente_mesmo_asin_nao_usa_seller():
    item = _amz(listing={"vendedor": "Amazon.com.br - Seller"})
    ok, _motivos = _captcha(item)
    assert ok is not None
    assert ok["original_url"] == PDP_AMZ
    assert jds._searchapi_amazon_captcha_estruturado_ok(
        item, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is True


def test_identidade_d_mesmo_token_product_id_diferente_asin_ok():
    item = _amz(listing={"product_id": "gpid-outro-google"})
    ok, _motivos = _captcha(item)
    assert ok is not None
    assert str(item["listing_source"]["product_id"]) == "gpid-outro-google"


def test_identidade_e_mesmo_product_id_token_diferente_asin_ok():
    item = _amz(listing={"product_token": "tok-outro-google"})
    ok, _motivos = _captcha(item)
    assert ok is not None
    assert item["listing_source"]["product_token"] == "tok-outro-google"


def test_identidade_f_preco_diferente_rejeita():
    item = _amz(listing={"preco_num": 9999.0, "extracted_price": 9999.0})
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_identidade_g_titulo_diferente_rejeita():
    item = _amz(listing={"titulo": "Geladeira Frost Free 400L"})
    ok, motivos = _captcha(item)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1


def test_integridade_mesma_linha_preco_url_titulo():
    ofe = _ofe_amz(ASIN_OK, 1849.0)
    item = sap.offer_para_item(Q, ofe, pais="BR")
    assert sap.validar_integridade_listing(item) is True
    item["preco_num"] = 10.0
    assert sap.validar_integridade_listing(item) is False
