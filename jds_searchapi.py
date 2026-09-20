"""SearchApi.io (Google Shopping + Product Offers) para o JDS Economiza.

Não imprime SEARCHAPI_API_KEY. Não inventa product_token nem IDs de loja.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse

import requests

import garimpo_jds as jds

API = "https://www.searchapi.io/api/v1/search"
ACCOUNT_API = "https://www.searchapi.io/api/v1/me"

_LOCK = threading.Lock()
_MEM = {}
_ULTIMO_DIAG = {}
_HTTP_GET = None  # testes: (params) -> (http, dict|None, bruto)


MOTIVOS_REJEICAO = (
    "url_google",
    "url_busca",
    "loja_fora",
    "url_nao_exata",
    "titulo_rejeitado",
    "matcher_rejeitou",
    "modelo_divergente",
    "variante_divergente",
    "condicao_divergente",
    "html_vazio",
    "pagina_bloqueada",
    "pagina_inutil",
    "id_nao_encontrado",
    "variante_nao_bate",
    "condicao_nao_bate",
    "preco_nao_encontrado",
    "preco_nao_confere",
    "preco_divergente",
    "confirmer_rejeitou",
)


def _motivos_zerados():
    return {k: 0 for k in MOTIVOS_REJEICAO}


def _inc(motivos, chave):
    if motivos is None:
        return
    if chave not in motivos:
        motivos[chave] = 0
    motivos[chave] += 1


def _amostra_rejeicao(ofe=None, item=None, motivo=""):
    ofe = ofe if isinstance(ofe, dict) else {}
    item = item if isinstance(item, dict) else {}
    merchant = ofe.get("merchant") if isinstance(ofe.get("merchant"), dict) else {}
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
    original = (
        item.get("original_url")
        or ofe.get("link")
        or item.get("url")
        or ""
    )
    return {
        "loja": str(loja)[:80],
        "titulo": str(titulo)[:140],
        "preco": preco,
        "original_url": str(original)[:200],
        "motivo": motivo,
    }


def _rejeitar(motivos, amostras, motivo, ofe=None, item=None):
    _inc(motivos, motivo)
    if amostras is None:
        return
    amostras.append(_amostra_rejeicao(ofe=ofe, item=item, motivo=motivo))


def ultimo_diag_searchapi():
    return dict(_ULTIMO_DIAG)


def _chave_searchapi():
    chaves = jds._chaves_env("SEARCHAPI_API_KEY", "SEARCHAPI_KEY")
    return chaves[0] if chaves else ""


def _cfg_pais(pais="BR"):
    if jds._normalizar_pais(pais) == "US":
        return {
            "pais": "US",
            "gl": "us",
            "hl": "en",
            "currency": "USD",
            "symbol": "$",
        }
    return {
        "pais": "BR",
        "gl": "br",
        "hl": "pt",
        "currency": "BRL",
        "symbol": "R$",
    }


def _max_product_offers():
    try:
        n = int((os.environ.get("SEARCHAPI_MAX_PRODUCT_OFFERS") or "3").strip() or 3)
    except ValueError:
        n = 3
    return max(1, min(n, 5))


def _ttl_shopping():
    try:
        return max(30, int((os.environ.get("SEARCHAPI_CACHE_TTL") or "900").strip() or 900))
    except ValueError:
        return 900


def _ttl_offers():
    try:
        return max(30, int((os.environ.get("SEARCHAPI_OFFERS_CACHE_TTL") or "900").strip() or 900))
    except ValueError:
        return 900


def _consulta_norm(termo):
    return jds._consulta_serper_shopping(termo)


def chave_cache_searchapi(termo, pais="BR"):
    cfg = _cfg_pais(pais)
    q = _consulta_norm(termo).lower()
    return f"{cfg['pais']}:{cfg['hl']}:{q}"


def _hash_token(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:24]


def _conectar():
    caminho = jds._arquivo_cache_sqlite()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho), timeout=12)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS searchapi_cache (
            chave TEXT PRIMARY KEY,
            json TEXT NOT NULL,
            criado_em REAL NOT NULL
        )
        """
    )
    return conn


