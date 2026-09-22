"""Laboratório local: cadeia SearchApi → confirmer. Sem APIs externas.

Não altera matcher, allowlist, Product Offers, confirmação ML nem regras de preço.
"""
from __future__ import annotations

import garimpo_jds as jds
import jds_searchapi as sap

Q_TV = "smart tv 50"
TITULO_TV = "Smart TV HQ QLED 50 Polegadas HQ-QLED50SM 4K Wi-Fi Bluetooth"
PRECO_TV = 1849.0
PDP_AMZ = "https://www.amazon.com.br/dp/B0GSH89DG4"
PDP_ML = (
    "https://www.mercadolivre.com.br/"
    "smart-tv-hq-qled-50-polegadas-4k-wifi/up/MLBU4780650807"
)
PDP_SHOPEE = "https://shopee.com.br/Smart-TV-HQ-QLED-50-Polegadas-i.1608031728.2309811123"

HTML_CAPTCHA_AMZ = (
    "<html><body>To discuss automated access to Amazon data please contact "
    "api-services-support@amazon.com. "
    '<form action="/errors_page/validateCaptcha"></form>'
    + ("x" * 200)
    + "</body></html>"
)
HTML_ML_ANTIBOT = (
    '<!DOCTYPE html><html lang="pt-BR" '
    'data-assets-prefix="https://http2.mlstatic.com/frontend-assets/'
    'suspicious-traffic-frontend/"><head><meta charSet="utf-8"/></head>'
    "<body>account-verification para continuar, acesse sua conta"
    + ("x" * 280)
    + "</body></html>"
)
HTML_404_GENERICO = (
    "<html><head><title>Page not found</title></head>"
    "<body>Sorry, we couldn't find that page."
    + ("x" * 200)
    + "</body></html>"
)


def _hash_id(val):
    texto = str(val or "").strip()
    return sap._hash_token(texto) if texto else ""


def evidencias_listing_source(item):
    origem = item.get("listing_source") if isinstance(item.get("listing_source"), dict) else {}
    campos = sorted(k for k, v in origem.items() if v not in (None, ""))
    return {
        "campos": campos,
        "titulo": origem.get("titulo") or "",
        "preco_num": origem.get("preco_num") or origem.get("extracted_price"),
        "url": origem.get("url") or "",
        "vendedor": origem.get("vendedor") or "",
        "tem_imagem": bool(str(origem.get("imagem") or "").strip()),
        "tem_product_token": bool(str(origem.get("product_token") or "").strip()),
        "tem_product_id": bool(str(origem.get("product_id") or "").strip()),
        "token_hash": _hash_id(origem.get("product_token")),
        "product_id_hash": _hash_id(origem.get("product_id")),
        "pdp_exata": jds._url_anuncio_exato(
            origem.get("url") or item.get("original_url") or "",
            item.get("plataforma") or "",
        ),
    }


def classificar_html(url, html, plat=""):
    html = html or ""
    if not html:
        return "html_vazio"
    if plat == "mercado_livre" and jds._html_e_verificacao_mercadolivre(html):
        return "anti_bot_ml"
    if jds._pagina_bloqueada(html):
        return "anti_bot_ou_captcha"
    if not jds._resposta_util_loja(url, html):
        return "pagina_inutil"
    if not jds._jds_titulo_html_anuncio(html):
        return "sem_titulo_na_pagina"
    if not jds._jds_precos_html_anuncio(html, pais="BR"):
        return "sem_preco_na_pagina"
    return "pagina_util"


def descarte(etapa, motivo, item=None, ofe=None):
    item = item if isinstance(item, dict) else {}
    ofe = ofe if isinstance(ofe, dict) else {}
    merchant = ofe.get("merchant") if isinstance(ofe.get("merchant"), dict) else {}
    origem = item.get("listing_source") if isinstance(item.get("listing_source"), dict) else {}
    loja = (
        item.get("vendedor_oferta")
        or item.get("loja")
        or merchant.get("name")
        or ofe.get("seller")
        or ""
    )
    titulo = item.get("titulo") or ofe.get("title") or ""
    preco = item.get("preco_num")
    if preco in (None, ""):
        preco = ofe.get("extracted_price") or ofe.get("price") or item.get("preco") or ""
    url = item.get("original_url") or ofe.get("link") or item.get("url") or ""
    token = origem.get("product_token") or ofe.get("product_token") or ""
    pid = origem.get("product_id") or ofe.get("product_id") or ""
    return {
        "etapa": etapa,
        "motivo": motivo,
        "loja": str(loja)[:80],
        "titulo": str(titulo)[:140],
        "preco": preco,
        "url": str(url)[:200],
        "tem_product_token": bool(str(token).strip()),
        "tem_product_id": bool(str(pid).strip()),
        "token_hash": _hash_id(token),
        "product_id_hash": _hash_id(pid),
    }


