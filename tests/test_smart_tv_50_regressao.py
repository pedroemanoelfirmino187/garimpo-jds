"""Regressão da busca real 'smart tv 50' que voltou vazia.

A oferta Amazon 'Smart TV 50" ... Compatível com Alexa e Google Home - TL059M'
(ASIN B0DBM7323B, R$ 2299,90) era descartada como anúncio genérico porque
'compatível' virava nao_original. O único anúncio allowlisted que sobrava
(ML) caía em html_vazio e a consulta terminava com 0 ofertas.
"""
from __future__ import annotations

import garimpo_jds as jds
import jds_searchapi as sap

Q = "smart tv 50"
TITULO_AMZ = (
    'Smart TV 50" Roku Multi 4K Compatível com Alexa e Google Home - TL059M'
)
PRECO_AMZ = 2299.90
ASIN = "B0DBM7323B"
PDP_AMZ = f"https://www.amazon.com.br/dp/{ASIN}"
TITULO_ML = "Smart Tv 50 Polegadas Dled 4k Multi Roku 4hdmi 2usb Wi-fi"
PRECO_ML = 2229.06
PDP_ML = (
    "https://www.mercadolivre.com.br/"
    "smart-tv-50-polegadas-dled-4k-multi-roku-4hdmi-2usb-wifi/up/MLBU3365756008"
)
TITULO_32 = "TV Samsung Smart HD 32 LS32H5000"
TITULO_GENERICO = "Controle Sem Fio Compatível com PS5"


def _html_amazon(titulo, preco_txt, asin):
    return (
        f'<html><head><meta property="og:title" content="{titulo}"></head>'
        f"<body><span id=\"productTitle\">{titulo}</span>"
        f'<span class="a-offscreen">{preco_txt}</span>'
        f"{asin}"
        + ("x" * 80)
        + "</body></html>"
    )


def test_titulo_real_amazon_bate_consulta_smart_tv_50():
    assert jds._jds_anuncio_bate_consulta(Q, TITULO_AMZ) is True
    assert jds._titulo_shopping_ok(Q, TITULO_AMZ) is True
    assert "nao_original" not in jds._jds_hard_features(TITULO_AMZ)[3]


def test_compativel_com_console_continua_generico():
    assert jds._jds_anuncio_bate_consulta("controle ps5", TITULO_GENERICO) is False
    assert "nao_original" in jds._jds_hard_features(TITULO_GENERICO)[3]


def test_tv_32_nao_passa_como_50():
    assert jds._jds_anuncio_bate_consulta(Q, TITULO_32) is False
    assert jds._titulo_relevante(Q, TITULO_32) is False


def test_pipeline_smart_tv_50_confirma_amazon_quando_ml_vem_sem_html(monkeypatch):
    """O caso que zerou a busca: Amazon válida + ML com HTML vazio."""
    monkeypatch.delenv("SEARCHAPI_MAX_PRODUCT_OFFERS", raising=False)
    monkeypatch.delenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", raising=False)
    foto = "https://example.com/tv50.jpg"
    shopping = [
        {
            "position": 1,
            "title": TITULO_AMZ,
            "seller": "Amazon.com.br - Seller",
            "extracted_price": PRECO_AMZ,
            "link": PDP_AMZ,
            "product_token": "tok-amz-tl059m",
            "product_id": "gpid-amz-tl059m",
            "thumbnail": foto,
        },
        {
            "position": 2,
            "title": TITULO_ML,
            "seller": "Mercado Livre",
            "extracted_price": PRECO_ML,
            "link": PDP_ML,
            "product_token": "tok-ml-roku",
            "product_id": "gpid-ml-roku",
            "thumbnail": foto,
        },
    ]
    offers = {
        "tok-amz-tl059m": {
            "offers": [{
                "title": TITULO_AMZ,
                "extracted_price": PRECO_AMZ,
                "price": "R$ 2.299,90",
                "link": PDP_AMZ,
                "merchant": {"name": "Amazon.com.br"},
                "thumbnail": foto,
                "product_token": "tok-amz-tl059m",
                "product_id": "gpid-amz-tl059m",
            }]
        },
        "tok-ml-roku": {
            "offers": [{
                "title": TITULO_ML,
                "extracted_price": PRECO_ML,
                "price": "R$ 2.229,06",
                "link": PDP_ML,
                "merchant": {"name": "Mercado Livre"},
                "thumbnail": foto,
                "product_token": "tok-ml-roku",
                "product_id": "gpid-ml-roku",
            }]
        },
    }

    def http_get(params):
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_offers":
            return 200, offers.get(params.get("product_token"), {"offers": []}), "{}"
        return 200, {}, "{}"

    def baixar(url):
        if ASIN.lower() in (url or "").lower():
            return _html_amazon(TITULO_AMZ, "R$ 2.299,90", ASIN)
        return ""

    ofertas, status = sap.buscar_ofertas_searchapi(
        Q,
        pais="BR",
        usar_cache=False,
        http_get=http_get,
        baixar=baixar,
        confirmar=True,
    )
    diag = sap.ultimo_diag_searchapi()
    assert status == "SEARCHAPI_SUCCESS"
    assert diag["offers_confirmed"] >= 1
    amazon = [o for o in ofertas if o.get("plataforma") == "amazon"]
    assert amazon, diag.get("rejeicoes")
    assert amazon[0]["original_url"] == PDP_AMZ
    assert amazon[0]["preco_num"] == PRECO_AMZ
    assert jds._asin_amazon(amazon[0]["original_url"]) == ASIN
    motivos = diag.get("rejeicoes") or {}
    assert motivos.get("matcher_rejeitou", 0) == 0