def _ler_cache(chave, ttl):
    agora = time.time()
    with _LOCK:
        mem = _MEM.get(chave)
        if mem and agora - float(mem.get("quando") or 0) <= ttl:
            return json.loads(json.dumps(mem.get("dados")))
        if mem:
            _MEM.pop(chave, None)
    try:
        with _LOCK:
            conn = _conectar()
            try:
                row = conn.execute(
                    "SELECT json, criado_em FROM searchapi_cache WHERE chave = ?",
                    (chave,),
                ).fetchone()
            finally:
                conn.close()
        if not row:
            return None
        blob, quando = row
        if agora - float(quando or 0) > ttl:
            return None
        dados = json.loads(blob)
        with _LOCK:
            _MEM[chave] = {"quando": float(quando), "dados": dados}
        return json.loads(json.dumps(dados))
    except Exception:
        return None


def _gravar_cache(chave, dados):
    agora = time.time()
    with _LOCK:
        _MEM[chave] = {"quando": agora, "dados": dados}
    try:
        payload = json.dumps(dados, ensure_ascii=False)
        with _LOCK:
            conn = _conectar()
            try:
                conn.execute(
                    """
                    INSERT INTO searchapi_cache (chave, json, criado_em)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chave) DO UPDATE SET
                        json = excluded.json,
                        criado_em = excluded.criado_em
                    """,
                    (chave, payload, agora),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


def searchapi_request(params, http_get=None):
    """GET SearchApi. params nunca devem incluir a chave em logs."""
    http_get = http_get or _HTTP_GET
    if callable(http_get):
        http, dados, bruto = http_get(dict(params))
        return int(http or 0), dados if isinstance(dados, dict) else None, bruto or ""
    chave = _chave_searchapi()
    if not chave:
        return 0, None, "sem_chave"
    envio = {k: v for k, v in (params or {}).items() if k not in {"api_key", "key"}}
    try:
        resp = requests.get(
            API,
            params=envio,
            headers={"Authorization": f"Bearer {chave}", "Accept": "application/json"},
            timeout=40,
        )
        bruto = resp.text or ""
        try:
            dados = resp.json() if bruto else {}
        except Exception:
            dados = None
        return resp.status_code, dados if isinstance(dados, dict) else None, bruto
    except Exception as exc:
        return 0, None, str(exc)[:180]


def consultar_uso_searchapi():
    """Account API — só diagnóstico. Não chamar no /garimpar."""
    chave = _chave_searchapi()
    if not chave:
        return {"ok": False, "configurado": False}
    try:
        resp = requests.get(
            ACCOUNT_API,
            headers={"Authorization": f"Bearer {chave}", "Accept": "application/json"},
            timeout=20,
        )
        dados = {}
        try:
            dados = resp.json() if resp.text else {}
        except Exception:
            dados = {}
        if not isinstance(dados, dict):
            dados = {}
        seguro = {
            k: dados.get(k)
            for k in (
                "plan",
                "credits",
                "credits_used",
                "credits_remaining",
                "rate_limit",
                "status",
            )
            if k in dados
        }
        return {"ok": resp.status_code < 400, "http": resp.status_code, "uso": seguro}
    except Exception as exc:
        return {"ok": False, "http": 0, "erro": str(exc)[:80]}


def campos_mesma_oferta(offer):
    """Lê título/preço/vendedor/URL/imagem da MESMA entrada offers[]."""
    if not isinstance(offer, dict):
        return None
    merchant = offer.get("merchant") if isinstance(offer.get("merchant"), dict) else {}
    titulo = str(offer.get("title") or "").strip()
    vendedor = str(merchant.get("name") or offer.get("seller") or "").strip()
    link = str(offer.get("link") or "").strip()
    preco_txt = str(offer.get("price") or offer.get("total_price") or "").strip()
    preco = offer.get("extracted_price")
    if preco in (None, "", 0, 0.0):
        preco = offer.get("extracted_total_price")
    imagem = ""
    for k in ("thumbnail", "image", "product_image"):
        v = offer.get(k)
        if isinstance(v, str) and v.strip():
            imagem = v.strip()
            break
    return {
        "titulo": titulo,
        "preco_txt": preco_txt,
        "extracted_price": preco,
        "vendedor": vendedor,
        "url": link,
        "imagem": imagem,
        "position": offer.get("position"),
    }


def validar_integridade_listing(item):
    origem = (item or {}).get("listing_source")
    if not isinstance(item, dict) or not isinstance(origem, dict):
        return False
    try:
        preco = float(item.get("preco_num") or 0)
        origem_preco = float(origem.get("preco_num") or origem.get("extracted_price") or 0)
    except (TypeError, ValueError):
        return False
    url_orig = (item.get("original_url") or "").split("?")[0]
    url_src = (origem.get("url") or "").split("?")[0]
    if (item.get("titulo") or "") != (origem.get("titulo") or ""):
        return False
    if abs(preco - origem_preco) > 0.009:
        return False
    if url_orig != url_src:
        return False
    vend_item = (item.get("vendedor_oferta") or item.get("loja") or "").strip().lower()
    vend_src = (origem.get("vendedor") or "").strip().lower()
    if vend_src and vend_item and vend_src not in vend_item and vend_item not in vend_src:
        # loja canônica (Amazon) vs merchant (Amazon.com.br) ainda bate pelo host
        if "amazon" not in vend_src + vend_item:
            return False
    img_src = (origem.get("imagem") or "").strip()
    if img_src:
        if (item.get("foto") or item.get("imagem") or "").strip() != img_src:
            return False
    return True


def _plat_de_oferta(vendedor, url, pais="BR"):
    plat = jds._plataforma_loja(url) or jds._loja_do_texto(vendedor)
    if plat and plat in jds._lojas_do_pais(pais):
        return plat
    return plat or ""


def shopping_para_candidato(query, bruto, pais="BR"):
    if not isinstance(bruto, dict):
        return None
    titulo = str(bruto.get("title") or "").strip()
    token = bruto.get("product_token")
    if not titulo:
        return None
    if token in (None, ""):
        token = None
    elif not isinstance(token, str):
        token = None
    if not jds._titulo_shopping_ok(query, titulo):
        return None
    if not jds._jds_mesmo_produto(titulo, titulo, query):
        return None
    seller = str(bruto.get("seller") or "").strip()
    link = str(bruto.get("link") or "").strip()
    plat = _plat_de_oferta(seller, link, pais=pais)
    if plat and plat not in jds._lojas_do_pais(pais):
        return None
    if plat and not jds._source_loja_oficial(seller or plat, pais=pais) and seller:
        if plat not in jds._lojas_do_pais(pais):
            return None
    preco = bruto.get("extracted_price")
    try:
        preco_n = float(preco) if preco not in (None, "") else 0.0
    except (TypeError, ValueError):
        preco_n = jds._preco_para_numero(str(bruto.get("price") or ""), pais=pais)
    return {
        "titulo": titulo,
        "seller": seller,
        "link": link,
        "product_token": token,
        "plataforma": plat,
        "preco_num": preco_n,
        "position": bruto.get("position"),
        "imagem": str(bruto.get("thumbnail") or bruto.get("image") or "").strip(),
    }


def selecionar_candidatos_token(query, shopping, pais="BR", limite=None):
    limite = limite if limite is not None else _max_product_offers()
    scored = []
    for bruto in shopping or []:
        cand = shopping_para_candidato(query, bruto, pais=pais)
        if not cand or not cand.get("product_token"):
            continue
        item_ref = {
            "titulo": cand["titulo"],
            "url": cand.get("link") or "",
            "plataforma": cand.get("plataforma") or "",
            "preco_num": cand.get("preco_num") or 0,
        }
        score = jds._jds_pontuar_referencia(query, item_ref)
        if cand.get("plataforma") in jds._lojas_do_pais(pais):
            score += 25
        scored.append((score, cand))
    scored.sort(key=lambda x: -x[0])
    escolhidos = []
    vistos = set()
    plats = set()

    def _encaixar(cand):
        tok = cand.get("product_token")
        if not tok or tok in vistos:
            return False
        plat = cand.get("plataforma")
        escolhidos.append(cand)
        vistos.add(tok)
        if plat:
            plats.add(plat)
        return True

    # US: reserva 1 vaga do limite atual para eBay válido, sem extra Product Offers.
    if jds._normalizar_pais(pais) == "US" and limite >= 1:
        for _score, cand in scored:
            if cand.get("plataforma") == "ebay" and _encaixar(cand):
                break

    for score, cand in scored:
        tok = cand["product_token"]
        if tok in vistos:
            continue
        plat = cand.get("plataforma")
        if plat and plat in plats:
            continue
        _encaixar(cand)
        if len(escolhidos) >= limite:
            return escolhidos
    for score, cand in scored:
        if cand["product_token"] in vistos:
            continue
        escolhidos.append(cand)
        vistos.add(cand["product_token"])
        if len(escolhidos) >= limite:
            break
    return escolhidos


def offer_para_item(query, offer, pais="BR", motivos=None, amostras=None):
    campos = campos_mesma_oferta(offer)
    if not campos:
        _rejeitar(motivos, amostras, "titulo_rejeitado", ofe=offer)
        return None
    titulo = campos["titulo"]
    link = campos["url"]
    vendedor = campos["vendedor"]
    if not titulo:
        _rejeitar(motivos, amostras, "titulo_rejeitado", ofe=offer)
        return None
    if not link:
        _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer)
        return None
    if jds._url_e_google(link):
        _rejeitar(motivos, amostras, "url_google", ofe=offer)
        return None
    if jds._url_e_busca_loja(link):
        _rejeitar(motivos, amostras, "url_busca", ofe=offer)
        return None
    plat = _plat_de_oferta(vendedor, link, pais=pais)
    if plat not in jds._lojas_do_pais(pais):
        _rejeitar(motivos, amostras, "loja_fora", ofe=offer)
        return None
    if not jds._url_anuncio_exato(link, plat):
        _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer)
        return None
    if pais == "US" and plat == "amazon" and not jds._host_amazon_eua(link):
        _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer)
        return None
    if plat == "ebay":
        if pais != "US":
            _rejeitar(motivos, amostras, "loja_fora", ofe=offer)
            return None
        if not jds._id_ebay(link) or "/sch/" in link.lower() or "ebay.us/" in link.lower():
            _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer)
            return None
    if not jds._titulo_shopping_ok(query, titulo):
        _rejeitar(motivos, amostras, "titulo_rejeitado", ofe=offer)
        return None
    if not jds._jds_mesmo_produto(titulo, titulo, query):
        _rejeitar(motivos, amostras, "matcher_rejeitou", ofe=offer)
        return None
    preco = campos["extracted_price"]
    try:
        preco_n = float(preco)
    except (TypeError, ValueError):
        preco_n = jds._preco_para_numero(campos["preco_txt"], pais=pais)
    if preco_n <= 0:
        _rejeitar(motivos, amostras, "preco_nao_encontrado", ofe=offer)
        return None
    foto = campos["imagem"]
    item = jds._item_google(
        query, titulo, preco_n, link, foto, plat, origem="searchapi", pais=pais,
    )
    if not item:
        _rejeitar(motivos, amostras, "titulo_rejeitado", ofe=offer)
        return None
    original = jds._url_canonica_loja(link, plat, pais=pais)
    if jds._url_e_google(original) or jds._url_e_busca_loja(original) or not jds._url_anuncio_exato(original, plat):
        _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer)
        return None
    item["original_url"] = original
    item["pais"] = pais
    item["preco"] = jds._formatar_preco(preco_n, pais=pais)
    item["preco_num"] = preco_n
    item["vendedor_oferta"] = vendedor
    item["loja"] = item.get("loja") or jds._nome_loja(plat)
    item["fonte"] = "searchapi"
    item["listing_source"] = {
        "titulo": titulo,
        "preco_num": preco_n,
        "extracted_price": preco_n,
        "vendedor": vendedor,
        "url": original,
        "imagem": foto,
    }
    if foto:
        item["foto"] = foto
        item["imagem"] = foto
    if not validar_integridade_listing(item):
        _rejeitar(motivos, amostras, "url_nao_exata", ofe=offer, item=item)
        return None
    return item


