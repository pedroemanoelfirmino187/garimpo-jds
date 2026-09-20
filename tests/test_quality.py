"""Suíte de qualidade do JDS Economiza.

Estes testes não usam chaves reais. Eles verificam as invariantes que não podem
ser quebradas mesmo quando uma fonte externa muda o formato dos resultados.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import garimpo_jds as jds
from api.main import app


SAME_PRODUCT = [
    ("Sony DualSense PS5 Branco", "Sony DualSense PS5 White"),
    ("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 256 GB"),
    ("Motorola Moto G84 256GB", "Motorola Moto G84 256 GB"),
    ("JBL Tune 520BT Preto", "JBL Tune 520BT Black"),
    ("Kingston SSD 1TB NV2", "SSD Kingston NV2 1 TB"),
]

DIFFERENT_PRODUCT = [
    ("Sony DualSense PS5", "Controle Compatível com PS5"),
    ("Sony DualSense PS5", "Sony DualSense PS4"),
    ("Nintendo Switch OLED 64GB", "Nintendo Switch Lite"),
    ("Samsung Galaxy S24 256GB", "Samsung Galaxy A55 256GB"),
    ("JBL Tune 520BT", "JBL Tune 510BT"),
    ("Motorola Moto G84 256GB", "Motorola Moto G54 256GB"),
    ("Sony PlayStation 5", "Sony PlayStation 5 Slim"),
    ("Apple iPhone 15 128GB", "Apple iPhone 15 256GB"),
    ("Apple iPhone 15", "Apple iPhone 15 Pro"),
    ("Apple iPhone 15 novo", "Apple iPhone 15 usado"),
]


@pytest.mark.parametrize("a,b", SAME_PRODUCT)
def test_matcher_aceita_mesmo_produto(a, b):
    assert jds._jds_mesmo_produto(a, b, a) is True


@pytest.mark.parametrize("a,b", DIFFERENT_PRODUCT)
def test_matcher_rejeita_produtos_diferentes(a, b):
    assert jds._jds_mesmo_produto(a, b, a) is False


@pytest.mark.parametrize(
    "query,candidate,expected",
    [
        ("controle ps5", "Controle Sem Fio Compatível com PS5", False),
        ("controle ps5 sony", "Controle Sem Fio Compatível com PS5", False),
        ("controle ps5 sony", "Sony DualSense PS5", True),
        ("controle ps5 sony branco", "Sony DualSense PS5 Preto", False),
        ("controle ps5 original", "Sony DualSense PS5 Original", True),
        ("controle ps5 original", "Controle Compatível PS5", False),
    ],
)
def test_regras_da_consulta(query, candidate, expected):
    # Comparação do candidato consigo mesmo, usando a consulta como requisito.
    assert jds._jds_mesmo_produto(candidate, candidate, query) is expected


@pytest.mark.parametrize(
    "a,b,query",
    [
        ("Sony DualSense PS5 Branco", "Sony DualSense PS5", "controle ps5 sony"),
        ("Apple iPhone 15 128GB Preto", "Apple iPhone 15 128GB", "iphone 15"),
    ],
)
def test_matcher_omite_cor_e_cor_explicita_sao_compativeis(a, b, query):
    assert jds._jds_mesmo_produto(a, b, query) is True


@pytest.mark.parametrize(
    "a,b,query",
    [
        ("Samsung Galaxy S24 256GB", "Samsung Galaxy S24 256GB 5G", "samsung galaxy s24"),
        ("Samsung Galaxy S24 256GB Preto", "Samsung Galaxy S24 256GB Branco", "samsung galaxy s24"),
        ("Sony DualSense PS5 Branco", "Sony DualSense PS5 Preto", "controle ps5 sony"),
        ("Apple iPhone 15 128GB", "Apple iPhone 15 128GB Seminovo", "iphone 15"),
        ("Sony DualSense PS5", "Controle Genérico para PS5", "controle ps5"),
    ],
)
def test_matcher_rejeita_atributo_explicito_sem_correspondencia(a, b, query):
    assert jds._jds_mesmo_produto(a, b, query) is False


def test_matcher_rejeita_compatível_mesmo_quando_a_consulta_e_generica():
    titulo = "Controle Sem Fio Compatível com PS5"
    assert jds._jds_mesmo_produto(titulo, titulo, "controle ps5") is False


def test_agrupamento_so_retorna_anuncios_compativeis_par_a_par():
    def oferta(titulo, plataforma, codigo):
        return {
            "titulo": titulo,
            "plataforma": plataforma,
            "url": {
                "amazon": f"https://www.amazon.com.br/dp/{codigo}",
                "mercado_livre": f"https://produto.mercadolivre.com.br/MLB-{codigo}",
                "shopee": f"https://shopee.com.br/DualSense-i.10.{codigo}",
            }[plataforma],
            "preco_num": 400.0,
            "foto": "https://img.example/dualsense.jpg",
            "fonte": "serper",
        }

    ofertas = [
        oferta("Sony DualSense PS5 Branco", "amazon", "B0CQKLS4RP"),
        oferta("Sony DualSense PS5", "mercado_livre", "123456"),
        oferta("Sony DualSense PS5 White", "shopee", "987654"),
    ]
    grupo = jds._jds_comparar_mesmo_produto("controle ps5 sony", ofertas)
    assert {item["plataforma"] for item in grupo} == {"amazon", "mercado_livre", "shopee"}
    assert all(
        jds._jds_mesmo_produto(a["titulo"], b["titulo"], "controle ps5 sony")
        for indice, a in enumerate(grupo) for b in grupo[indice + 1:]
    )
    cores_opostas = [
        oferta("Sony DualSense PS5 Branco", "amazon", "B0CQKLS4RP"),
        oferta("Sony DualSense PS5 Preto", "mercado_livre", "123456"),
    ]
    grupo_cor = jds._jds_comparar_mesmo_produto("controle ps5 sony", cores_opostas)
    assert len({item["plataforma"] for item in grupo_cor}) == 1


def test_card_nao_mistura_preco_imagem_titulo_url():
    item = {
        "titulo": "Sony DualSense PS5 Branco",
        "preco_numerico": 404.27,
        "preco_formatado": "R$ 404,27",
        "imagem": "https://img.example/dualsense-white.jpg",
        "link": "https://www.mercadolivre.com.br/MLB-123456",
        "link_afiliado": "https://www.mercadolivre.com.br/MLB-123456?matt_tool=x",
        "loja": "Mercado Livre",
    }
    assert item["preco_numerico"] is not None
    assert item["imagem"]
    assert item["link"]
    assert item["link_afiliado"]
    assert "MLB-123456" in item["link"]
    assert "MLB-123456" in item["link_afiliado"]
    assert "controle" not in item["titulo"].lower() or "dualsense" in item["titulo"].lower()


def test_url_generica_nao_e_anuncio_exato():
    generica = "https://lista.mercadolivre.com.br/controle-ps5"
    exata = "https://produto.mercadolivre.com.br/MLB-123456"
    assert jds._eh_pagina_compra(generica, "mercado_livre") is False
    assert jds._eh_pagina_compra(exata, "mercado_livre") is True


def test_serializacao_preserva_preco_e_link():
    item = {
        "titulo": "Sony DualSense PS5 Branco",
        "preco": "R$ 404,27",
        "preco_numerico": 404.27,
        "link": "https://produto.mercadolivre.com.br/MLB-123456",
        "imagem": "https://img.example/a.jpg",
        "plataforma": "mercadolivre",
    }
    out = jds.serializar_oferta_app(item, "BR")
    assert out.get("preco_numerico") == pytest.approx(404.27)
    assert out.get("imagem") == item["imagem"]
    assert "MLB-123456" in (out.get("link") or "")


def test_api_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "serper" in data["chaves"]
    assert "searchapi" in data["chaves"]
    assert "cache_sqlite" in data["chaves"]


def test_api_get_garimpar_sem_chamada_externa():
    fake = [
        {
            "titulo": "Sony DualSense PS5 Branco",
            "preco": "R$ 404,27",
            "preco_numerico": 404.27,
            "link": "https://produto.mercadolivre.com.br/MLB-123456",
            "imagem": "https://img.example/a.jpg",
            "plataforma": "mercadolivre",
            "loja": "Mercado Livre",
        }
    ]
    with patch("api.main._buscar_serper_pais", return_value=fake):
        client = TestClient(app)
        response = client.get("/garimpar", params={"q": "controle ps5 sony branco"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["total"] == 1
    assert data["ofertas"][0]["preco_numerico"] == pytest.approx(404.27)
    assert "MLB-123456" in data["ofertas"][0]["link"]


def test_api_rejeita_token_invalido():
    old = os.environ.get("JDS_API_TOKEN")
    os.environ["JDS_API_TOKEN"] = "token-de-teste"
    try:
        client = TestClient(app)
        sem_token = client.get("/garimpar", params={"q": "ps5"})
        assert sem_token.status_code == 401
        assert sem_token.json()["ok"] is False
        errado = client.get(
            "/garimpar",
            params={"q": "ps5"},
            headers={"X-JDS-TOKEN": "token-errado"},
        )
        assert errado.status_code == 401
        post_sem = client.post("/garimpar", json={"q": "ps5", "pais": "BR"})
        assert post_sem.status_code == 401
        saude = client.get("/health")
        assert saude.status_code == 200
        assert saude.json()["ok"] is True
    finally:
        if old is None:
            os.environ.pop("JDS_API_TOKEN", None)
        else:
            os.environ["JDS_API_TOKEN"] = old


def _oferta_amazon(titulo, preco, asin, imagem="https://m.media-amazon.com/images/I/xx.jpg"):
    return {
        "titulo": titulo,
        "preco_num": preco,
        "preco_numerico": preco,
        "url": f"https://www.amazon.com.br/dp/{asin}",
        "link": f"https://www.amazon.com.br/dp/{asin}",
        "imagem": imagem,
        "foto": imagem,
        "plataforma": "amazon",
        "loja": "Amazon",
        "fonte": "google",
        "pais": "BR",
    }


def test_descarta_preco_nao_confirmado_na_pagina():
    item = _oferta_amazon("Controle Dualsense Sem Fio Sony", 419.0, "B0FY6X2XXY")
    html = """
    <html><body>
    <span id="productTitle">Controle sem fio PlayStation DualSense Branco</span>
    <span class="a-offscreen">R$404,27</span>
    B0FY6X2XXY
    </body></html>
    """
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None


def test_mantem_preco_confirmado_na_mesma_url():
    item = _oferta_amazon("Fone de Ouvido Bluetooth JBL Tune 520BT", 228.38, "B0C6SPNVF5")
    html = """
    <html><body>
    <span id="productTitle">JBL Tune 520BT Sem Fio Branco</span>
    <span class="a-offscreen">R$228,38</span>
    B0C6SPNVF5
    </body></html>
    """
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=html)
    assert ok is not None
    assert ok["preco_num"] == pytest.approx(228.38)
    assert "B0C6SPNVF5" in ok["url"]
    assert ok["titulo"] == item["titulo"]
    assert ok["foto"] == item["foto"]


def test_descarta_128gb_quando_pagina_e_256gb_seminovo():
    item = _oferta_amazon(
        "Smartphone Samsung Galaxy S24 128GB 5G Cinza Galaxy AI",
        2779.0,
        "B0FTMSMR7X",
    )
    html = """
    <html><body>
    <span id="productTitle">Samsung Galaxy S24 256GB Preto (Seminovo)</span>
    <span class="a-offscreen">R$2.789,00</span>
    B0FTMSMR7X
    </body></html>
    """
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None


def test_pagina_bloqueada_nao_vira_busca_nem_catalogo():
    item = _oferta_amazon("Sony DualSense PS5", 404.27, "B0CQKLS4RP")
    html = "<html>account-verification acesse sua conta</html>"
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None
    vazia = jds._jds_confirmar_listings([item], baixar=lambda url: "")
    assert vazia == []


def test_nao_completa_loja_faltando():
    amazon = _oferta_amazon("Sony DualSense PS5 Branco", 404.27, "B0CQKLS4RP")
    grupo = jds._jds_comparar_mesmo_produto("controle ps5 sony branco", [amazon], "BR")
    assert len(grupo) == 1
    assert grupo[0]["plataforma"] == "amazon"


PRECOS_BR = [
    ("R$ 228,38", 228.38),
    ("R$ 202,00", 202.00),
    ("R$ 419,00", 419.00),
    ("R$ 404,27", 404.27),
    ("R$ 2.779,00", 2779.00),
    ("R$ 2.789,00", 2789.00),
]


@pytest.mark.parametrize("texto,esperado", PRECOS_BR)
def test_preco_br_virgula_decimal(texto, esperado):
    assert jds._preco_para_numero(texto, pais="BR") == pytest.approx(esperado)
    assert "\\" not in jds._jds_normalizar_texto_preco(texto)


@pytest.mark.parametrize("texto,esperado", PRECOS_BR)
def test_confirmer_le_preco_br_no_html(texto, esperado):
    html = f'<span class="a-offscreen">{texto}</span>'
    precos = jds._jds_precos_html_anuncio(html, pais="BR")
    assert esperado in precos


def test_confirmer_le_preco_br_sem_espaco_e_nbsp():
    html = (
        '<span class="a-offscreen">R$404,27</span>'
        '<span class="a-offscreen">R$\xa0228,38</span>'
        '<span class="a-offscreen">R\\$ 202,00</span>'
    )
    precos = jds._jds_precos_html_anuncio(html, pais="BR")
    assert 404.27 in precos
    assert 228.38 in precos
    assert 202.00 in precos
    assert all(isinstance(p, float) for p in precos)


def test_descarte_nao_vira_busca_nem_catalogo():
    item = _oferta_amazon("Controle Dualsense Sem Fio Sony", 419.0, "B0FY6X2XXY")
    html = """
    <html><body>
    <span id="productTitle">Controle sem fio PlayStation DualSense Branco</span>
    <span class="a-offscreen">R$ 404,27</span>
    B0FY6X2XXY
    </body></html>
    """
    assert jds._jds_confirmar_oferta_na_pagina(item, html=html) is None
    saida = jds._jds_confirmar_listings([item], baixar=lambda url: html)
    assert saida == []
    for p in saida:
        assert (p.get("fonte") or "") not in {"catalogo", "busca_loja"}
        assert not jds._url_e_busca_loja(p.get("url") or "")


def test_api_aceita_token_valido_sem_chamar_loja():
    old = os.environ.get("JDS_API_TOKEN")
    os.environ["JDS_API_TOKEN"] = "token-de-teste"
    fake = []
    try:
        with patch("api.main._buscar_serper_pais", return_value=fake):
            client = TestClient(app)
            response = client.get(
                "/garimpar",
                params={"q": "produto-inexistente"},
                headers={"X-JDS-TOKEN": "token-de-teste"},
            )
            post = client.post(
                "/garimpar",
                json={"q": "produto-inexistente", "pais": "BR"},
                headers={"Authorization": "Bearer token-de-teste"},
            )
        assert response.status_code == 200
        assert response.json()["ok"] is False
        assert response.json()["status"] == "empty"
        assert post.status_code == 200
        assert post.json()["status"] == "empty"
    finally:
        if old is None:
            os.environ.pop("JDS_API_TOKEN", None)
        else:
            os.environ["JDS_API_TOKEN"] = old
