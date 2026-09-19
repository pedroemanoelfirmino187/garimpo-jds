"""Resolução da URL de anúncio a partir do HTML do Google Shopping."""
from __future__ import annotations

import garimpo_jds as jds


PONTE = (
    "https://www.google.com/search?ibp=oshop&q=iphone+15+128gb"
    "&prds=localAnnotatedOfferId:1,catalogid:871091021334399569,pvo:2,pvt:hg"
    "&gl=br&udm=28&pvorigin=2"
)
IMG = "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:CARDIMG15"
ASIN_RETAIL = "B0CP6CVJSG"
ASIN_SELLER = "B0FTKPP8LZ"
MLB_OK = "2000139744"
MLB_VIZINHO = "1027172677"
SHOPEE_OK = "https://shopee.com.br/iPhone-15-128GB-Preto-i.1608031728.2309811123"


def _card(**kwargs):
    base = {
        "title": "Apple iPhone 15 128GB Preto",
        "source": "Amazon.com.br - Retail",
        "link": PONTE,
        "price": "R$ 4.776,77",
        "imageUrl": IMG,
        "productId": "871091021334399569",
    }
    base.update(kwargs)
    return base


def _html_amazon_dois_cards():
    return f"""
    <html>
      <div class="vizinho" data-item-index="1"
           data-redirect-url="https://www.amazon.com.br/Apple-iPhone-15-128-Recondicionado/dp/{ASIN_SELLER}?psc=1">
        <span>Amazon.com.br - Seller</span>
      </div>
      <div class="destaque" data-item-index="0"
           data-redirect-url="https://www.amazon.com.br/Apple-iPhone-15-128-GB/dp/{ASIN_RETAIL}?source=ps-sl-shoppingads-lpcontext&amp;psc=1"
           data-target-url="https://www.amazon.com.br/Apple-iPhone-15-128-GB/dp/{ASIN_RETAIL}"
           ping="/url?sa=t&amp;source=web&amp;rct=j&amp;url=https://www.amazon.com.br/Apple-iPhone-15-128-GB/dp/{ASIN_RETAIL}%3Fpsc%3D1">
        <span>Amazon.com.br - Retail</span>
      </div>
    </html>
    """


def _html_ml_com_amazon_vizinha():
    return f"""
    <html>
      <div data-redirect-url="https://www.amazon.com.br/Apple-iPhone-15-Pro-128/dp/B0CHXRHSLC">
        <span>Amazon.com.br - Retail</span>
      </div>
      <div data-redirect-url="https://www.mercadolivre.com.br/apple-iphone-15-128-gb-preto/p/MLB{MLB_OK}"
           ping="/url?sa=t&amp;url=https://www.mercadolivre.com.br/apple-iphone-15-128-gb-preto/p/MLB{MLB_OK}">
        <span>Mercado Livre</span>
      </div>
    </html>
    """


def _html_ml_ambiguo():
    return f"""
    <html>
      <div data-redirect-url="https://www.mercadolivre.com.br/apple-iphone-15/p/MLB{MLB_OK}">
        <span>Mercado Livre</span>
      </div>
      <div data-redirect-url="https://www.mercadolivre.com.br/apple-iphone-15-pro/p/MLB{MLB_VIZINHO}">
        <span>Mercado Livre</span>
      </div>
    </html>
    """


def _html_shopee_ok():
    return f"""
    <html>
      <div data-redirect-url="https://www.magazineluiza.com.br/iphone-15/p/abc">
        <span>Magalu</span>
      </div>
      <div data-redirect-url="{SHOPEE_OK}">
        <span>Shopee</span>
      </div>
    </html>
    """


def _html_shopee_sem_pdp():
    return """
    <html>
      <div data-redirect-url="https://shopee.com.br/search?keyword=iphone+15">
        <span>Shopee</span>
      </div>
      <div data-redirect-url="https://www.magazineluiza.com.br/iphone-15/p/abc">
        <span>Magalu</span>
      </div>
    </html>
    """


def _baixar(html):
    def _fn(url):
        assert "google.com" in url
        assert "ibp=oshop" in url
        return html
    return _fn


def _item(card, html):
    return jds._jds_item_serper("iphone 15 128gb", card, pais="BR", baixar=_baixar(html))


def test_amazon_card_encontra_dp_asin_correto():
    item = _item(_card(), _html_amazon_dois_cards())
    assert item is not None
    assert ASIN_RETAIL in item["url"]
    assert ASIN_SELLER not in item["url"]
    assert jds._url_anuncio_exato(item["url"], "amazon")
    assert "google." not in item["url"].lower()