def organic_ebay_para_offer(bruto):
    """Converte organic_results do ebay_search no formato de offer_para_item.

    Não inventa ITEM_ID. Exige PDP /itm/{id}. Se o JSON trouxer item_id
    diferente da URL, descarta (não substitui o ID).
    """
    if not isinstance(bruto, dict):
        return None
    url = str(bruto.get("link") or bruto.get("url") or bruto.get("product_link") or "").strip()
    if not jds._url_anuncio_exato(url, "ebay"):
        return None
    eid = jds._id_ebay(url)
    if not eid:
        return None
    json_id = str(bruto.get("item_id") or bruto.get("itemId") or "").strip()
    if json_id and json_id.isdigit() and json_id != eid:
        return None
    pdp = jds._pdp_ebay(eid)
    if not pdp:
        return None
    titulo = str(bruto.get("title") or bruto.get("name") or "").strip()
    if not titulo:
        return None
    preco = bruto.get("extracted_price")
    vendedor = str(
        bruto.get("seller") or bruto.get("store") or bruto.get("shop") or "eBay"
    ).strip() or "eBay"
    imagem = ""
    for k in ("thumbnail", "image", "product_image"):
        v = bruto.get(k)
        if isinstance(v, str) and v.strip():
            imagem = v.strip()
            break
    return {
        "title": titulo,
        "price": bruto.get("price") or preco,
        "extracted_price": preco,
        "link": pdp,
        "merchant": {"name": vendedor},
        "thumbnail": imagem,
    }