def _item_tv(plat, titulo=TITULO_TV, preco=PRECO_TV, url="", token="tok-tv", pid="pid-tv"):
    urls = {
        "amazon": PDP_AMZ,
        "mercado_livre": PDP_ML,
        "shopee": PDP_SHOPEE,
    }
    lojas = {
        "amazon": ("Amazon", "Amazon.com.br"),
        "mercado_livre": ("Mercado Livre", "mercadolivre.com.br"),
        "shopee": ("Shopee", "Shopee"),
    }
    url = url or urls[plat]
    loja, vend = lojas[plat]
    foto = "https://example.com/tv.jpg"
    return {
        "titulo": titulo,
        "preco_num": preco,
        "url": url,
        "original_url": url,
        "plataforma": plat,
        "loja": loja,
        "fonte": "searchapi",
        "pais": "BR",
        "consulta": Q_TV,
        "foto": foto,
        "imagem": foto,
        "listing_source": {
            "titulo": titulo,
            "preco_num": preco,
            "extracted_price": preco,
            "vendedor": vend,
            "url": url,
            "imagem": foto,
            "product_token": token,
            "product_id": pid,
            "consulta": Q_TV,
        },
    }


def _html_pdp_ok(titulo, preco_txt, ident):
    return (
        f"<html><head><meta property=\"og:title\" content=\"{titulo}\"></head>"
        f"<body><span id=\"productTitle\">{titulo}</span>"
        f"<span class=\"a-offscreen\">{preco_txt}</span>"
        f"<span class=\"andes-money-amount__fraction\">{preco_txt}</span>"
        f"{ident}"
        + ("x" * 80)
        + "</body></html>"
    )


def _html_shopee_sem_preco(titulo):
    return (
        f"<html><head><meta property=\"og:title\" content=\"{titulo}\"></head>"
        f"<body>itemid 2309811123 shop 1608031728 -i.1608031728.2309811123"
        + ("x" * 80)
        + "</body></html>"
    )


def _shopping_tv(n_lixo=12):
    """40 linhas: Amazon/ML/Shopee com token + Magalu/Google/sem título."""
    shopping = [
        {
            "position": 1,
            "title": TITULO_TV,
            "seller": "Amazon.com.br",
            "extracted_price": PRECO_TV,
            "link": PDP_AMZ,
            "product_token": "tok-amz-tv",
            "product_id": "gpid-amz",
            "thumbnail": "https://example.com/tv.jpg",
        },
        {
            "position": 2,
            "title": TITULO_TV,
            "seller": "Mercado Livre",
            "extracted_price": 1899.0,
            "link": PDP_ML,
            "product_token": "tok-ml-tv",
            "product_id": "gpid-ml",
            "thumbnail": "https://example.com/tv.jpg",
        },
        {
            "position": 3,
            "title": TITULO_TV,
            "seller": "Shopee",
            "extracted_price": 1799.0,
            "link": PDP_SHOPEE,
            "product_token": "tok-shp-tv",
            "product_id": "gpid-shp",
            "thumbnail": "https://example.com/tv.jpg",
        },
    ]
    for i in range(n_lixo):
        shopping.append(
            {
                "position": 10 + i,
                "title": f"{TITULO_TV} extra {i}",
                "seller": "Amazon.com.br" if i % 2 == 0 else "Magazine Luiza",
                "extracted_price": 1900 + i,
                "link": f"https://www.amazon.com.br/dp/B0GSH89D{i:02d}" if i % 2 == 0 else "https://www.magazineluiza.com.br/tv",
                "product_token": f"tok-extra-{i}",
                "product_id": f"gpid-extra-{i}",
                "thumbnail": "https://example.com/tv.jpg",
            }
        )
    shopping.append(
        {
            "position": 40,
            "title": TITULO_TV,
            "seller": "Google",
            "extracted_price": 1700,
            "link": "https://www.google.com/search?ibp=oshop&q=smart+tv+50",
            "product_token": "tok-google",
        }
    )
    return shopping