def test_amazon_seller_nao_usa_asin_de_outro_card():
    card = _card(
        source="Amazon.com.br - Seller",
        title="Apple iPhone 15 128GB Preto",
        price="R$ 2.931,65",
        productId="17087176537471722413",
    )
    item = _item(card, _html_amazon_dois_cards())
    assert item is not None
    assert ASIN_SELLER in item["url"]
    assert ASIN_RETAIL not in item["url"]


def test_mercado_livre_nao_pega_dp_amazon_do_mesmo_html():
    card = _card(
        source="Mercado Livre",
        price="R$ 3.199,00",
        productId="7918653946291441411",
    )
    item = _item(card, _html_ml_com_amazon_vizinha())
    assert item is not None
    assert item["plataforma"] == "mercado_livre"
    assert MLB_OK in item["url"]
    assert "/dp/" not in item["url"]
    assert "amazon." not in item["url"].lower()


def test_mercado_livre_aceita_somente_mlb_do_bloco_correto():
    card = _card(source="Mercado Livre", price="R$ 3.199,00")
    assert _item(card, _html_ml_ambiguo()) is None
    item = _item(card, _html_ml_com_amazon_vizinha())
    assert item is not None
    assert MLB_OK in item["url"]
    assert MLB_VIZINHO not in item["url"]


def test_shopee_aceita_somente_url_pdp_exata():
    card = _card(
        source="Shopee",
        title="iPhone 15 128GB Preto Poucas Marcas",
        price="R$ 2.850,00",
    )
    item = _item(card, _html_shopee_ok())
    assert item is not None
    assert item["plataforma"] == "shopee"
    assert "-i.1608031728.2309811123" in item["url"]
    assert jds._url_anuncio_exato(item["url"], "shopee")


def test_shopee_sem_url_exata_descarta():
    card = _card(source="Shopee", price="R$ 2.850,00")
    assert _item(card, _html_shopee_sem_pdp()) is None
    assert _item(card, "<html>localAnnotatedOfferId:1,productid:5178971384858540456</html>") is None


def test_google_search_nunca_chega_ao_matcher_como_anuncio():
    card = _card()
    cands = jds._jds_extrair_candidatos(
        "iphone 15 128gb", [card], pais="BR", baixar=_baixar("<html>sem loja</html>"),
    )
    assert cands == []
    assert all("google." not in (c.get("url") or "").lower() for c in cands)
    matched = jds._jds_comparar_mesmo_produto("iphone 15 128gb", cands, pais="BR")
    assert matched == []
    item = _item(card, "<html></html>")
    assert item is None


def test_title_price_image_url_permanecem_no_mesmo_card():
    card = _card()
    item = _item(card, _html_amazon_dois_cards())
    assert item["titulo"] == card["title"]
    assert abs(item["preco_num"] - 4776.77) < 0.01
    assert item["foto"] == IMG
    assert ASIN_RETAIL in item["url"]
    assert item.get("source_serper") == card["source"]
    assert item.get("productId") == card["productId"]


def test_url_vizinha_nunca_associada_ao_preco_do_card():
    card = _card(
        source="Mercado Livre",
        price="R$ 3.199,00",
        imageUrl=IMG,
    )
    item = _item(card, _html_ml_com_amazon_vizinha())
    assert item is not None
    assert abs(item["preco_num"] - 3199.00) < 0.01
    assert MLB_OK in item["url"]
    assert "B0CHXRHSLC" not in item["url"]
    cands = jds._jds_extrair_candidatos(
        "iphone 15 128gb", [card], pais="BR", baixar=_baixar(_html_ml_com_amazon_vizinha()),
    )
    matched = jds._jds_comparar_mesmo_produto("iphone 15 128gb", cands, pais="BR")
    assert matched
    assert all(MLB_OK in (m.get("url") or "") for m in matched)
    assert all("B0CHXRHSLC" not in (m.get("url") or "") for m in matched)


def test_nao_fabrica_asin_a_partir_de_catalogid_google():
    html = """
    <html>prds=localAnnotatedOfferId:1,catalogid:871091021334399569,rds=PC_6027158597472037202|PROD_PC_6027158597472037202</html>
    """
    assert _item(_card(), html) is None
    assert jds._jds_resolver_url_anuncio_google_shopping(
        PONTE, "Amazon.com.br - Retail", pais="BR", html=html,
    ) == ""