def _tem_ebay_confirmado(itens):
    for p in itens or []:
        if not isinstance(p, dict):
            continue
        if p.get("plataforma") != "ebay":
            continue
        orig = p.get("original_url") or p.get("url") or ""
        if jds._id_ebay(orig) and jds._url_anuncio_exato(orig, "ebay"):
            return True
    return False


def _organic_ebay_search(termo, pais="US", usar_cache=True, http_get=None):
    chave = "ebay:" + chave_cache_searchapi(termo, pais)
    if usar_cache:
        cached = _ler_cache(chave, _ttl_shopping())
        if isinstance(cached, dict) and isinstance(cached.get("organic_results"), list):
            return cached.get("organic_results"), 0
    http, dados, _bruto = searchapi_request(
        {
            "engine": "ebay_search",
            "q": termo,
            "ebay_domain": "ebay.com",
            "country": "us",
        },
        http_get=http_get,
    )
    if http >= 400 or not isinstance(dados, dict):
        return [], 1
    organic = dados.get("organic_results") or []
    if not isinstance(organic, list):
        organic = []
    if usar_cache:
        _gravar_cache(chave, {"organic_results": organic})
    return organic, 1


def completar_ebay_via_search(
    query,
    pais="US",
    usar_cache=True,
    http_get=None,
    baixar=None,
    confirmar=True,
    motivos=None,
    amostras=None,
):
    """US: ebay_search → offer_para_item → matcher existente → confirmer → EPN."""
    pais = jds._normalizar_pais(pais)
    if pais != "US":
        return [], 0, 0
    organic, req = _organic_ebay_search(
        query, pais=pais, usar_cache=usar_cache, http_get=http_get,
    )
    itens = []
    rejeitadas = 0
    for bruto in organic:
        ofe = organic_ebay_para_offer(bruto)
        if not ofe:
            rejeitadas += 1
            continue
        item = offer_para_item(query, ofe, pais=pais, motivos=motivos, amostras=amostras)
        if not item:
            rejeitadas += 1
            continue
        itens.append(item)
    grupo = jds._jds_comparar_mesmo_produto(query, itens, pais=pais)
    if confirmar:
        grupo = jds._jds_confirmar_listings(
            grupo, pais=pais, baixar=baixar, motivos=motivos, amostras=amostras,
        )
    else:
        grupo = jds._ordenar_entrega_menor_preco(
            jds._carimbar_lista_afiliado(grupo, pais=pais)
        )
    confirmados = []
    for p in grupo or []:
        if p.get("plataforma") != "ebay":
            continue
        orig = p.get("original_url") or (p.get("listing_source") or {}).get("url")
        if not jds._url_anuncio_exato(orig or "", "ebay"):
            continue
        if p.get("fonte") == "searchapi" and not validar_integridade_listing(
            {**p, "original_url": orig}
        ):
            continue
        p["original_url"] = orig or p.get("original_url")
        p["affiliate_url"] = p.get("url") or p.get("link_afiliado")
        confirmados.append(p)
    return confirmados, req, len(organic)