def _http_get_tv(shopping, offers_por_token):
    def _get(params):
        engine = params.get("engine")
        if engine == "google_shopping":
            return 200, {"shopping_results": shopping}, "{}"
        if engine == "google_product_offers":
            tok = params.get("product_token")
            return 200, offers_por_token.get(tok, {"offers": []}), "{}"
        if engine == "google_product_page":
            return 200, {}, "{}"
        return 0, None, "engine_nao_usado"

    return _get


def _offers_tv():
    return {
        "tok-amz-tv": {
            "offers": [
                {
                    "title": TITULO_TV,
                    "extracted_price": PRECO_TV,
                    "price": "R$ 1.849,00",
                    "link": PDP_AMZ,
                    "merchant": {"name": "Amazon.com.br"},
                    "thumbnail": "https://example.com/tv.jpg",
                    "product_token": "tok-amz-tv",
                    "product_id": "gpid-amz",
                }
            ]
        },
        "tok-ml-tv": {
            "offers": [
                {
                    "title": TITULO_TV,
                    "extracted_price": 1899.0,
                    "price": "R$ 1.899,00",
                    "link": PDP_ML,
                    "merchant": {"name": "Mercado Livre"},
                    "thumbnail": "https://example.com/tv.jpg",
                    "product_token": "tok-ml-tv",
                    "product_id": "gpid-ml",
                }
            ]
        },
        "tok-shp-tv": {
            "offers": [
                {
                    "title": TITULO_TV,
                    "extracted_price": 1799.0,
                    "price": "R$ 1.799,00",
                    "link": PDP_SHOPEE,
                    "merchant": {"name": "Shopee"},
                    "thumbnail": "https://example.com/tv.jpg",
                    "product_token": "tok-shp-tv",
                    "product_id": "gpid-shp",
                }
            ]
        },
    }


def _cadeia_searchapi(shopping, baixar, monkeypatch):
    monkeypatch.delenv("SEARCHAPI_MAX_PRODUCT_OFFERS", raising=False)
    monkeypatch.delenv("SEARCHAPI_MAX_REQUESTS_PER_QUERY", raising=False)
    monkeypatch.delenv("JDS_SKIP_PAGE_CONFIRM", raising=False)
    descartes = []
    orig_rejeitar = sap._rejeitar
    orig_anotar = jds._anotar_rejeicao_confirmer

    def _rej(motivos, amostras, motivo, ofe=None, item=None):
        descartes.append(descarte("offer_para_item", motivo, item=item, ofe=ofe))
        return orig_rejeitar(motivos, amostras, motivo, ofe=ofe, item=item)

    def _anot(motivos, amostras, motivo, item):
        descartes.append(descarte("confirmer", motivo, item=item))
        return orig_anotar(motivos, amostras, motivo, item)

    monkeypatch.setattr(sap, "_rejeitar", _rej)
    monkeypatch.setattr(jds, "_anotar_rejeicao_confirmer", _anot)
    ofertas, status = sap.buscar_ofertas_searchapi(
        Q_TV,
        pais="BR",
        usar_cache=False,
        http_get=_http_get_tv(shopping, _offers_tv()),
        baixar=baixar,
        confirmar=True,
    )
    diag = sap.ultimo_diag_searchapi()
    return ofertas, status, diag, descartes


