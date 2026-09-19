"""Cada resultado precisa nascer da mesma oferta (título+preço+imagem+vendedor+URL)."""
from __future__ import annotations

import jds_searchapi as sap


def test_same_listing_integrity():
    offer = {
        "title": "Sony DualSense PS5 Branco",
        "price": "R$ 404,27",
        "extracted_price": 404.27,
        "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "merchant": {"name": "Amazon.com.br"},
        "thumbnail": "https://m.media-amazon.com/images/I/dualsense.jpg",
    }
    campos = sap.campos_mesma_oferta(offer)
    assert campos["titulo"] == offer["title"]
    assert campos["extracted_price"] == offer["extracted_price"]
    assert campos["url"] == offer["link"]
    assert campos["vendedor"] == "Amazon.com.br"
    assert campos["imagem"] == offer["thumbnail"]
    item = sap.offer_para_item("controle ps5 sony branco", offer, "BR")
    assert item is not None
    assert sap.validar_integridade_listing(item)


def test_same_listing_integrity_rejeita_mistura():
    offer = {
        "title": "Sony DualSense PS5 Branco",
        "extracted_price": 404.27,
        "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "merchant": {"name": "Amazon.com.br"},
        "thumbnail": "https://m.media-amazon.com/images/I/dualsense.jpg",
    }
    item = sap.offer_para_item("controle ps5 sony branco", offer, "BR")
    assert item is not None
    misturado = dict(item)
    misturado["titulo"] = "iPhone 15 256GB"
    misturado["preco_num"] = 12.34
    misturado["original_url"] = "https://www.mercadolivre.com.br/MLB-999"
    misturado["listing_source"] = dict(item["listing_source"])
    assert sap.validar_integridade_listing(misturado) is False
