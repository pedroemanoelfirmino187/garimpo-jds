"""Etapa 1 do matcher: consulta → anúncio. Sem SearchApi real."""
from __future__ import annotations

import garimpo_jds as jds
import jds_searchapi as sap

ITEM_ID = "226994069950"
PDP = f"https://www.ebay.com/itm/{ITEM_ID}"
FOTO = "https://i.ebayimg.com/images/g/dualsense/s-l1600.jpg"


def _bate(query, titulo):
    return jds._jds_anuncio_bate_consulta(query, titulo)


def test_a_dualsense_generico_aceita_black_white():
    assert _bate(
        "Sony DualSense PS5 controller",
        "Sony DualSense Black/White Wireless Controller for PS5",
    ) is True


def test_b_dualsense_white_aceita_white():
    assert _bate(
        "Sony DualSense White PS5 controller",
        "Sony DualSense Wireless Controller White for PS5",
    ) is True


def test_c_dualsense_white_rejeita_black_white():
    assert _bate(
        "Sony DualSense White PS5 controller",
        "Sony DualSense Black/White Wireless Controller for PS5",
    ) is False


def test_d_dualsense_rejeita_edge():
    assert _bate(
        "Sony DualSense PS5 controller",
        "Sony DualSense Edge Wireless Controller",
    ) is False


def test_e_s24_aceita_s24():
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 256GB") is True


def test_f_s24_rejeita_s24_plus():
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24+ 256GB") is False
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 Plus 256GB") is False


def test_g_s24_rejeita_ultra():
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 Ultra 256GB") is False


def test_g2_s24_ultra_rejeita_s24_plus():
    assert _bate("Samsung Galaxy S24 Ultra 256GB", "Samsung Galaxy S24+ 256GB") is False


def test_h_s24_rejeita_fe():
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 FE 256GB") is False


def test_i_ideapad_3_aceita_ideapad_3():
    assert _bate("Lenovo IdeaPad 3 Ryzen 5", "Lenovo IdeaPad 3 Ryzen 5") is True


def test_j_ideapad_3_rejeita_slim_3():
    assert _bate("Lenovo IdeaPad 3 Ryzen 5", "Lenovo IdeaPad Slim 3 Ryzen 5") is False


def test_k_ideapad_slim_aceita_slim():
    assert _bate("Lenovo IdeaPad Slim 3 Ryzen 5", "Lenovo IdeaPad Slim 3 Ryzen 5") is True


def test_l_s24_rejeita_capacidade_diferente():
    assert _bate("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 128GB") is False


def test_edge_sem_ps5_aceita():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Wireless Controller",
    ) is True


def test_edge_com_ps5_explicito_aceita():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Wireless Controller for PS5",
    ) is True


def test_edge_white_sem_ps5_aceita():
    assert _bate(
        "Sony DualSense Edge White PS5 controller",
        "Sony DualSense Edge White Wireless Controller",
    ) is True


def test_edge_black_white_sem_cor_na_consulta_aceita():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Black/White Wireless Controller",
    ) is True


def test_edge_consulta_rejeita_dualsense_sem_edge():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Wireless Controller",
    ) is False


def test_edge_rejeita_xbox():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Wireless Controller for Xbox",
    ) is False


def test_edge_rejeita_ps4():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Wireless Controller for PS4",
    ) is False


def test_edge_rejeita_pc():
    assert _bate(
        "Sony DualSense Edge PS5 controller",
        "Sony DualSense Edge Wireless Controller for PC",
    ) is False


def test_plus_preservado_no_hard_norm_nao_no_v4():
    assert "plus" not in jds._jds_v4_norm("S24+")
    assert "plus" in jds._jds_hard_norm("S24+")
    assert "plus" in jds._jds_hard_norm("Galaxy S24+")


def test_ebay_product_nao_roda_para_black_white_quando_query_e_white():
    visto = []
    organic = [
        {
            "title": "Sony DualSense Black/White Wireless Controller for PS5",
            "price": "$35.00",
            "extracted_price": 35.0,
            "link": PDP,
            "item_id": ITEM_ID,
            "thumbnail": FOTO,
            "seller": "eBay",
        }
    ]

    def http_get(params):
        visto.append(params.get("engine"))
        if params.get("engine") == "ebay_search":
            return 200, {"organic_results": organic}, "{}"
        if params.get("engine") == "ebay_product":
            raise AssertionError("ebay_product nao deve rodar para Black/White")
        return 200, {}, "{}"

    ok, _req, norg, nprod = sap.completar_ebay_via_search(
        "Sony DualSense White PS5 controller",
        pais="US",
        usar_cache=False,
        http_get=http_get,
        baixar=lambda u: (_ for _ in ()).throw(AssertionError("sem HTML eBay")),
        confirmar=True,
    )
    assert norg == 1
    assert nprod == 0
    assert ok == []
    assert "ebay_product" not in visto
    assert "ebay_search" in visto