def test_a_searchapi_amazon_captcha_trilha_smart_tv_50(monkeypatch):
    shopping = _shopping_tv()
    tabela = []

    cands = [sap.shopping_para_candidato(Q_TV, row, "BR") for row in shopping]
    cands = [c for c in cands if c]
    amz_cand = next(c for c in cands if c.get("link") == PDP_AMZ)
    tabela.append(("Amazon", "shopping", "OK", ""))
    tabela.append(("Amazon", "candidate", "OK", ""))
    tabela.append(("Amazon", "product_token", "OK" if amz_cand.get("product_token") else "FALHOU", ""))
    tabela.append(("Amazon", "product_id", "OK" if amz_cand.get("product_id") else "FALHOU", ""))

    escolhidos = sap.selecionar_candidatos_token(Q_TV, shopping, "BR")
    tabela.append(("Amazon", "po_fila", "OK" if any(c.get("link") == PDP_AMZ for c in escolhidos) else "FORA", "limite_3"))

    item = sap.offer_para_item(Q_TV, _offers_tv()["tok-amz-tv"]["offers"][0], pais="BR")
    assert item is not None
    ev = evidencias_listing_source(item)
    tabela.append(("Amazon", "parser", "OK", ""))
    assert ev["tem_product_token"] and ev["tem_product_id"] and ev["pdp_exata"]
    assert ev["preco_num"] == PRECO_TV
    assert item["original_url"] == PDP_AMZ

    grupo = jds._jds_comparar_mesmo_produto(Q_TV, [item], pais="BR")
    tabela.append(("Amazon", "matcher", "OK" if grupo else "REJEITADA", ""))
    assert grupo

    assert jds._html_e_captcha_amazon(HTML_CAPTCHA_AMZ) is True
    assert jds._resposta_util_loja(PDP_AMZ, HTML_CAPTCHA_AMZ) is False
    assert classificar_html(PDP_AMZ, HTML_CAPTCHA_AMZ, "amazon") == "anti_bot_ou_captcha"
    assert jds._searchapi_ml_antibot_estruturado_ok(
        item, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is False
    assert jds._searchapi_amazon_captcha_estruturado_ok(
        item, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is True

    motivos = sap._motivos_zerados()
    ok = jds._jds_confirmar_oferta_na_pagina(
        item, html=HTML_CAPTCHA_AMZ, motivos=motivos,
    )
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert ok["titulo"] == TITULO_TV
    assert ok["preco_num"] == PRECO_TV
    assert ok["original_url"] == PDP_AMZ
    tabela.append(("Amazon", "confirmer", "OK", "searchapi_structured_offer"))
    tabela.append(("Amazon", "html_captcha", "NAO_E_PDP", "pagina_bloqueada_detectada"))
    assert motivos.get("pagina_bloqueada", 0) == 0

    sem_id = sap.offer_para_item(Q_TV, _offers_tv()["tok-amz-tv"]["offers"][0], pais="BR")
    sem_id["listing_source"]["product_id"] = ""
    motivos2 = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        sem_id, html=HTML_CAPTCHA_AMZ, motivos=motivos2,
    ) is None
    assert motivos2["pagina_bloqueada"] >= 1
    tabela.append(("Amazon_sem_product_id", "confirmer", "REJEITADA", "pagina_bloqueada"))

    def _baixar_misto(url):
        if "amazon.com.br" in url:
            return HTML_CAPTCHA_AMZ
        if "mercadolivre" in url:
            return HTML_ML_ANTIBOT
        if "shopee" in url:
            return ""
        return ""

    ofertas_misto, status_misto, diag, descartes = _cadeia_searchapi(
        shopping, _baixar_misto, monkeypatch,
    )
    tabela.append(("pipeline", "shopping_results", str(diag["shopping_results"]), ""))
    tabela.append(("pipeline", "candidates", str(diag["candidates"]), ""))
    tabela.append(("pipeline", "tokens", str(diag["candidatos_com_product_token"]), ""))
    tabela.append(("pipeline", "product_offers", str(diag["product_offers_requests"]), "pdp_ja_no_shopping"))
    tabela.append(("pipeline", "offers_received", str(diag["offers_received"]), ""))
    assert diag["po_fila_candidatos"] == 3
    assert diag["offers_received"] == 0
    assert diag["product_offers_requests"] == 0
    plats = {p["plataforma"] for p in ofertas_misto}
    assert "amazon" in plats
    assert status_misto == "SEARCHAPI_SUCCESS"
    assert all(d["motivo"] != "aceita_captcha" for d in descartes)
    assert not any("tok-amz-tv" in str(d) for d in descartes)
    print("TRILHA")
    for loja, etapa, resultado, motivo in tabela:
        print(f"{loja} | {etapa} | {resultado} | {motivo}")


def test_a2_captcha_nao_e_html_valido_sem_provas():
    item = _item_tv("amazon", token="tok-amz-tv", pid="")
    motivos = sap._motivos_zerados()
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=HTML_CAPTCHA_AMZ, motivos=motivos)
    assert ok is None
    assert motivos["pagina_bloqueada"] >= 1
    assert jds._resposta_util_loja(PDP_AMZ, HTML_CAPTCHA_AMZ) is False


