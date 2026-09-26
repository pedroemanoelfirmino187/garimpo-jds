"""Super Descontos: oferta real, cache do dia e matcher intacto. Sem SearchApi."""
from __future__ import annotations

import garimpo_jds as jds

TITULO_128 = "Apple iPhone 15 128GB 6GB Ram Tela 6.1"
TITULO_256 = "Apple iPhone 15 256GB"
URL_A = "https://www.amazon.com.br/dp/B0CQKLS4RP"
URL_B = "https://www.amazon.com.br/dp/B096SJTF8F"
URL_BUSCA = "https://www.amazon.com.br/s?k=iphone+15"
CONSULTA = "iPhone 15 128GB"


def _item(titulo=TITULO_128, preco=3999.0, url=URL_A, fonte="searchapi", **extra):
    base = {
        "titulo": titulo,
        "preco_num": preco,
        "preco": f"R$ {preco:.2f}",
        "url": url,
        "original_url": url,
        "plataforma": "amazon",
        "loja": "Amazon",
        "fonte": fonte,
        "foto": "https://m.media-amazon.com/images/I/iphone.jpg",
        "pais": "BR",
        "selo": "NOVO",
    }
    base.update(extra)
    return base


def test_a_oferta_real_e_aceita():
    assert jds.oferta_valida_super_desconto(_item(), CONSULTA, "BR") is True


def test_b_oferta_sem_preco_e_rejeitada():
    assert jds.oferta_valida_super_desconto(_item(preco=0), CONSULTA, "BR") is False


def test_c_url_generica_e_rejeitada():
    assert jds.oferta_valida_super_desconto(_item(url=URL_BUSCA), CONSULTA, "BR") is False


def test_d_produto_incompativel_e_rejeitado():
    assert jds.oferta_valida_super_desconto(_item(titulo=TITULO_256), CONSULTA, "BR") is False
    assert jds.oferta_valida_super_desconto(
        _item(titulo="Controle DualSense Edge PS5", url=URL_B),
        "controle dualsense ps5",
        "BR",
    ) is False


def test_catalogo_fixo_nao_entra():
    assert jds.oferta_valida_super_desconto(_item(fonte="catalogo"), CONSULTA, "BR") is False


def test_nao_inventa_percentual_sem_preco_anterior():
    item = _item()
    assert "%" not in jds._selo_super_desconto(item)
    com_de = _item(preco_de=5000.0)
    assert jds._selo_super_desconto(com_de).endswith("%")


def test_e_mesma_selecao_no_mesmo_dia(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_GARIMPO_DB", str(tmp_path / "cache.db"))
    monkeypatch.setattr(jds, "consultas_super_descontos", lambda dia=None, quantidade=3: [CONSULTA])
    chamadas = {"n": 0}

    def buscar(termo, pais="BR"):
        chamadas["n"] += 1
        return [_item(), _item(titulo=TITULO_256, url=URL_B, preco=4500)]

    primeira = jds._ofertas_super_descontos("BR", "2026-09-25", buscar)
    segunda = jds._ofertas_super_descontos("BR", "2026-09-25", buscar)
    assert chamadas["n"] == 1
    assert [p["url"] for p in primeira] == [p["url"] for p in segunda] == [URL_A]


def test_f_chave_muda_no_dia_seguinte():
    assert jds.chave_super_descontos("BR", "2026-09-25") == "super_descontos:BR:2026-09-25"
    assert jds.chave_super_descontos("BR", "2026-09-25") != jds.chave_super_descontos("BR", "2026-09-26")
    assert jds.consultas_super_descontos("2026-09-25") != jds.consultas_super_descontos("2026-09-26")
    assert jds.consultas_super_descontos("2026-09-25") == jds.consultas_super_descontos("2026-09-25")


def test_g_oferta_invalida_e_substituida(monkeypatch):
    monkeypatch.setattr(jds, "consultas_super_descontos", lambda dia=None, quantidade=3: [CONSULTA])
    pool = {
        CONSULTA: [
            _item(preco=0, url=URL_A),
            _item(url=URL_BUSCA, preco=1000),
            _item(url=URL_B, preco=4100),
        ]
    }
    escolhidas = jds._escolher_ofertas_super(pool, "BR", "2026-09-25")
    assert len(escolhidas) == 1
    assert escolhidas[0]["url"] == URL_B


def test_h_matcher_atual_continua_rejeitando_incompativel():
    assert jds._jds_anuncio_bate_consulta(CONSULTA, TITULO_128) is True
    assert jds._jds_anuncio_bate_consulta(CONSULTA, TITULO_256) is False
    assert jds._jds_anuncio_bate_consulta(
        "controle dualsense ps5",
        "Controle DualSense Edge PS5",
    ) is False


def test_cache_troca_card_invalido_sem_nova_busca(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_GARIMPO_DB", str(tmp_path / "cache.db"))
    chave = jds.chave_super_descontos("BR", "2026-09-25")
    jds._gravar_pacote_super(chave, {
        "chave": chave,
        "exibidas": [_item(preco=0, termo_busca=CONSULTA)],
        "pool": {CONSULTA: [_item(preco=0), _item(url=URL_B, preco=4100)]},
    })
    saida = jds._ofertas_super_descontos("BR", "2026-09-25", permitir_rede=False)
    assert [p["url"] for p in saida] == [URL_B]