def _diag(**kwargs):
    _ULTIMO_DIAG.clear()
    _ULTIMO_DIAG.update(kwargs)


def buscar_ofertas_searchapi(
    termo,
    pais="BR",
    limite=20,
    usar_cache=True,
    http_get=None,
    baixar=None,
    confirmar=True,
):
    t = _consulta_norm(termo)
    pais = jds._normalizar_pais(pais)
    cfg = _cfg_pais(pais)
    if not t:
        _diag(status="SEARCHAPI_EMPTY", q=t, pais=pais)
        return [], "SEARCHAPI_EMPTY"

    chave_shop = "shop:" + chave_cache_searchapi(t, pais)
    cache_hit = False
    shopping = None
    http = 0
    if usar_cache:
        cached = _ler_cache(chave_shop, _ttl_shopping())
        if isinstance(cached, dict) and isinstance(cached.get("shopping_results"), list):
            shopping = cached.get("shopping_results")
            cache_hit = True
            http = 200

    if shopping is None:
        if not _chave_searchapi() and not callable(http_get or _HTTP_GET):
            _diag(status="SEARCHAPI_ERROR", q=t, pais=pais, erro="sem_chave", cache_hit=False)
            return [], "SEARCHAPI_ERROR"
        http, dados, bruto = searchapi_request(
            {"engine": "google_shopping", "q": t, "gl": cfg["gl"], "hl": cfg["hl"]},
            http_get=http_get,
        )
        if http >= 400 or not isinstance(dados, dict):
            _diag(
                status="SEARCHAPI_ERROR",
                q=t,
                pais=pais,
                http=http,
                erro=(dados or {}).get("error") if isinstance(dados, dict) else (bruto or "")[:80],
                cache_hit=False,
                gl=cfg["gl"],
                hl=cfg["hl"],
            )
            return [], "SEARCHAPI_ERROR"
        shopping = dados.get("shopping_results") or []
        if not isinstance(shopping, list):
            shopping = []
        if usar_cache:
            _gravar_cache(chave_shop, {"shopping_results": shopping})

    candidatos = []
    for bruto in shopping:
        cand = shopping_para_candidato(t, bruto, pais=pais)
        if cand:
            candidatos.append(cand)

    tokens = selecionar_candidatos_token(t, shopping, pais=pais, limite=_max_product_offers())
    offers_req = 0
    offers_recv = 0
    rejeitadas = 0
    itens = []
    motivos = _motivos_zerados()
    amostras = []

    # Shopping já com PDP na mesma linha (title+price+seller+link) economiza Product Offers.
    for cand in candidatos:
        link = cand.get("link") or ""
        plat = cand.get("plataforma")
        if not plat or not jds._url_anuncio_exato(link, plat):
            continue
        fake_offer = {
            "title": cand["titulo"],
            "price": cand.get("preco_num"),
            "extracted_price": cand.get("preco_num"),
            "link": link,
            "merchant": {"name": cand.get("seller") or plat},
            "thumbnail": cand.get("imagem") or "",
        }
        item = offer_para_item(t, fake_offer, pais=pais, motivos=motivos, amostras=amostras)
        if item:
            itens.append(item)

    plats_ok = {p.get("plataforma") for p in itens}
    for cand in tokens:
        if len(plats_ok) >= len(jds._lojas_do_pais(pais)) and len(itens) >= 1:
            break
        tok = cand.get("product_token")
        if not tok:
            continue
        chave_off = f"off:{cfg['pais']}:{cfg['hl']}:{_hash_token(tok)}"
        payload = None
        if usar_cache:
            payload = _ler_cache(chave_off, _ttl_offers())
        if not isinstance(payload, dict):
            offers_req += 1
            oh, odados, obruto = searchapi_request(
                {
                    "engine": "google_product_offers",
                    "product_token": tok,
                    "gl": cfg["gl"],
                    "hl": cfg["hl"],
                    "link": "resolved",
                },
                http_get=http_get,
            )
            if oh >= 400 or not isinstance(odados, dict):
                continue
            payload = odados
            if usar_cache:
                _gravar_cache(chave_off, payload)
        offers = payload.get("offers") or []
        if not isinstance(offers, list):
            continue
        offers_recv += len(offers)
        for ofe in offers:
            item = offer_para_item(t, ofe, pais=pais, motivos=motivos, amostras=amostras)
            if not item:
                rejeitadas += 1
                continue
            itens.append(item)

    apos_parser = len(itens)
    grupo = jds._jds_comparar_mesmo_produto(t, itens, pais=pais)
    apos_matcher = len(grupo or [])
    confirmer_entrada = apos_matcher if confirmar else 0
    if confirmar:
        grupo = jds._jds_confirmar_listings(
            grupo, pais=pais, baixar=baixar, motivos=motivos, amostras=amostras,
        )
    else:
        grupo = jds._ordenar_entrega_menor_preco(
            jds._carimbar_lista_afiliado(grupo, pais=pais)
        )
    grupo = [p for p in (grupo or []) if validar_integridade_listing(p) or p.get("fonte") != "searchapi"]
    confirmados = []
    for p in grupo or []:
        orig = p.get("original_url") or (p.get("listing_source") or {}).get("url")
        if p.get("fonte") == "searchapi" and not validar_integridade_listing(
            {**p, "original_url": orig}
        ):
            continue
        p["original_url"] = orig or p.get("original_url")
        p["affiliate_url"] = p.get("url") or p.get("link_afiliado")
        confirmados.append(p)

    ebay_search_requests = 0
    ebay_search_results = 0
    ebay_search_skip = ""
    if pais != "US":
        ebay_search_skip = "nao_us"
    elif _tem_ebay_confirmado(confirmados):
        ebay_search_skip = "ebay_ja_confirmado"
    else:
        extra, ebay_search_requests, ebay_search_results = completar_ebay_via_search(
            t,
            pais=pais,
            usar_cache=usar_cache,
            http_get=http_get,
            baixar=baixar,
            confirmar=confirmar,
            motivos=motivos,
            amostras=amostras,
        )
        for p in extra:
            if p.get("plataforma") == "ebay" and _tem_ebay_confirmado(confirmados):
                continue
            confirmados.append(p)

    status = "SEARCHAPI_SUCCESS" if confirmados else "SEARCHAPI_EMPTY"
    etapas = {
        "shopping_results": len(shopping),
        "candidates": len(candidatos),
        "offers_received": offers_recv,
        "apos_parser": apos_parser,
        "apos_matcher": apos_matcher,
        "confirmer_entrada": confirmer_entrada,
        "offers_confirmed": len(confirmados),
        "ebay_search_requests": ebay_search_requests,
        "ebay_search_results": ebay_search_results,
        "ebay_search_skip": ebay_search_skip,
    }
    _diag(
        status=status,
        q=t,
        pais=pais,
        gl=cfg["gl"],
        hl=cfg["hl"],
        currency=cfg["currency"],
        symbol=cfg["symbol"],
        shopping_requests=0 if cache_hit else 1,
        shopping_results=len(shopping),
        candidates=len(candidatos),
        product_offers_requests=offers_req,
        offers_received=offers_recv,
        offers_rejected=rejeitadas,
        offers_confirmed=len(confirmados),
        etapas=etapas,
        rejeicoes={k: v for k, v in motivos.items() if v},
        rejeicoes_ofertas=amostras[:20],
        cache_hit=cache_hit,
        fallback=False,
        http=http,
        ebay_search_requests=ebay_search_requests,
        ebay_search_results=ebay_search_results,
        ebay_search_skip=ebay_search_skip,
    )
    print(
        "[SearchApi] "
        f"shopping_requests={0 if cache_hit else 1} "
        f"shopping_results={len(shopping)} "
        f"candidates={len(candidatos)} "
        f"product_offers_requests={offers_req} "
        f"offers_received={offers_recv} "
        f"apos_parser={apos_parser} "
        f"apos_matcher={apos_matcher} "
        f"confirmer_entrada={confirmer_entrada} "
        f"offers_rejected={rejeitadas} "
        f"offers_confirmed={len(confirmados)} "
        f"rejeicoes={ {k: v for k, v in motivos.items() if v} } "
        f"rejeicoes_ofertas={amostras[:11]} "
        f"cache_hit={str(cache_hit).lower()} "
        f"ebay_search_requests={ebay_search_requests} "
        f"ebay_search_skip={ebay_search_skip or '-'} "
        f"fallback=false"
    )
    return confirmados[:limite], status