def test_b_searchapi_ml_antibot_so_nas_condicoes_estritas():
    item = _item_tv("mercado_livre")
    assert jds._html_e_verificacao_mercadolivre(HTML_ML_ANTIBOT) is True
    assert jds._searchapi_ml_antibot_estruturado_ok(
        item, PDP_ML, TITULO_TV, PRECO_TV, pais="BR",
    ) is True
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=HTML_ML_ANTIBOT)
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"

    sem_token = _item_tv("mercado_livre", token="")
    assert jds._searchapi_ml_antibot_estruturado_ok(
        sem_token, PDP_ML, TITULO_TV, PRECO_TV, pais="BR",
    ) is False
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        sem_token, html=HTML_ML_ANTIBOT, motivos=motivos,
    ) is None
    assert motivos["pagina_bloqueada"] >= 1

    amazon = _item_tv("amazon")
    assert jds._searchapi_ml_antibot_estruturado_ok(
        amazon, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is False


def test_c_searchapi_shopee_html_sem_preco():
    item = _item_tv("shopee", preco=1799.0)
    html = _html_shopee_sem_preco(TITULO_TV)
    assert "R$" not in html
    assert classificar_html(PDP_SHOPEE, html, "shopee") == "sem_preco_na_pagina"
    motivos = sap._motivos_zerados()
    ok = jds._jds_confirmar_oferta_na_pagina(item, html=html, motivos=motivos)
    # HTML útil + IDs na página + preço estruturado SearchApi → não descarta.
    assert ok is not None
    assert ok["confirmacao"] == "searchapi_structured_offer"
    assert ok["preco_num"] == 1799.0
    assert motivos.get("preco_nao_encontrado", 0) == 0

    sem_token = _item_tv("shopee", preco=1799.0, token="", pid="")
    motivos2 = sap._motivos_zerados()
    ok2 = jds._jds_confirmar_oferta_na_pagina(sem_token, html=html, motivos=motivos2)
    assert ok2 is None
    assert motivos2["preco_nao_encontrado"] >= 1
    d = descarte("confirmer", "preco_nao_encontrado", item=sem_token)
    assert d["tem_product_token"] is False
    assert d["motivo"] == "preco_nao_encontrado"


def test_d_oferta_searchapi_valida_chega_ao_final(monkeypatch):
    html_amz = _html_pdp_ok(TITULO_TV, "R$ 1.849,00", "B0GSH89DG4")
    html_ml = _html_pdp_ok(TITULO_TV, "R$ 1.899,00", "/up/MLBU4780650807")
    html_shp = _html_pdp_ok(TITULO_TV, "R$ 1.799,00", "1608031728 2309811123 -i.1608031728.2309811123")

    def _baixar(url):
        if "amazon.com.br" in url:
            return html_amz
        if "mercadolivre" in url:
            return html_ml
        if "shopee" in url:
            return html_shp
        return ""

    ofertas, status, diag, _descartes = _cadeia_searchapi(_shopping_tv(), _baixar, monkeypatch)
    assert status == "SEARCHAPI_SUCCESS"
    assert ofertas
    plats = {p["plataforma"] for p in ofertas}
    assert "amazon" in plats or "shopee" in plats or "mercado_livre" in plats
    assert all(p.get("confirmada_pagina") is True for p in ofertas)
    assert all(jds._url_anuncio_exato(p["original_url"], p["plataforma"]) for p in ofertas)
    etapas = diag.get("etapas") or {}
    assert diag["offers_confirmed"] >= 1
    assert (etapas.get("confirmer_entrada") or 0) >= 1
    assert (etapas.get("apos_matcher") or 0) >= 1


def test_e_identidade_continua_rejeitada():
    q = "iPhone 15 128GB"
    assert jds._jds_mesmo_produto("Apple iPhone 15 128GB", "Apple iPhone 15 256GB", q) is False
    assert jds._jds_anuncio_bate_consulta(q, "Apple iPhone 15 256GB") is False
    assert jds._jds_mesmo_produto("Console PlayStation 5", "Console PlayStation 5 Slim", "playstation 5") is False
    assert jds._jds_mesmo_produto(
        "Sony DualSense Wireless Controller White",
        "Sony DualSense Wireless Controller Black",
        "sony dualsense ps5",
    ) is False
    assert jds._jds_mesmo_produto(
        "Controle DualSense Sony PS5 original",
        "Controle DualSense compatível PS5",
        "controle dualsense ps5",
    ) is False
    assert jds._titulo_usado("Apple iPhone 15 128GB usado") is True
    assert jds._jds_mesmo_produto(
        "Apple iPhone 15 128GB",
        "Apple iPhone 15 128GB usado",
        "iphone 15 128gb",
    ) is False
    assert jds._titulo_shopping_ok("iphone 15 128gb", "Apple iPhone 15 128GB seminovo") is False


def test_f_coloracao_contrato_omitida_vs_conflito():
    q = "sony dualsense ps5"
    base = "Sony DualSense Wireless Controller for PS5"
    assert jds._jds_mesmo_produto(base, base + " White", q) is True
    assert jds._jds_mesmo_produto(base + " White", base, q) is True
    assert jds._jds_mesmo_produto(base + " White", base + " Black", q) is False


def test_g_hipotese_bloqueio_vs_pagina_inexistente():
    item = _item_tv("amazon")
    ev = evidencias_listing_source(item)
    fortes = {
        "titulo_searchapi": bool(ev["titulo"]),
        "preco_searchapi": ev["preco_num"] == PRECO_TV,
        "pdp_exata": ev["pdp_exata"],
        "tem_product_token": ev["tem_product_token"],
        "tem_product_id": ev["tem_product_id"],
        "asin_na_url": "B0GSH89DG4" in (ev["url"] or ""),
        "campos_listing_source": ev["campos"],
    }
    assert all(
        fortes[k] for k in (
            "titulo_searchapi", "preco_searchapi", "pdp_exata",
            "tem_product_token", "tem_product_id", "asin_na_url",
        )
    )

    cap = classificar_html(PDP_AMZ, HTML_CAPTCHA_AMZ, "amazon")
    vazio = classificar_html(PDP_AMZ, "", "amazon")
    inexistente = classificar_html(PDP_AMZ, HTML_404_GENERICO, "amazon")
    assert cap == "anti_bot_ou_captcha"
    assert vazio == "html_vazio"
    assert inexistente in {"pagina_inutil", "sem_titulo_na_pagina", "sem_preco_na_pagina"}
    assert cap != vazio
    assert cap != inexistente

    motivos_cap = sap._motivos_zerados()
    motivos_404 = sap._motivos_zerados()
    motivos_vazio = sap._motivos_zerados()
    ok_cap = jds._jds_confirmar_oferta_na_pagina(item, html=HTML_CAPTCHA_AMZ, motivos=motivos_cap)
    assert ok_cap is not None
    assert ok_cap["confirmacao"] == "searchapi_structured_offer"
    assert jds._jds_confirmar_oferta_na_pagina(item, html=HTML_404_GENERICO, motivos=motivos_404) is None
    assert jds._jds_confirmar_oferta_na_pagina(item, html="", motivos=motivos_vazio) is None
    assert motivos_vazio["html_vazio"] >= 1
    assert motivos_404.get("pagina_inutil", 0) >= 1 or motivos_404.get("pagina_bloqueada", 0) >= 1
    assert jds._searchapi_ml_antibot_estruturado_ok(
        item, PDP_AMZ, TITULO_TV, PRECO_TV, pais="BR",
    ) is False


def test_h_po_fila_limita_a_3_mesmo_com_15_tokens(monkeypatch):
    shopping = _shopping_tv(n_lixo=20)
    cands = [c for c in (sap.shopping_para_candidato(Q_TV, r, "BR") for r in shopping) if c]
    com_token = [c for c in cands if c.get("product_token")]
    assert len(com_token) >= 12
    escolhidos = sap.selecionar_candidatos_token(Q_TV, shopping, "BR")
    assert len(escolhidos) == 3
    plats = {c.get("plataforma") for c in escolhidos}
    assert "amazon" in plats

    def _baixar(_url):
        return HTML_CAPTCHA_AMZ if "amazon" in _url else ""

    _ofertas, _status, diag, _d = _cadeia_searchapi(shopping, _baixar, monkeypatch)
    assert diag["po_fila_candidatos"] == 3
    assert diag["po_fila_tokens_distintos"] == 3
    assert diag["searchapi_budget"] == 5
    # Shopping já traz PDP Amazon: PO da mesma loja é pulado (_loja_tem_pdp_exato).
    assert diag["candidates"] >= 12
    assert diag["candidatos_com_product_token"] >= 12


def test_i_cadeia_etapas_aparecem_no_diag(monkeypatch):
    def _baixar(url):
        if "amazon" in url:
            return HTML_CAPTCHA_AMZ
        if "mercadolivre" in url:
            return HTML_ML_ANTIBOT
        return _html_shopee_sem_preco(TITULO_TV)

    ofertas, status, diag, descartes = _cadeia_searchapi(_shopping_tv(), _baixar, monkeypatch)
    etapas = diag.get("etapas") or {}
    for chave in (
        "shopping_results", "candidates", "candidatos_com_product_token",
        "candidatos_com_product_id", "po_fila_candidatos", "po_fila_tokens_distintos",
        "offers_received", "apos_parser", "apos_matcher", "confirmer_entrada",
        "offers_confirmed",
    ):
        assert chave in etapas or chave in diag
    assert "shopping_start" in (diag.get("etapas_fluxo") or [])
    assert "final_result" in (diag.get("etapas_fluxo") or [])
    for d in descartes:
        assert set(d) >= {
            "etapa", "motivo", "loja", "titulo", "preco", "url",
            "tem_product_token", "tem_product_id",
        }
        assert "tok-amz-tv" not in str(d)
        assert len(d.get("token_hash") or "") <= 24
    # ML anti-bot e Amazon CAPTCHA com provas estruturadas sobrevivem; CAPTCHA não é PDP.
    plats = {p["plataforma"] for p in ofertas}
    assert "amazon" in plats
    assert status == "SEARCHAPI_SUCCESS"
    amz = next(p for p in ofertas if p["plataforma"] == "amazon")
    assert amz["confirmacao"] == "searchapi_structured_offer"
    assert amz["original_url"] == PDP_AMZ


def test_j_urls_google_e_busca_continuam_rejeitadas():
    gshop = (
        "https://www.google.com/search?ibp=oshop&q=smart+tv+50"
        "&prds=localAnnotatedOfferId:1,catalogid:1"
    )
    item = _item_tv("amazon", url=gshop)
    item["listing_source"]["url"] = gshop
    motivos = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        item, html=HTML_CAPTCHA_AMZ, motivos=motivos,
    ) is None
    assert motivos["url_nao_exata"] >= 1
    busca = "https://www.amazon.com.br/s?k=smart+tv+50"
    item2 = _item_tv("amazon", url=busca)
    item2["listing_source"]["url"] = busca
    motivos2 = sap._motivos_zerados()
    assert jds._jds_confirmar_oferta_na_pagina(
        item2, html=HTML_CAPTCHA_AMZ, motivos=motivos2,
    ) is None
    assert motivos2["url_nao_exata"] >= 1


def test_k_allowlist_br_inalterada():
    assert jds._lojas_do_pais("BR") == ("amazon", "mercado_livre", "shopee")


def test_l_garimpar_local_health_e_smart_tv_mock(monkeypatch):
    """Sem credenciais reais: /health ao vivo e /garimpar com fixture."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    saude = client.get("/health")
    assert saude.status_code == 200
    body = saude.json()
    assert body["ok"] is True
    assert body["chaves"].get("zenrows") is None
    assert body["chaves"].get("scrapingant") is None

    item = _item_tv("amazon")
    item["confirmada_pagina"] = True
    item["confirmacao"] = "searchapi_structured_offer"
    item["preco"] = "R$ 1.849,00"
    item["preco_numerico"] = PRECO_TV

    monkeypatch.setenv("JDS_API_TOKEN", "lab-token")
    monkeypatch.setattr(
        "api.main.buscar_ofertas_jds_shopping",
        lambda termo, usar_cache=True, pais="BR", limite=20: [item],
    )
    resp = client.get(
        "/garimpar",
        params={"q": "smart tv 50", "pais": "BR"},
        headers={"X-JDS-TOKEN": "lab-token"},
    )
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["ok"] is True
    assert dados["total"] >= 1
    assert dados["ofertas"][0]["plataforma"] == "amazon"
    assert "B0GSH89DG4" in (dados["ofertas"][0].get("original_url") or dados["ofertas"][0].get("url") or dados["ofertas"][0].get("link") or "")
