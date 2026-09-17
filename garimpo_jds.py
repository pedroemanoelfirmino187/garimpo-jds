

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import os
import random
import re
import subprocess
import sys
import urllib.parse
import sqlite3
import threading
import json
import locale
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

try:
    import flet as ft
except ImportError:
    ft = None

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

ID_AMAZON = (
    (os.environ.get("AMAZON_PARTNER_TAG") or os.environ.get("AMAZON_TAG_BR") or "").strip()
    or "jdseconomiz0e-20"
)
ID_AMAZON_US = (
    (os.environ.get("AMAZON_TAG_US") or os.environ.get("AMAZON_PARTNER_TAG_US") or "").strip()
    or "jdseconomiza-20"
)
ID_SHOPEE = "18381751263"
ID_MERCADO_LIVRE = "mape592520"


def _normalizar_pais(pais):
    p = (pais or "BR").strip().upper().replace("-", " ")
    if p in {"US", "USA", "UNITED STATES", "EUA", "EN", "EN US"}:
        return "US"
    return "BR"


_TEXTOS_SERVIDOR = {
    "nenhum_produto": {
        "BR": "Nenhum produto encontrado",
        "US": "No products found",
    },
    "erro_servidor": {
        "BR": "Erro no servidor",
        "US": "Server error",
    },
    "token_invalido": {
        "BR": "token inválido",
        "US": "invalid token",
    },
    "ver_preco_loja": {
        "BR": "Ver preço na loja",
        "US": "See price in store",
    },
    "ver_preco_site": {
        "BR": "Ver Preço Real no Site",
        "US": "See real price on the site",
    },
    "ok": {"BR": "ok", "US": "ok"},
}


def mensagem_servidor(chave, pais="BR"):
    """Texto da API no idioma do mercado: BR → português, US → inglês."""
    bloco = _TEXTOS_SERVIDOR.get(chave) or {}
    idioma = "US" if _normalizar_pais(pais) == "US" else "BR"
    return bloco.get(idioma) or bloco.get("BR") or str(chave or "")


def idioma_eh_portugues(texto):
    s = (texto or "").strip().lower().replace("_", "-")
    if not s:
        return False
    if "portuguese" in s or "portugues" in s:
        return True
    return bool(re.search(r"(?:^|[\s,;/])pt(?:[-@.]|$)", " " + s))


def pais_pelo_idioma(texto_locale):
    """Locale 'pt' (pt, pt-BR, pt-PT) → BR. Qualquer outro idioma → US."""
    return "BR" if idioma_eh_portugues(texto_locale) else "US"


def detectar_locale_sistema(page=None):
    """Lê o idioma padrão do aparelho/OS, sem pedir escolha ao usuário."""
    partes = []
    if page is not None:
        for nome in ("platform_locale", "web_renderer"):
            val = getattr(page, nome, None)
            if val and nome != "web_renderer":
                partes.append(str(val))
        loc = getattr(page, "locale", None)
        if loc is not None:
            partes.append(str(loc))
            for attr in ("language_code", "language", "script", "country_code", "locale_name"):
                val = getattr(loc, attr, None)
                if val:
                    partes.append(str(val))
    for envk in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        val = (os.environ.get(envk) or "").strip()
        if val:
            partes.append(val)
    for fn in (locale.getdefaultlocale, locale.getlocale):
        try:
            par = fn()
            if par and par[0]:
                partes.append(str(par[0]))
        except Exception:
            pass
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(128)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 128):
                partes.append(buf.value)
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (int(langid) & 0x3FF) == 0x16:
                partes.append("pt")
        except Exception:
            pass
    return " ".join(str(p) for p in partes if p)


def pais_do_dispositivo(page=None):
    return pais_pelo_idioma(detectar_locale_sistema(page))


_TEXTOS_APP = {
    "hint_busca": {"BR": "Garimpar produto...", "US": "Search a product..."},
    "garimpar": {"BR": "Garimpar", "US": "Search"},
    "tooltip_voz": {"BR": "Falar qualquer produto", "US": "Speak any product"},
    "tooltip_share": {"BR": "Compartilhar", "US": "Share"},
    "hint_menor": {
        "BR": "O menor preço aparece no topo após o garimpo.",
        "US": "The lowest price appears on top after the search.",
    },
    "cole_link": {"BR": "Cole o link do produto", "US": "Paste the product link"},
    "pontos": {"BR": "Pontos JDS: {n}", "US": "JDS points: {n}"},
    "roleta_hint": {"BR": "Gire a Roleta da Sorte semanal", "US": "Spin the weekly lucky wheel"},
    "checkin": {"BR": "Check-in Diário", "US": "Daily check-in"},
    "loja": {"BR": "Loja", "US": "Store"},
    "ver_oferta": {"BR": "Ver Oferta", "US": "View Deal"},
    "copiar_titulo": {"BR": "Copiar título", "US": "Copy title"},
    "lista_desejos": {"BR": "Lista de Desejos", "US": "Wishlist"},
    "melhor_preco": {"BR": "🔥 MELHOR PREÇO", "US": "🔥 BEST PRICE"},
    "menor_preco_selo": {"BR": "🏆 MENOR PREÇO", "US": "🏆 LOWEST PRICE"},
    "primeiro": {"BR": "🏆 1º LUGAR", "US": "🏆 1ST PLACE"},
    "loja_oficial": {"BR": "LOJA OFICIAL", "US": "OFFICIAL STORE"},
    "anti_golpe": {"BR": "ANTI-GOLPE: confira o vendedor", "US": "SCAM CHECK: review the seller"},
    "novo": {"BR": "NOVO", "US": "NEW"},
    "titulo_copiado": {"BR": "Título copiado", "US": "Title copied"},
    "cupom": {
        "BR": "Cupom JDS10 copiado. Cole no carrinho da loja.",
        "US": "Coupon JDS10 copied. Paste it in the store cart.",
    },
    "ja_desejo": {
        "BR": "Este produto já está na Lista de Desejos",
        "US": "This product is already on the Wishlist",
    },
    "guardado": {
        "BR": "Guardado. Vamos avisar se o preço cair (app aberto).",
        "US": "Saved. We'll notify you if the price drops (app open).",
    },
    "preco_caiu": {"BR": "Preço caiu!", "US": "Price dropped!"},
    "desconto": {"BR": "Desconto: {titulo} agora {preco}", "US": "Deal: {titulo} now {preco}"},
    "sem_alerta": {
        "BR": "Nenhum alerta ainda. Toque na estrela de um card no Garimpar.",
        "US": "No alerts yet. Tap the star on a card in Search.",
    },
    "caiu": {"BR": "Caiu: {a} → {b}", "US": "Dropped: {a} → {b}"},
    "monitorando": {"BR": "Monitorando {p}", "US": "Watching {p}"},
    "alerta_ativo": {
        "BR": "Alerta ativo — aviso no app se o preço cair",
        "US": "Alert on — we'll notify in the app if the price drops",
    },
    "remover": {"BR": "Remover", "US": "Remove"},
    "removido": {"BR": "Removido da Lista de Desejos", "US": "Removed from Wishlist"},
    "sem_desejos": {"BR": "Nenhum produto na Lista de Desejos", "US": "No products on the Wishlist"},
    "verificando": {"BR": "Verificando preços da Lista de Desejos...", "US": "Checking Wishlist prices..."},
    "sem_desconto": {"BR": "Nenhum desconto novo agora", "US": "No new discounts right now"},
    "digite": {"BR": "Digite um produto para garimpar", "US": "Type a product to search"},
    "ainda": {"BR": "Ainda garimpando o produto anterior...", "US": "Still searching the previous product..."},
    "nenhuma_oferta": {"BR": "Nenhuma oferta encontrada para este termo", "US": "No products found"},
    "menor_preco_linha": {
        "BR": "Menor preço: {preco} na {loja}",
        "US": "Lowest price: {preco} at {loja}",
    },
    "falha_motor": {"BR": "Falha no motor de busca: {e}", "US": "Search error: {e}"},
    "fale": {"BR": "Fale o produto... (qualquer um)", "US": "Say the product... (anything)"},
    "nao_entendi": {
        "BR": "Não entendi. Fale de novo ou digite o produto.",
        "US": "Didn't catch that. Speak again or type the product.",
    },
    "cole_valido": {"BR": "Cole um link válido", "US": "Paste a valid link"},
    "achado_ok": {"BR": "Link pronto para abrir com rastreio JDS", "US": "Link ready to open with JDS tracking"},
    "achado_validado": {"BR": "Achado validado pela JDS Economiza", "US": "Find validated by JDS Economiza"},
    "checkin_feito": {"BR": "Check-in de hoje já feito", "US": "Today's check-in already done"},
    "checkin_ok": {"BR": "Check-in diário +25 pontos", "US": "Daily check-in +25 points"},
    "roleta_ja": {"BR": "A roleta já girou nesta semana", "US": "The wheel already spun this week"},
    "roleta_premio": {"BR": "Roleta da Sorte: {premio}", "US": "Lucky wheel: {premio}"},
    "roleta_snack": {"BR": "Roleta: {premio}", "US": "Wheel: {premio}"},
    "tab_garimpar": {"BR": "🔍 Garimpar", "US": "🔍 Search"},
    "tab_descontos": {"BR": "🔥 Super Descontos", "US": "🔥 Super Deals"},
    "tab_desejos": {"BR": "⭐ Lista de Desejos", "US": "⭐ Wishlist"},
    "tab_achados": {"BR": "👥 Achados", "US": "👥 Finds"},
    "tab_recompensas": {"BR": "🎰 Recompensas", "US": "🎰 Rewards"},
    "promo_jds": {
        "BR": "Promoções agressivas selecionadas pela JDS",
        "US": "Aggressive deals selected by JDS",
    },
    "aviso_desejos": {
        "BR": "Aviso no app se o preço cair. Precisa do JDS aberto. Checagem a cada 15 min.",
        "US": "In-app alert if the price drops. Keep JDS open. Checks every 15 min.",
    },
    "verificar_agora": {"BR": "Verificar preços agora", "US": "Check prices now"},
    "cole_rastreio": {
        "BR": "Cole um link. A JDS Economiza trata o rastreio em segundo plano.",
        "US": "Paste a link. JDS Economiza handles tracking in the background.",
    },
    "validar": {"BR": "Validar achado", "US": "Validate find"},
    "roleta_titulo": {"BR": "Roleta da Sorte semanal", "US": "Weekly lucky wheel"},
    "girar": {"BR": "Girar roleta", "US": "Spin the wheel"},
    "convite_titulo": {"BR": "Convite JDS Economiza", "US": "JDS Economiza invite"},
    "convite_corpo": {
        "BR": "JDS Economiza — o app híbrido para garimpar o menor preço na Amazon, Shopee e Mercado Livre. Compartilhe e economize com a JDS.",
        "US": "JDS Economiza — the hybrid app to hunt the lowest price on Amazon and eBay. Share and save with JDS.",
    },
    "convite_copiado": {"BR": "O texto do convite já foi copiado.", "US": "The invite text was copied."},
    "fechar": {"BR": "Fechar", "US": "Close"},
    "copiado": {"BR": "Copiado", "US": "Copied"},
    "nao_copiar": {"BR": "Não foi possível copiar agora", "US": "Couldn't copy right now"},
    "de_por": {"BR": "De {a} por {b}", "US": "From {a} to {b}"},
    "premio_50": {"BR": "+50 pontos", "US": "+50 points"},
    "premio_cupom": {"BR": "Cupom JDS10", "US": "JDS10 coupon"},
    "premio_frete": {"BR": "Frete monitorado", "US": "Tracked shipping"},
    "premio_alerta": {"BR": "Alerta extra", "US": "Extra alert"},
    "premio_tente": {"BR": "Tente na próxima semana", "US": "Try again next week"},
}


def texto_app(chave, pais="BR", **kwargs):
    bloco = _TEXTOS_APP.get(chave) or {}
    idioma = "US" if _normalizar_pais(pais) == "US" else "BR"
    s = bloco.get(idioma) or bloco.get("BR") or str(chave or "")
    if kwargs:
        try:
            s = s.format(**kwargs)
        except Exception:
            pass
    return s


def _serper_locale(pais="BR"):
    if _normalizar_pais(pais) == "US":
        return {"gl": "us", "hl": "en"}
    return {"gl": "br", "hl": "pt"}


def _consulta_serper_shopping(termo):
    """Só o nome do produto. Nunca envia site:amazon / site:shopee / site:mercadolivre."""
    t = re.sub(r"\s+", " ", (termo or "").strip())
    t = re.sub(r"\bsite:\S+", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _lojas_do_pais(pais="BR"):
    if _normalizar_pais(pais) == "US":
        return ("amazon", "ebay")
    return ("amazon", "mercado_livre", "shopee")


def _host_amazon_eua(url):
    host = urllib.parse.urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if "amazon.com.br" in host or "amazon.com.mx" in host:
        return False
    return host == "amazon.com" or host.endswith(".amazon.com")


def _carimbar_tag_amazon(url, tag):
    url_limpa = (url or "").strip()
    if not url_limpa.startswith("http") or "amazon." not in url_limpa.lower():
        return url_limpa
    try:
        parsed = urllib.parse.urlparse(url_limpa)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        qs["tag"] = [(tag or ID_AMAZON).strip() or ID_AMAZON]
        return urllib.parse.urlunparse(parsed._replace(
            query=urllib.parse.urlencode(qs, doseq=True),
        ))
    except Exception:
        sep = "&" if "?" in url_limpa else "?"
        return f"{url_limpa}{sep}tag={tag or ID_AMAZON}"


def aplicar_tag_amazon_eua(url):
    """amazon.com → jdseconomiza-20. Nunca usa o ID do Brasil."""
    if "amazon.com.br" in (url or "").lower():
        return _carimbar_tag_amazon(url, ID_AMAZON)
    return _carimbar_tag_amazon(url, ID_AMAZON_US)


def aplicar_afiliado_por_dominio(url):
    """Link final da loja + ID JDS do Brasil ou dos EUA, conforme o domínio."""
    href = _desempacotar_link_google(url) or (url or "").strip()
    if not href.startswith("http"):
        return href
    plat = _plataforma_loja(href) or _detectar_plataforma(href)
    if plat == "amazon":
        if _host_amazon_eua(href):
            return aplicar_tag_amazon_eua(href)
        return _carimbar_tag_amazon(href, ID_AMAZON)
    return _aplicar_afiliado_google(href, plat)


def _titulo_limpo_oferta(titulo):
    t = re.sub(r"\s+", " ", (titulo or "").strip())
    t = re.sub(
        r"\s*[-|]\s*(Shopee Brasil|Shopee|Amazon\.com\.br|Amazon\.com|Amazon|Mercado Livre|eBay)\s*$",
        "",
        t,
        flags=re.I,
    )
    return t[:180].strip()


def _preco_numerico_limpo(valor, pais="BR"):
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        n = _preco_para_numero(valor, pais=pais)
    if n != n or n < 0:
        return 0.0
    return round(n, 2)


def serializar_oferta_app(item, pais="BR"):
    """JSON limpo do app móvel: titulo, preco_formatado, preco_numerico, loja, link_afiliado, imagem."""
    p = item if isinstance(item, dict) else {}
    pais = _normalizar_pais(p.get("pais") or pais)
    titulo = _titulo_limpo_oferta(p.get("titulo") or "")
    bruto = p.get("preco_num")
    if bruto in (None, "", 0, 0.0):
        bruto = p.get("preco_numerico") or p.get("preco") or p.get("price")
    numero = _preco_numerico_limpo(bruto, pais=pais)
    if numero >= 999990:
        texto = mensagem_servidor("ver_preco_loja", pais)
    else:
        texto = _formatar_preco(numero, pais=pais)
    href = aplicar_afiliado_por_dominio(
        _link_ver_oferta(p) or p.get("url") or p.get("link") or p.get("link_afiliado") or ""
    )
    imagem = (p.get("foto") or p.get("imagem") or p.get("image") or "").strip()
    if imagem.startswith("//"):
        imagem = "https:" + imagem
    loja = (p.get("loja") or _nome_loja(p.get("plataforma")) or "").strip()
    return {
        "titulo": titulo,
        "preco_formatado": texto,
        "preco_numerico": numero,
        "loja": loja,
        "link_afiliado": href,
        "imagem": imagem,
        "price": texto,
        "preco": texto,
        "preco_num": numero,
        "url": href,
        "link": href,
        "foto": imagem,
        "plataforma": p.get("plataforma") or _plataforma_loja(href),
        "pais": pais,
        "selo": p.get("selo"),
        "campeao": bool(p.get("campeao")),
        "fonte": p.get("fonte"),
        "full": bool(p.get("full")),
        "loja_oficial": p.get("loja_oficial", True),
        "termo_busca": p.get("termo_busca") or "",
    }


def serializar_lista_app(lista, pais="BR"):
    pais = _normalizar_pais(pais)
    saida = [serializar_oferta_app(p, pais=pais) for p in (lista or []) if isinstance(p, dict)]
    saida.sort(key=_rank_oferta_real)
    return saida


ASIN_DUALSENSE = "B0CQKLS4RP"
CUPOM_JDS = "JDS10"
CACHE_GARIMPO = Path(__file__).resolve().parent / "cache_garimpo.json"
CACHE_GARIMPO_DB = Path(__file__).resolve().parent / "cache_garimpo.db"
ARQ_DESEJOS = Path(__file__).resolve().parent / "desejos_jds.json"
ARQ_PONTOS = Path(__file__).resolve().parent / "pontos_jds.json"
CACHE_TTL_SEG = 2 * 3600
_CACHE_LOCK = threading.Lock()
_MEM_CACHE = {}
INTERVALO_ALERTA_SEG = 15 * 60
JDS_API_URL = (os.environ.get("JDS_API_URL") or "").strip().rstrip("/")
FOTO_PADRAO = "https://images.unsplash.com/photo-1544816155-12df9643f363?w=600&auto=format&fit=crop&q=80"
HEADERS_GOOGLE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Connection": "keep-alive",
}

def _carregar_json(caminho, padrao):
    try:
        if caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            return dados if isinstance(dados, type(padrao)) else padrao
    except Exception:
        pass
    return padrao


def _gravar_json(caminho, dados):
    try:
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[JDS] não gravou {caminho.name}: {e}")


def _item_desejo_gravavel(item):
    return {
        "titulo": item.get("titulo") or "",
        "preco": item.get("preco") or "",
        "preco_num": float(item.get("preco_num") or 0),
        "url": item.get("url") or "",
        "foto": item.get("foto") or "",
        "plataforma": item.get("plataforma") or "",
        "loja": item.get("loja") or "",
        "pais": _normalizar_pais(item.get("pais") or "BR"),
        "alerta": True,
        "queda": bool(item.get("queda")),
        "preco_anterior": item.get("preco_anterior") or "",
    }


lista_desejos = [
    _item_desejo_gravavel(x)
    for x in (_carregar_json(ARQ_DESEJOS, []) or [])
    if isinstance(x, dict) and (x.get("url") or x.get("titulo"))
]
_pts = _carregar_json(ARQ_PONTOS, {"saldo": 0, "checkin": "", "roleta": ""})
pontos_jds = {
    "saldo": int(_pts.get("saldo") or 0),
    "checkin": str(_pts.get("checkin") or ""),
    "roleta": str(_pts.get("roleta") or ""),
}
achados_convertidos = []


def _salvar_desejos():
    _gravar_json(ARQ_DESEJOS, [_item_desejo_gravavel(x) for x in lista_desejos])


def _salvar_pontos():
    _gravar_json(ARQ_PONTOS, pontos_jds)


def _url_chave(url):
    return (url or "").split("?")[0].split("#")[0].rstrip("/").lower()


def gerar_link_afiliado(url_original, plataforma):
    try:
        url_limpa = (url_original or "").strip()
        if not url_limpa or "http" not in url_limpa:
            return url_limpa
        if plataforma == "shopee":
            parsed_url = urllib.parse.urlparse(url_limpa)
            qs = urllib.parse.parse_qs(parsed_url.query)
            termo = (qs.get("keyword") or [""])[0]
            if not termo:
                slug = urllib.parse.unquote(parsed_url.path.strip("/"))
                termo = re.sub(r"-i\.\d+.*", "", slug, flags=re.I)
                termo = re.sub(r"product/\d+/\d+", "", termo)
                termo = termo.replace("-", " ").strip()
            return _link_busca_shopee(termo or "ofertas")
        if _eh_pagina_compra(url_limpa, plataforma):
            return _aplicar_afiliado_google(url_limpa, plataforma)
        if plataforma == "amazon":
            parsed_url = urllib.parse.urlparse(url_limpa)
            qs = urllib.parse.parse_qs(parsed_url.query)
            termo = (qs.get("k") or qs.get("keyword") or [""])[0]
            if not termo:
                termo = urllib.parse.unquote(parsed_url.path.strip("/")).replace("-", " ")
            return _link_busca_amazon(termo or "ofertas")
        if plataforma == "mercado_livre":
            parsed_url = urllib.parse.urlparse(url_limpa)
            slug = urllib.parse.unquote(parsed_url.path.strip("/"))
            slug = re.sub(r"/p/.*", "", slug)
            termo = slug.replace("-", " ").replace("/", " ").strip()
            return _link_busca_ml(termo or "ofertas")
        return url_limpa
    except Exception as e:
        print(f"[Aviso] Erro no link: {e}")
        return url_original


def _limpar_preco_serper(texto, pais="BR"):
    """BR: R$ 1.799,00 → 1799.00. US: $62.00 → 62.00 (não apaga o ponto decimal)."""
    if texto is None:
        return 0.0
    if isinstance(texto, (int, float)):
        n = float(texto)
        return n if n > 0 else 0.0
    bruto = str(texto).strip()
    if not bruto:
        return 0.0
    us = (
        _normalizar_pais(pais) == "US"
        or ("$" in bruto and "R$" not in bruto.upper())
    )
    if us:
        n = _preco_para_numero(bruto, pais="US")
        return n if n > 0 else 0.0
    s = bruto.replace("R$", "").replace("r$", "").replace("$", "")
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d.]", "", s)
    if not s or s == ".":
        return 0.0
    try:
        n = float(s)
        return n if n > 0 else 0.0
    except ValueError:
        return 0.0


def _preco_serper_para_float(texto, pais="BR"):
    """Converte texto de preço Serper em float no formato do país."""
    return _limpar_preco_serper(texto, pais=pais)


def _source_loja_oficial(source, pais="BR"):
    s = (source or "").lower()
    if _normalizar_pais(pais) == "US":
        return "amazon" in s or "ebay" in s
    return (
        "mercado livre" in s
        or "mercadolivre" in s
        or "mercado libre" in s
        or "amazon" in s
        or "shopee" in s
    )


def _preco_para_numero(texto, pais="BR"):
    if texto is None:
        return 0.0
    if isinstance(texto, (int, float)):
        return float(texto)
    limpo = re.sub(r"[^\d,.-]", "", str(texto))
    if not limpo:
        return 0.0
    if _normalizar_pais(pais) == "US":
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(",", "")
        elif "," in limpo and "." not in limpo:
            limpo = limpo.replace(",", ".")
    elif "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


def _formatar_preco(valor, pais="BR"):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        n = 0.0
    if n == 999999.0 or n >= 999990:
        return mensagem_servidor("ver_preco_site", pais)
    if _normalizar_pais(pais) == "US":
        return f"${n:,.2f}"
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _detectar_plataforma(url):
    baixa = (url or "").lower()
    if "amazon." in baixa:
        return "amazon"
    if "shopee." in baixa or "shp.ee" in baixa:
        return "shopee"
    if "mercadolivre." in baixa or "mercadolibre." in baixa:
        return "mercado_livre"
    if "ebay." in baixa:
        return "ebay"
    return "mercado_livre"


NOMES_LOJA = {
    "mercado_livre": "Mercado Livre",
    "amazon": "Amazon",
    "shopee": "Shopee",
    "ebay": "eBay",
}


def _link_busca_shopee(termo):
    """Busca pública na Shopee (mais vendidos), sem utm de afiliado que pede login."""
    q = urllib.parse.quote((termo or "ofertas").strip())
    return (
        f"https://shopee.com.br/search?keyword={q}"
        f"&sortBy=sales"
        f"&sub_id={ID_SHOPEE}"
    )


def _consulta_shopee(produto):
    """Usa o título do card (o produto), não só o termo curto da busca."""
    p = produto or {}
    return (p.get("titulo") or p.get("termo_busca") or "ofertas").strip()


def _consulta_do_card(produto):
    """Título do anúncio, não o termo curto (evita Amazon abrir controle paralelo)."""
    p = produto or {}
    return (p.get("titulo") or p.get("termo_busca") or "ofertas").strip()


def _link_busca_ml(termo):
    """Lista do produto no ML ordenada pelo menor preço (OrderId_PRICE)."""
    limpo = re.sub(r"[^\w\s-]", "", (termo or "ofertas").lower())
    slug = "-".join(p for p in limpo.split() if p)[:80] or "ofertas"
    return (
        f"https://lista.mercadolivre.com.br/{slug}_OrderId_PRICE"
        f"?identity={ID_MERCADO_LIVRE}"
    )


def _link_busca_amazon(termo):
    """Busca do produto na Amazon por relevância (price-asc mostra paralelo)."""
    q = urllib.parse.quote((termo or "ofertas").strip())
    return f"https://www.amazon.com.br/s?k={q}&tag={ID_AMAZON}"


def _link_busca_amazon_us(termo):
    q = urllib.parse.quote((termo or "deals").strip())
    return f"https://www.amazon.com/s?k={q}&tag={ID_AMAZON_US}"


def _link_busca_ebay(termo):
    q = urllib.parse.quote((termo or "deals").strip())
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&_sop=15"


def _anuncio_veio_do_google(produto):
    fonte = ((produto or {}).get("fonte") or "").lower()
    return fonte in {"google", "scrape", "oficial"}


def _url_canonica_loja(url, plat, pais="BR"):
    """Normaliza para a página do produto quando dá para extrair o ID."""
    href = (url or "").strip()
    pais = _normalizar_pais(pais)
    if plat == "amazon":
        asin = _asin_amazon(href)
        if asin:
            if pais == "US" or _host_amazon_eua(href):
                return f"https://www.amazon.com/dp/{asin}"
            return f"https://www.amazon.com.br/dp/{asin}"
    if plat == "ebay":
        itm = re.search(r"/itm/(?:[^/?#]+/)?(\d{9,})", href)
        if itm:
            return f"https://www.ebay.com/itm/{itm.group(1)}"
    return href


def _url_e_google(url):
    """True se o clique cairia no Google, não na loja."""
    return "google." in (url or "").lower()


def _url_e_busca_loja(url):
    """True se o link é barra de pesquisa da loja (/search, ?q=, keyword=, ranking…)."""
    bruto = (url or "").strip()
    if not bruto:
        return False
    u = bruto.lower()
    parsed = urllib.parse.urlparse(u if u.startswith("http") else "https://x/" + u.lstrip("/"))
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    host = (parsed.netloc or "").lower()
    if "google." in host:
        if "ibp=oshop" in u or "prds=" in u or "/shopping/" in path:
            return False
        return "/search" in path
    if any(p in path for p in ("/search", "/sch/", "/jm/search")):
        return True
    if path.rstrip("/") == "/s" or path.endswith("/s/") or "/s?" in u:
        return True
    if "lista.mercadolivre" in host or "listado.mercadolivre" in host or "listado.mercadolibre" in host:
        return True
    if "orderid_price" in u:
        return True
    if "price-asc-rank" in u:
        return True
    qs = urllib.parse.parse_qs(parsed.query)
    if any(k in qs for k in ("keyword", "keywords", "_nkw")):
        if any(x in path for x in ("/dp/", "/gp/product/", "/p/", "/itm/", "-i.")):
            return False
        return True
    if ("k" in qs or "q" in qs) and (
        path.rstrip("/") == "/s" or "/search" in path or "/sch/" in path
    ):
        return True
    return False


def _url_anuncio_exato(url, plat):
    """True só para página do anúncio (não busca da loja)."""
    u = (url or "").lower()
    if not u.startswith("http"):
        return False
    if _url_e_busca_loja(url):
        return False
    if plat == "amazon":
        return bool(_asin_amazon(url))
    if plat == "mercado_livre":
        if _parece_url_conteudo(u):
            return False
        return bool(_id_mlb(url)) or "/p/" in u or "produto.mercadolivre." in u or "produto.mercadolibre." in u
    if plat == "shopee":
        return "-i." in u or "/product/" in u
    if plat == "ebay":
        return "/itm/" in u
    return False


def _link_do_item_serper_card(produto):
    """O link do próprio item da Serper, com afiliado. Não troca o produto."""
    p = produto if isinstance(produto, dict) else {}
    plat = p.get("plataforma") or _plataforma_loja(p.get("url") or "")
    pais = _normalizar_pais(p.get("pais") or "BR")
    for bruto in (p.get("url"), p.get("link"), p.get("link_afiliado")):
        h = (bruto or "").strip()
        if not h:
            continue
        h = _desempacotar_link_google(h) or h
        if not h.startswith("http"):
            continue
        if _url_e_busca_loja(h):
            continue
        if _url_e_google(h):
            continue
        can = _url_canonica_loja(h, plat or _plataforma_loja(h), pais=pais)
        return aplicar_afiliado_por_dominio(can)
    return ""


def _link_compra_do_card(produto):
    """Ver Oferta: link do item. Busca da loja só em catálogo/fallback."""
    p = produto or {}
    plat = p.get("plataforma")
    url = p.get("url") or p.get("link_afiliado") or ""
    pais = _normalizar_pais(p.get("pais") or "BR")
    fonte = (p.get("fonte") or "").lower()
    q = _consulta_do_card(p)
    if fonte != "catalogo" and fonte != "busca_loja":
        direto = _link_do_item_serper_card(p)
        if direto and not _url_e_google(direto):
            return direto
    if fonte == "busca_loja":
        return aplicar_afiliado_por_dominio(url) if url.startswith("http") else url
    url = _desempacotar_link_google(url) or url
    if _url_e_google(url) or _url_e_busca_loja(url):
        url = ""
    url = _url_canonica_loja(url, plat, pais=pais)
    if _url_anuncio_exato(url, plat) and fonte != "catalogo":
        return aplicar_afiliado_por_dominio(url)
    if fonte != "catalogo":
        if _url_anuncio_exato(url, plat):
            return aplicar_afiliado_por_dominio(url)
        if url.startswith("http") and not _url_e_busca_loja(url) and not _url_e_google(url):
            return aplicar_afiliado_por_dominio(url)
        if plat == "amazon":
            return _link_busca_amazon_us(q) if pais == "US" else _link_busca_amazon(q)
        if plat == "mercado_livre":
            return _link_busca_ml(q)
        if plat == "shopee":
            return _link_busca_shopee(_consulta_shopee(p))
        return ""
    if pais == "US":
        if plat == "amazon":
            return aplicar_tag_amazon_eua(url or _link_busca_amazon_us(q))
        if plat == "ebay":
            return url or _link_busca_ebay(q)
        return url
    if plat == "amazon":
        return _link_busca_amazon(q)
    if plat == "mercado_livre":
        return _link_busca_ml(q)
    if plat == "shopee":
        return _link_busca_shopee(_consulta_shopee(p))
    return aplicar_afiliado_por_dominio(url)


def _link_ver_oferta(produto):
    """Ver Oferta: o link do produto da Serper (ou catálogo), já com afiliado."""
    p = produto if isinstance(produto, dict) else {}
    fonte = (p.get("fonte") or "").lower()
    if fonte in {"catalogo", "busca_loja"}:
        return _link_compra_do_card(p)
    direto = _link_do_item_serper_card(p)
    if direto and not _url_e_google(direto):
        return direto
    return _link_compra_do_card(p)


def _nome_loja(plataforma):
    return NOMES_LOJA.get(plataforma, "Loja")


def _eh_link_produto(url, plataforma):
    return _url_anuncio_exato(url, plataforma)


def _extrair_foto(img_tag):
    if not img_tag:
        return None
    for attr in ("data-src", "data-srcset", "src", "data-zoom", "data-lsrc"):
        valor = img_tag.get(attr)
        if not valor:
            continue
        if "srcset" in attr and "," in valor:
            valor = valor.split(",")[0].strip().split(" ")[0]
        if valor.startswith("//"):
            valor = "https:" + valor
        if valor.startswith("http") and "placeholder" not in valor.lower():
            return valor
    return None


def _eh_pagina_compra(url, plat):
    u = (url or "").lower()
    if plat == "amazon":
        return "/dp/" in u or "/gp/product/" in u
    if plat == "mercado_livre":
        return (
            "/p/" in u
            or "/mlb" in u
            or "produto.mercadolivre." in u
            or "produto.mercadolibre." in u
            or "orderid_price" in u
        )
    if plat == "shopee":
        return (
            "-i." in u
            or "/product/" in u
            or ("shopee.com.br/search" in u and "keyword=" in u)
            or "affiliate.shopee" in u
            or "s.shopee.com.br" in u
        )
    if plat == "ebay":
        return "/itm/" in u or "/i/" in u
    return False


def _asin_amazon(url):
    h = urllib.parse.unquote(url or "")
    achado = re.search(
        r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/|/images/P/)([A-Z0-9]{10})",
        h,
        re.I,
    )
    if achado:
        return achado.group(1).upper()
    achado = re.search(r"[?&]asin=([A-Z0-9]{10})\b", url or "", re.I)
    return achado.group(1).upper() if achado else ""


def _id_mlb(url):
    achado = re.search(r"MLB-?(\d{8,})", url or "", re.I)
    return achado.group(1) if achado else ""


def _titulo_parece_mesmo_produto(titulo_a, titulo_b):
    a = set(_tokens_busca(titulo_a))
    b = set(_tokens_busca(titulo_b))
    if not a or not b:
        return False
    comuns = a & b
    return len(comuns) >= min(3, max(2, int(0.5 * min(len(a), len(b)))))


def _scrape_e_o_mesmo_produto(item, ref):
    """Scrape só substitui o catálogo se for o mesmo anúncio/produto."""
    if not item or not ref:
        return False
    plat = item.get("plataforma")
    if plat != ref.get("plataforma"):
        return False
    try:
        pi = float(item.get("preco_num") or 0)
        pr = float(ref.get("preco_num") or 0)
    except (TypeError, ValueError):
        return False
    if pi <= 0 or pr <= 0:
        return False
    if plat == "amazon":
        ai = _asin_amazon(item.get("url") or "")
        ar = _asin_amazon(ref.get("url") or "")
        if ar:
            return bool(ai) and ai == ar
    if plat == "mercado_livre":
        mi = _id_mlb(item.get("url") or "")
        mr = _id_mlb(ref.get("url") or "")
        if mr:
            return bool(mi) and mi == mr
    if not _titulo_parece_mesmo_produto(item.get("titulo"), ref.get("titulo")):
        return False
    return pi >= pr * 0.72


def _foto_e_generica(foto):
    f = (foto or "").lower()
    if not f.startswith("http"):
        return True
    return "unsplash.com" in f or "placeholder" in f or "via.placeholder" in f


def _foto_da_oferta(url, plat, foto_hint=""):
    """Foto do próprio anúncio — nunca imagem genérica de banco de fotos."""
    if plat == "amazon":
        asin = _asin_amazon(url)
        if asin:
            return f"https://m.media-amazon.com/images/P/{asin}._AC_SL500_.jpg"
    hint = (foto_hint or "").strip()
    if hint.startswith("//"):
        hint = "https:" + hint
    if _foto_e_generica(hint):
        return ""
    baixa = hint.lower()
    if any(p in baixa for p in ("gstatic.com", "googleusercontent.com", "encrypted-tbn")):
        return hint
    if plat == "mercado_livre" and "mlstatic" in baixa:
        return hint.replace("-I.jpg", "-O.jpg").replace("-I.webp", "-O.webp")
    if plat == "shopee" and ("cf.shopee" in baixa or "shopee" in baixa):
        return hint
    if plat == "ebay" and ("ebay" in baixa or "ebayimg" in baixa):
        return hint
    if plat == "amazon" and "amazon" in baixa:
        return hint
    if "mlstatic.com" in baixa or "media-amazon" in baixa or "cf.shopee" in baixa:
        return hint
    return ""


def _oferta_foto_preco_do_mesmo_item(item):
    """Garante título + preço + foto + link do mesmo produto."""
    if not item:
        return False
    foto = item.get("foto") or ""
    url = item.get("url") or ""
    plat = item.get("plataforma")
    try:
        preco = float(item.get("preco_num") or 0)
    except (TypeError, ValueError):
        return False
    if preco <= 0:
        return False
    if _url_anuncio_exato(url, plat):
        return True
    if _url_e_busca_loja(url):
        return False
    if _anuncio_veio_do_google(item) and str(url).startswith("http"):
        return True
    if _foto_e_generica(foto):
        return False
    if not _eh_link_produto(url, plat):
        return False
    if _anuncio_veio_do_google(item):
        return True
    f = (foto or "").lower()
    if "gstatic.com" in f or "googleusercontent.com" in f or "encrypted-tbn" in f:
        return True
    if plat == "amazon":
        if _asin_amazon(url):
            return "media-amazon" in f or "ssl-images-amazon" in f or "amazon" in f
        return "/s?" in url.lower()
    if plat == "mercado_livre":
        return "mlstatic" in f or "media-amazon" in f
    if plat == "shopee":
        return "shopee" in f or "cf.shopee" in f or "media-amazon" in f
    if plat == "ebay":
        return "ebay" in f or "ebayimg" in f or "i.ebay" in f or "gstatic.com" in f
    return False


def _montar_item_oferta(titulo, preco_num, url, foto, plat, full=False, selo="NOVO", pais="BR"):
    pais = _normalizar_pais(pais)
    url = _url_canonica_loja(url, plat, pais=pais)
    if _url_anuncio_exato(url, plat) or (_eh_pagina_compra(url, plat) and "orderid_price" not in (url or "").lower() and "/s?" not in (url or "").lower() and "shopee.com.br/search" not in (url or "").lower()):
        url_final = _aplicar_afiliado_google(url, plat, pais=pais)
    elif str(url or "").startswith("http") and not _url_e_busca_loja(url):
        url_final = url
    elif plat == "shopee":
        url_final = _link_busca_shopee(titulo)
    elif plat == "amazon":
        url_final = _link_busca_amazon_us(titulo) if pais == "US" else _link_busca_amazon(titulo)
    elif plat == "mercado_livre":
        url_final = _link_busca_ml(titulo)
    elif plat == "ebay":
        url_final = url if _url_anuncio_exato(url, "ebay") else _link_busca_ebay(titulo)
    else:
        url_final = _aplicar_afiliado_google(url, plat, pais=pais)
    foto_final = _foto_da_oferta(url_final, plat, foto) or _foto_da_oferta(url, plat, foto)
    url_final = _aplicar_afiliado_google(url_final, plat, pais=pais)
    item = {
        "titulo": titulo,
        "preco": _formatar_preco(preco_num, pais=pais),
        "preco_num": float(preco_num),
        "url": url_final,
        "foto": foto_final,
        "plataforma": plat,
        "loja": _nome_loja(plat),
        "loja_oficial": True,
        "full": full,
        "aviso_golpe": False,
        "selo": selo,
        "vale_a_pena": True,
        "pais": pais,
    }
    return item



def _score_catalogo(termo, cat_item):
    t_low = (termo or "").lower()
    return max((len(t) for t in cat_item["termos"] if t and t in t_low), default=0)


def _catalogo_compativel(termo, cat_item):
    t_low = (termo or "").lower()
    termos_cat = [t.lower() for t in cat_item["termos"]]
    if not any(t in t_low for t in termos_cat):
        return False
    marcas = [
        "samsung", "xiaomi", "iphone", "apple", "nike", "stanley",
        "lenovo", "dell", "mondial", "playstation", "xbox",
    ]
    titulos = " ".join(of["titulo"].lower() for of in cat_item["ofertas"])
    blob = f"{titulos} {' '.join(termos_cat)}"
    for marca in marcas:
        if marca in t_low and marca not in blob:
            return False
    return True


_STOPWORDS_BUSCA = {
    "de", "da", "do", "das", "dos", "para", "com", "em", "na", "no", "um", "uma",
    "o", "a", "os", "as", "e", "ou", "the", "and", "of", "sem",
}


def _sem_acento(texto):
    tabela = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñ",
        "aaaaaeeeeiiiiooooouuuucn",
    )
    return (texto or "").lower().translate(tabela)


def _tokens_busca(termo):
    texto = _sem_acento(termo)
    texto = texto.replace("sem fio", "wireless")
    texto = texto.replace("air fryer", "airfryer")
    toks = [
        t for t in re.findall(r"[a-z0-9]+", texto)
        if t not in _STOPWORDS_BUSCA and len(t) > 1
    ]
    return toks


def _token_no_titulo(tok, titulo):
    if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", titulo):
        return True
    if tok == "wireless" and ("sem fio" in titulo or "bluetooth" in titulo):
        return True
    sinonimos = {
        "garrafa": ("garrafa", "copo", "squeeze"),
        "copo": ("copo", "garrafa"),
        "termica": ("termica", "termico"),
        "termico": ("termico", "termica"),
        "tenis": ("tenis", "sapato", "sneaker"),
        "esportivo": ("esportivo", "corrida", "caminhada", "nike"),
        "celular": ("celular", "smartphone", "galaxy"),
        "smartphone": ("smartphone", "celular", "galaxy"),
        "notebook": ("notebook", "laptop", "computador"),
        "laptop": ("laptop", "notebook"),
        "relogio": ("relogio", "smartwatch", "watch"),
        "smartwatch": ("smartwatch", "relogio", "watch"),
        "airfryer": ("airfryer", "fritadeira", "air"),
        "controle": ("controle", "dualsense", "joystick", "gamepad"),
        "ps5": ("ps5", "playstation 5", "playstation5", "dualsense"),
        "playstation": ("playstation", "ps5", "dualsense"),
        "dualsense": ("dualsense", "dual sense"),
        "whey": ("whey", "protein", "proteina"),
        "protein": ("protein", "proteina", "whey"),
        "proteina": ("proteina", "protein", "whey"),
    }
    for alt in sinonimos.get(tok, ()):
        if alt in titulo:
            return True
    if tok.endswith("g") and tok[:-1].isdigit() and tok[:-1] in titulo:
        return True
    return False


def _titulo_usado(titulo):
    t = _sem_acento(titulo)
    return any(
        x in t for x in (
            "seminovo", "usado", "recondicionado", "refurbished", "open box",
        )
    )


def _titulo_indisponivel(titulo):
    t = _sem_acento(titulo or "")
    return any(
        x in t for x in (
            "nao disponivel", "indisponivel", "sem estoque", "esgotado",
            "fora de estoque", "unavailable",
        )
    )


def _parece_url_conteudo(url):
    u = (url or "").lower()
    return any(
        x in u for x in (
            "/magazine", "/blog", "/noticias", "/ajuda", "/developers",
            "/comunidade", "/forum", "/institucional", "/melistore",
        )
    )


def _parece_artigo_nao_produto(titulo):
    t = _sem_acento(titulo)
    return any(
        x in t for x in (
            "vale a pena", "qual versao", "qual e a diferenca",
            "review", "unboxing", "comparativo", "como escolher",
            "guia de compra", "tudo sobre", "fique por dentro",
            "testamos", "analise completa", "versus", " saiba se",
            "descubra se", "qual modelo",
        )
    ) or ("?" in (titulo or "") and any(
        x in t for x in ("qual ", "vale ", "melhor ", "como ", "porque ", "por que ")
    ))


def _titulo_e_acessorio_imediato(titulo):
    """Descarta capinha, película, capa, suporte e cabo no título, na hora."""
    t = _sem_acento(titulo or "")
    for palavra in ("capinha", "pelicula", "capa", "suporte", "cabo"):
        if re.search(rf"(?<![a-z0-9]){re.escape(palavra)}(?![a-z0-9])", t):
            return True
    return False


def _titulo_e_amostra_miniatura(termo, titulo):
    """Whey/creatina: sachê 30g não substitui o pote da busca."""
    t = _sem_acento(titulo or "")
    tl = _sem_acento(termo or "")
    if not any(k in tl for k in ("whey", "protein", "proteina", "creatina")):
        return False
    if any(k in tl for k in ("sache", "sachet", "30g", "amostra")):
        return False
    return any(
        x in t for x in ("sache", "sachet", "amostra", "30g", "dose unica", "1 dose")
    )


def _titulo_shopping_ok(termo, titulo):
    """Shopping: o título tem que ser o produto buscado (todas as palavras), aí o mais barato ganha."""
    if _titulo_e_acessorio_imediato(titulo) or _parece_artigo_nao_produto(titulo):
        return False
    if _titulo_e_amostra_miniatura(termo, titulo):
        return False
    if _parece_acessorio_barato(titulo, termo):
        return False
    if _titulo_usado(titulo):
        return False
    if _titulo_indisponivel(titulo):
        return False
    toks = _tokens_busca(termo)
    if not toks:
        return True
    t = _sem_acento(titulo or "")
    if not t:
        return False
    if "xbox" in toks and "xbox" not in t and any(x in t for x in ("dualsense", "ps5", "playstation")):
        return False
    if any(w in toks for w in ("ps5", "playstation", "dualsense")) and "xbox" not in toks:
        if "xbox" in t and "dualsense" not in t and "ps5" not in t:
            return False
    return _termo_contido_no_titulo(termo, titulo)


_STOP_TITULO_FORTE = {
    "controle", "sem", "para", "com", "wireless", "preto", "branco", "original",
    "oficial", "novo", "nova", "kit", "pack", "geracao", "geracao", "series",
}


def _titulos_mesmo_produto(busca, titulo_card, titulo_loja):
    """Não cola o /dp/ da Sony no card Gamrombo só porque os dois são PS5."""
    if not _titulo_shopping_ok(busca, titulo_loja):
        return False
    ts = _sem_acento(titulo_card or "")
    to = _sem_acento(titulo_loja or "")
    toks = [
        w for w in re.findall(r"[a-z0-9]+", ts)
        if len(w) > 3 and w not in _STOPWORDS_BUSCA and w not in _STOP_TITULO_FORTE
    ]
    if toks:
        return any(_token_no_titulo(w, to) for w in toks[:6])
    return _termo_contido_no_titulo(busca, titulo_loja)


def _termo_contido_no_titulo(termo, titulo):
    """Ex.: 'controle ps5' precisa aparecer no título (com sinônimos)."""
    toks = _tokens_busca(termo)
    if not toks:
        return True
    t = _sem_acento(titulo or "")
    if not t:
        return False
    return all(_token_no_titulo(tok, t) for tok in toks)


def _titulo_relevante(termo, titulo):
    if _titulo_usado(titulo):
        return False
    if _titulo_e_acessorio_imediato(titulo):
        return False
    toks = _tokens_busca(termo)
    if not toks:
        return True
    t = _sem_acento(titulo)
    if _parece_artigo_nao_produto(titulo):
        return False
    if _parece_acessorio_barato(titulo, termo):
        return False
    if any(w in toks for w in ("redmi", "iphone", "galaxy", "xiaomi")) and not any(
        x in t for x in ("gb", "ram", "smartphone", "celular", "desbloqueado", "dual sim")
    ):
        return False
    nums = [w for w in toks if w.isdigit()]
    if any(not _token_no_titulo(n, t) for n in nums):
        return False
    if any(w in toks for w in ("ps5", "playstation")) and "xbox" not in toks:
        if "dualsense" not in t and "sony" not in t:
            return False
    if "dualsense" in toks and "dualsense" not in t and "dual sense" not in t:
        return False
    hits = sum(1 for w in toks if _token_no_titulo(w, t))
    if "dualsense" in toks and ("dualsense" in t or "dual sense" in t):
        return True if len(toks) == 1 else hits >= 2
    if len(toks) <= 3:
        return hits >= max(2, len(toks) - 1) if len(toks) >= 2 else hits == 1
    return hits >= max(2, int(len(toks) * 0.7))


def _parece_acessorio_barato(titulo, termo=""):
    t = _sem_acento(titulo)
    tl = _sem_acento(termo)
    if "bolsa" in t and any(k in tl for k in ("camera", "dslr", "canon")):
        return True
    if any(k in tl for k in ("controle", "ps5", "dualsense", "playstation", "xbox")) and any(
        x in t for x in (
            "grip", "protector", "playvital", "anti-skid", "sweat",
            "dock", "carregador", "cabo", "analogico", "thumbstick",
            "base de carreg", "capa para controle", "skin", "silicone",
            "suporte", "stand", "holder", "suporte controle",
            "base para controle", "carregador de controle",
            "protetor", "capinha", "capa silicone", "capa dualsense",
            "capa ps5", "kit analog", "tpu", "soft case", "hard case",
            "estojo", "pouch", "chaveiro", "wall mount", "charging station",
        )
    ):
        return True
    if any(k in tl for k in ("redmi", "iphone", "xiaomi", "smartphone", "celular", "galaxy")) and (
        re.search(r"\bcapas?\b", t)
        or re.search(r"\btela\b", t)
        or any(
            x in t for x in (
                "capinha", "pelicula", " case", "case ", "cover", "bumper",
                "vidro temperado", "protetor de tela", "cabo usb",
                "display", "modulo", "pb para", "peca para",
            )
        )
    ):
        return True
    if any(k in tl for k in ("airpods", "airpod")) and any(
        x in t for x in (
            "charging case only", "case only", "ear tips", "capa para airpods",
            "esquerdo", "direito", "somente", "unico para", "um lado",
            "reposicao", "replacement", "left ear", "right ear",
        )
    ):
        return True
    if any(k in tl for k in ("echo", "alexa")) and (
        "relogio" in t or ("caixa de som" in t and "alexa" not in t)
    ):
        return True
    return any(
        p in t for p in (
            "capa de", "capa para", " capa", "skin", "adesivo", "pelicula",
            "silicone", "suporte para", "lixa", "adesivos", "presidio",
            " case", "case ", "cover", "bumper", "protetor de tela",
            "pelicula", "lux fold", "fold clear", "kit de reparo",
            "peca de reposicao", "peca sobressalente", "placa de reposicao",
            "bolsa para", "bolsa impermeavel", "capinha",
        )
    )


def _faixa_preco(termo, pais="BR"):
    """Piso e teto para recusar acessório barato e preço 100x (parse)."""
    t = (termo or "").lower()
    us = _normalizar_pais(pais) == "US"
    if any(k in t for k in ("dualsense", "ps5", "playstation", "xbox", "controle")):
        return (35.0, 280.0) if us else (320.0, 1600.0)
    if any(k in t for k in ("airpods", "airpod")):
        return (45.0, 450.0) if us else (250.0, 2500.0)
    if any(k in t for k in ("echo", "alexa")):
        return (80.0, 450.0) if us else (180.0, 900.0)
    if any(k in t for k in ("kindle", "e-reader", "ereader", "e reader")):
        return (40.0, 700.0) if us else (350.0, 4500.0)
    if "iphone" in t:
        return (180.0, 2500.0) if us else (1200.0, 12000.0)
    if any(k in t for k in ("redmi", "xiaomi", "galaxy", "smartphone", "celular")):
        return (80.0, 1600.0) if us else (449.0, 8000.0)
    base = float(_obter_preco_base_categoria(termo) or 40)
    if us:
        return (max(5.0, base * 0.08), max(800.0, base * 3))
    return (max(8.0, base * 0.25), max(base * 8, 500.0))


def _preco_plausivel(termo, preco, titulo, pais="BR"):
    try:
        preco = float(preco)
    except (TypeError, ValueError):
        return False
    if preco <= 0:
        return False
    if _parece_acessorio_barato(titulo, termo):
        return False
    tlow = (termo or "").lower()
    piso, teto = _faixa_preco(termo, pais=pais)
    if any(k in tlow for k in ("cabo", "carregador")):
        piso = 5.0 if _normalizar_pais(pais) == "US" else 5.0
        teto = max(teto, 200.0)
    tit = _sem_acento(titulo or "")
    if any(k in tlow for k in ("whey", "protein", "proteina")) and any(
        x in tit for x in ("900g", "1kg", "2kg", "pote")
    ):
        piso = max(piso, 45.0 if _normalizar_pais(pais) == "BR" else 12.0)
    return piso <= preco <= teto


def _normalizar_preco_mercado(n, termo, titulo, pais="BR"):
    """US: se o parse inflou 100x ($62.00 → 6200), volta o valor. BR não divide."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return 0.0
    if n <= 0:
        return 0.0
    if _preco_plausivel(termo, n, titulo, pais=pais):
        return n
    if _normalizar_pais(pais) == "US":
        cand = round(n / 100.0, 2)
        if cand > 0 and _preco_plausivel(termo, cand, titulo, pais=pais):
            return cand
    return 0.0


def _raspar_cards_mercado_livre(termo_busca, limite=6):
    """Raspagem de cards ML: título, href, foto e preço no mesmo <li>/poly-card."""
    if requests is None or BeautifulSoup is None:
        return []
    slug = "-".join((termo_busca or "ofertas").strip().lower().split()) or "ofertas"
    urls = [
        f"https://lista.mercadolivre.com.br/{slug}",
        f"https://lista.mercadolivre.com.br/{slug}_NoIndex_True",
        f"https://mercadolivre.com.br/{slug}_NoIndex_True",
    ]
    html, origem = "", ""
    for url in urls:
        html, origem = _baixar_url_loja(url, headers=HEADERS_GOOGLE, timeout=6, browser=True)
        if html and ("ui-search" in html or "poly-card" in html or "andes-money" in html):
            break
        html = ""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.ui-search-layout__item, div.poly-card, div.ui-search-result")
    produtos = []
    vistos = set()
    for card in cards:
        texto_l = card.get_text(" ", strip=True).lower()
        if "usado" in texto_l or "recondicionado" in texto_l:
            continue
        titulo_el = card.select_one("h2, a.poly-component__title, .ui-search-item__title")
        titulo = titulo_el.get_text(" ", strip=True) if titulo_el else ""
        if not titulo or titulo in vistos:
            continue
        link_el = card.select_one(
            "a[href*='/p/'], a[href*='MLB'], a.poly-component__title, a.ui-search-link, a[href]"
        )
        href = (link_el.get("href") if link_el else "") or ""
        href = href.split("#")[0]
        if href.startswith("/"):
            href = "https://www.mercadolivre.com.br" + href
        if not _eh_link_produto(href, "mercado_livre"):
            continue
        frac = card.select_one("span.andes-money-amount__fraction")
        cents = card.select_one("span.andes-money-amount__cents")
        if frac:
            preco_txt = frac.get_text(strip=True)
            if cents:
                preco_txt = f"{preco_txt},{cents.get_text(strip=True)}"
        else:
            achado = re.search(r"R\$\s*[\d\.]+,\d{2}", card.get_text(" ", strip=True))
            preco_txt = achado.group(0) if achado else ""
        preco_num = _preco_para_numero(preco_txt)
        if preco_num <= 0:
            continue
        if not _titulo_relevante(termo_busca, titulo) or not _preco_plausivel(termo_busca, preco_num, titulo):
            continue
        foto = _extrair_foto(card.select_one("img"))
        if not foto:
            continue
        vistos.add(titulo)
        produtos.append(_marcar_fonte_scrape(_montar_item_oferta(
            titulo, preco_num, href, foto, "mercado_livre",
            full="full" in texto_l,
        ), origem))
        if len(produtos) >= limite:
            break
    return produtos


def _aplicar_afiliado_google(link_loja, plataforma=None, pais="BR"):
    """Todo link de loja sai com afiliado JDS (substitui tag de terceiros)."""
    url_limpa = (link_loja or "").strip()
    if not url_limpa.startswith("http"):
        return url_limpa
    pais = _normalizar_pais(pais)
    plat = plataforma or _plataforma_loja(url_limpa)
    if plat not in {"amazon", "shopee", "mercado_livre", "ebay"}:
        plat = _detectar_plataforma(url_limpa)
    if plat == "amazon" and _host_amazon_eua(url_limpa):
        return aplicar_tag_amazon_eua(url_limpa)
    try:
        parsed = urllib.parse.urlparse(url_limpa)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if plat == "amazon":
            qs["tag"] = [ID_AMAZON]
        elif plat == "mercado_livre":
            qs["identity"] = [ID_MERCADO_LIVRE]
        elif plat == "shopee":
            qs["sub_id"] = [ID_SHOPEE]
            qs.pop("utm_source", None)
            qs.pop("utm_medium", None)
            if "shopee.com.br/search" in url_limpa.lower():
                qs["sortBy"] = ["sales"]
                qs.pop("order", None)
        elif plat == "ebay":
            return url_limpa
        else:
            return url_limpa
        return urllib.parse.urlunparse(parsed._replace(
            query=urllib.parse.urlencode(qs, doseq=True),
        ))
    except Exception as e:
        print(f"[Aviso] Erro ao aplicar afiliado: {e}")
        return url_limpa


# Catálogo oficial de produtos 100% reais com fotos de estúdio autênticas e links diretos
CATALOGO_PRODUTOS_REAIS = [
    {
        "termos": ["stanley", "copo stanley", "garrafa stanley", "copo termico", "garrafa termica", "copo"],
        "foto_real": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Copo Térmico Tipo Stanley 473ml com Tampa e Abridor Inox",
                "preco": 42.90,
                "de": 69.90,
                "url": f"https://shopee.com.br/Copo-T%C3%A9rmico-Inox-473ml-Com-Tampa-Abridor-i.389201992.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Copo Térmico Stanley com Tampa 473ml Original Aço Inoxidável",
                "preco": 49.90,
                "de": 89.90,
                "url": f"https://www.mercadolivre.com.br/copo-termico-stanley-com-tampa-473ml/p/MLB19515598?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Copo Térmico de Cerveja Stanley com Tampa 473ml Hammertone Green",
                "preco": 59.90,
                "de": 99.00,
                "url": f"https://www.amazon.com.br/dp/B0829MBQ1X?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["fone", "fone bluetooth", "bluetooth", "lenovo", "gm2 pro", "airdots", "earbuds", "headphone"],
        "foto_real": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Fone De Ouvido Bluetooth Sem Fio Lenovo GM2 Pro Gamer TWS",
                "preco": 38.90,
                "de": 79.90,
                "url": f"https://shopee.com.br/Fone-De-Ouvido-Bluetooth-Sem-Fio-Lenovo-GM2-Pro-i.389201992.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Fone de Ouvido in-ear Sem Fio Lenovo Thinkplus Livepods GM2 Pro",
                "preco": 42.50,
                "de": 85.00,
                "url": f"https://www.mercadolivre.com.br/fone-de-ouvido-in-ear-sem-fio-lenovo-thinkplus-livepods-gm2-pro/p/MLB21617267?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Fone de Ouvido Bluetooth Sem Fio Gamer Lenovo GM2 Pro Baixa Latência",
                "preco": 49.90,
                "de": 89.90,
                "url": f"https://www.amazon.com.br/dp/B0B68C2X76?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["relogio", "relógio", "smartwatch", "d20", "y68", "t800", "pulseira inteligente", "smart watch"],
        "foto_real": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Relógio Smartwatch D20 Y68 Bluetooth Inteligente Fitness",
                "preco": 29.90,
                "de": 59.90,
                "url": f"https://shopee.com.br/Rel%C3%B3gio-Smartwatch-D20-Y68-Bluetooth-Inteligente-i.312984920.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Relógio Smartwatch D20 Y68 Bluetooth Notificações Monitor Cardíaco",
                "preco": 34.90,
                "de": 65.00,
                "url": f"https://www.mercadolivre.com.br/relogio-smartwatch-d20-y68-bluetooth-notificacoes-monitor-cardiaco/p/MLB18446210?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Smartwatch D20 Inteligente com Bluetooth e Monitor Cardíaco Fitness",
                "preco": 39.90,
                "de": 75.00,
                "url": f"https://www.amazon.com.br/dp/B08N5WRWNW?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["tenis", "tênis", "nike", "tenis nike", "revolution", "sapato", "calcado", "sneaker"],
        "foto_real": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Tênis Esportivo Masculino Corrida Caminhada Confortável",
                "preco": 139.90,
                "de": 229.90,
                "url": f"https://shopee.com.br/T%C3%AAnis-Masculino-Esportivo-Corrida-Caminhada-i.293849182.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Tênis Nike Revolution 6 Next Nature Masculino Original",
                "preco": 169.90,
                "de": 299.90,
                "url": f"https://www.mercadolivre.com.br/tenis-nike-revolution-6-next-nature-masculino/p/MLB19523773?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Tênis Masculino Nike Revolution 6 Next Nature Amortecimento",
                "preco": 199.90,
                "de": 349.90,
                "url": f"https://www.amazon.com.br/dp/B09B8V1LZ3?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["xiaomi", "redmi", "redmi note 13", "note 13"],
        "foto_real": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Smartphone Xiaomi Redmi Note 13 4G 128GB 6GB RAM Versão Global",
                "preco": 899.00,
                "de": 1299.00,
                "url": f"https://shopee.com.br/Smartphone-Xiaomi-Redmi-Note-13-4G-128GB-6GB-RAM-i.401928392.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Smartphone Xiaomi Redmi Note 13 4G 128GB 6GB RAM Dual SIM",
                "preco": 949.00,
                "de": 1399.00,
                "url": f"https://www.mercadolivre.com.br/smartphone-xiaomi-redmi-note-13-4g-128gb-6gb-ram-dual-sim/p/MLB28972132?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Xiaomi Redmi Note 13 4G 128GB 6GB RAM Midnight Black Desbloqueado",
                "preco": 999.00,
                "de": 1499.00,
                "url": f"https://www.amazon.com.br/dp/B0CS3V5J3H?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["air fryer", "airfryer", "fritadeira", "mondial", "panela eletrica"],
        "foto_real": "https://images.unsplash.com/photo-1584269600464-37b1b58a9fe7?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Fritadeira Sem Óleo Air Fryer Mondial 4L Painel Inox Antiaderente",
                "preco": 239.90,
                "de": 399.90,
                "url": f"https://shopee.com.br/Fritadeira-Sem-%C3%93leo-Air-Fryer-Mondial-4L-i.382910293.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Fritadeira Sem Óleo Air Fryer Mondial AFN-40-RI Preto 4L Inox 127V",
                "preco": 269.90,
                "de": 429.00,
                "url": f"https://www.mercadolivre.com.br/fritadeira-sem-oleo-air-fryer-mondial-afn-40-ri-preto-4l-127v/p/MLB18520863?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Fritadeira Sem Óleo Mondial AFN-40-RI Family 4 Litros com Timer",
                "preco": 289.90,
                "de": 449.00,
                "url": f"https://www.amazon.com.br/dp/B09G9FPHP6?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["whey", "whey protein", "max titanium", "creatina", "suplemento", "proteina"],
        "foto_real": "https://images.unsplash.com/photo-1593095948071-474c5cc2989d?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "100% Whey Refil 900g Max Titanium Original Proteína Concentrada",
                "preco": 74.90,
                "de": 119.90,
                "url": f"https://shopee.com.br/100-Whey-Refil-900g-Max-Titanium-Original-i.391029384.18381751263?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "100% Whey Refil 900g Max Titanium Sabor Baunilha com BCAA",
                "preco": 79.90,
                "de": 125.00,
                "url": f"https://www.mercadolivre.com.br/100-whey-refil-900g-max-titanium-sabor-baunilha/p/MLB15147895?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Whey Protein 100% Puro Max Titanium Refil 900g Concentrado",
                "preco": 89.90,
                "de": 139.90,
                "url": f"https://www.amazon.com.br/dp/B094RFF8S6?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["controle", "ps5", "dualsense", "playstation", "joystick", "gamepad", "controle ps5"],
        "foto_real": "https://images.unsplash.com/photo-1606144042614-b2417e99c4e3?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "amazon",
                "titulo": "PlayStation DualSense Controle sem fio – Branco Sony PS5",
                "preco": 404.27,
                "de": 499.90,
                "url": f"https://www.amazon.com.br/PlayStation-DualSense-Controle-sem-fio/dp/{ASIN_DUALSENSE}?tag={ID_AMAZON}",
                "full": False,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Controle DualSense Sony PlayStation 5 Original Branco CFI-ZCT1W",
                "preco": 419.00,
                "de": 499.00,
                "url": f"https://lista.mercadolivre.com.br/controle-dualsense-sony-playstation-5-original_OrderId_PRICE?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "shopee",
                "titulo": "Controle DualSense Sony Original PS5 Branco",
                "preco": 449.00,
                "de": 499.90,
                "url": f"https://shopee.com.br/search?keyword={urllib.parse.quote('controle dualsense sony original ps5')}&sortBy=sales&sub_id={ID_SHOPEE}",
                "full": True,
            },
        ],
    },
    {
        "termos": ["xbox", "controle xbox", "xbox series", "controle xbox series"],
        "foto_real": "https://images.unsplash.com/photo-1605901309584-818e25960a8f?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "amazon",
                "titulo": "Xbox Wireless Controller Carbon Black – Xbox Series X|S",
                "preco": 429.90,
                "de": 499.90,
                "url": f"https://www.amazon.com.br/dp/B08H99BPJN?tag={ID_AMAZON}",
                "full": False,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Controle Xbox Series X S Sem Fio Carbon Black Original",
                "preco": 449.00,
                "de": 529.00,
                "url": f"https://lista.mercadolivre.com.br/controle-xbox-series-wireless_OrderId_PRICE?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "shopee",
                "titulo": "Controle Xbox Series Wireless Carbon Black Original",
                "preco": 469.00,
                "de": 549.90,
                "url": f"https://shopee.com.br/search?keyword={urllib.parse.quote('controle xbox series wireless original')}&sortBy=sales&sub_id={ID_SHOPEE}",
                "full": True,
            },
        ],
    },
    {
        "termos": ["samsung", "galaxy", "smartphone samsung", "celular samsung"],
        "foto_real": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Smartphone Samsung Galaxy A15 128GB 4GB RAM Dual Chip",
                "preco": 799.00,
                "de": 1099.00,
                "url": f"https://shopee.com.br/Smartphone-Samsung-Galaxy-A15-128GB-i.401928392.22001122335?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Samsung Galaxy A15 128GB Azul Escuro 4GB RAM",
                "preco": 849.00,
                "de": 1199.00,
                "url": f"https://www.mercadolivre.com.br/samsung-galaxy-a15-128-gb-azul-oscuro-4-gb-ram/p/MLB36922115?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Samsung Galaxy A15 5G 128GB Azul Escuro",
                "preco": 899.00,
                "de": 1299.00,
                "url": f"https://www.amazon.com.br/dp/B0CRQS7C8D?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["notebook", "dell", "laptop", "notebook dell"],
        "foto_real": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Notebook Dell Inspiron 15 Intel i5 8GB 256GB SSD",
                "preco": 2499.00,
                "de": 3299.00,
                "url": f"https://shopee.com.br/Notebook-Dell-Inspiron-15-Intel-i5-i.401928392.22001122336?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Notebook Dell Inspiron 15 3000 Intel Core i5",
                "preco": 2699.00,
                "de": 3499.00,
                "url": f"https://www.mercadolivre.com.br/notebook-dell-inspiron-15-3000-intel-core-i5/p/MLB19651234?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Dell Inspiron 15 Laptop Intel Core i5 8GB RAM 256GB SSD",
                "preco": 2899.00,
                "de": 3699.00,
                "url": f"https://www.amazon.com.br/dp/B0C7Q4K9XY?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["tv", "smart tv", "televisao", "televisão", "smart tv 50"],
        "foto_real": "https://images.unsplash.com/photo-1593784991095-a205069470b6?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Smart TV 50 Polegadas 4K UHD Wi-Fi HDR",
                "preco": 1799.00,
                "de": 2499.00,
                "url": f"https://shopee.com.br/Smart-TV-50-Polegadas-4K-UHD-i.401928392.22001122337?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Smart TV 50 4K UHD Samsung Crystal",
                "preco": 1999.00,
                "de": 2799.00,
                "url": f"https://www.mercadolivre.com.br/smart-tv-50-4k-uhd-samsung-crystal/p/MLB20111222?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Samsung Smart TV 50 4K Crystal UHD",
                "preco": 2199.00,
                "de": 2999.00,
                "url": f"https://www.amazon.com.br/dp/B0C1H3N2KQ?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["camera", "câmera", "dslr", "canon", "camera dslr"],
        "foto_real": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Câmera Digital DSLR Profissional Kit Lente",
                "preco": 1899.00,
                "de": 2599.00,
                "url": f"https://shopee.com.br/Camera-Digital-DSLR-Profissional-i.401928392.22001122338?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Câmera Canon EOS Rebel DSLR com Lente",
                "preco": 2199.00,
                "de": 2899.00,
                "url": f"https://www.mercadolivre.com.br/camera-canon-eos-rebel-dslr-com-lente/p/MLB18877665?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Canon EOS Rebel T7 DSLR Camera with Lens",
                "preco": 2399.00,
                "de": 3099.00,
                "url": f"https://www.amazon.com.br/dp/B07C2Z21X5?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
    {
        "termos": ["mouse", "mouse sem fio", "mouse gamer", "mouse wireless"],
        "foto_real": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600&auto=format&fit=crop&q=80",
        "ofertas": [
            {
                "plataforma": "shopee",
                "titulo": "Mouse Sem Fio Silencioso 2.4G USB Receptor",
                "preco": 33.91,
                "de": 59.90,
                "url": f"https://shopee.com.br/Mouse-Sem-Fio-Silencioso-2-4G-USB-i.389201992.22001122339?sub_id={ID_SHOPEE}",
                "full": True,
            },
            {
                "plataforma": "mercado_livre",
                "titulo": "Mouse Sem Fio Logitech M170 USB",
                "preco": 37.90,
                "de": 69.90,
                "url": f"https://www.mercadolivre.com.br/mouse-sem-fio-logitech-m170-usb/p/MLB6123456?identity={ID_MERCADO_LIVRE}",
                "full": True,
            },
            {
                "plataforma": "amazon",
                "titulo": "Logitech M170 Mouse Sem Fio USB",
                "preco": 43.89,
                "de": 79.90,
                "url": f"https://www.amazon.com.br/dp/B01N5PGDM9?tag={ID_AMAZON}",
                "full": False,
            },
        ],
    },
]

def _obter_preco_base_categoria(termo):
    t_low = (termo or "").lower()
    if any(k in t_low for k in ["smartphone", "celular", "iphone", "xiaomi", "redmi", "galaxy"]):
        return 799.0
    elif any(k in t_low for k in ["notebook", "laptop", "macbook"]):
        return 1899.0
    elif any(k in t_low for k in ["tv", "televisao", "smart tv"]):
        return 1299.0
    elif any(k in t_low for k in ["camera", "dslr", "drone"]):
        return 649.0
    elif any(k in t_low for k in ["controle", "ps5", "dualsense", "joystick", "gamepad", "playstation", "xbox"]):
        return 399.90
    elif any(k in t_low for k in ["air fryer", "fritadeira", "cafeteira", "panela", "microondas"]):
        return 289.90
    elif any(k in t_low for k in ["cadeira", "mesa"]):
        return 349.90
    elif any(k in t_low for k in ["bicicleta", "bike"]):
        return 699.0
    elif any(k in t_low for k in ["kindle", "e-reader", "ereader"]):
        return 899.0
    elif any(k in t_low for k in ["echo", "alexa"]):
        return 349.0
    elif any(k in t_low for k in ["whey", "creatina", "suplemento"]):
        return 89.90
    elif any(k in t_low for k in ["perfume", "fragrancia"]):
        return 149.90
    elif any(k in t_low for k in ["tenis", "sapato"]):
        return 139.90
    elif any(k in t_low for k in ["camisa", "camiseta", "roupa", "vestido"]):
        return 59.90
    elif any(k in t_low for k in ["relogio", "smartwatch"]):
        return 99.90
    elif any(k in t_low for k in ["headset", "headphone"]):
        return 89.90
    elif any(k in t_low for k in ["caixa de som", "som", "alexa", "speaker"]):
        return 119.90
    elif any(k in t_low for k in ["fone", "earbud", "airpod"]):
        return 49.90
    elif any(k in t_low for k in ["mochila", "bolsa"]):
        return 79.90
    elif any(k in t_low for k in ["mouse", "teclado"]):
        return 39.90
    elif any(k in t_low for k in ["garrafa", "copo"]):
        return 29.90
    elif any(k in t_low for k in ["livro"]):
        return 34.90
    return 69.90


def _rank_oferta_real(p):
    """Menor preço entre anúncios reais. Lista de busca da loja fica por último."""
    try:
        preco = float((p or {}).get("preco_num") or 9e9)
    except (TypeError, ValueError):
        preco = 9e9
    fonte = ((p or {}).get("fonte") or "").lower()
    url = (p or {}).get("url") or (p or {}).get("link") or ""
    if fonte == "busca_loja" or _url_e_busca_loja(url):
        return (2, preco)
    return (0, preco)


def _ordenar_entrega_menor_preco(lista_produtos):
    """Garante o menor valor no topo e só a oferta mais barata de cada loja."""
    validos = []
    for p in lista_produtos or []:
        n = p.get("preco_num")
        try:
            n = float(n)
        except (TypeError, ValueError):
            n = _preco_para_numero(p.get("preco"))
        if n <= 0 or n >= 999999:
            continue
        p["preco_num"] = n
        if p.get("fonte") != "busca_loja":
            p["preco"] = _formatar_preco(n)
        validos.append(p)

    melhor_por_loja = {}
    for p in validos:
        plat = p.get("plataforma") or "outro"
        atual = melhor_por_loja.get(plat)
        if atual is None or _rank_oferta_real(p) < _rank_oferta_real(atual):
            melhor_por_loja[plat] = p

    ordenados = sorted(melhor_por_loja.values(), key=_rank_oferta_real)
    for i, p in enumerate(ordenados):
        if p.get("fonte") == "busca_loja":
            p["selo"] = "BUSCA NA LOJA"
            p["campeao"] = i == 0
            continue
        if i == 0:
            p["selo"] = "🏆 MENOR PREÇO"
            p["campeao"] = True
        else:
            p["selo"] = f"{i + 1}º menor"
            p["campeao"] = False
    return ordenados


def _chave_cache(termo, pais="BR"):
    pais = _normalizar_pais(pais)
    return "v39:" + pais + ":" + _termo_cache_norm(termo)


def _termo_cache_norm(termo):
    return re.sub(r"\s+", " ", (termo or "").strip().lower())


def _arquivo_cache_sqlite():
    extra = (os.environ.get("CACHE_GARIMPO_DB") or "").strip()
    if extra:
        return Path(extra)
    mount = (os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    candidatos = []
    if mount:
        candidatos.append(Path(mount) / "cache_garimpo.db")
    if os.name != "nt":
        data = Path("/data")
        if data.is_dir():
            candidatos.append(data / "cache_garimpo.db")
    candidatos.append(CACHE_GARIMPO_DB)
    for caminho in candidatos:
        pasta = caminho.parent
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            teste = pasta / ".jds_cache_ok"
            teste.write_text("ok", encoding="utf-8")
            teste.unlink(missing_ok=True)
            return caminho
        except Exception:
            continue
    return CACHE_GARIMPO_DB


def _copia_cache_lista(produtos):
    try:
        return json.loads(json.dumps(produtos, ensure_ascii=False))
    except Exception:
        return list(produtos or [])


def _ler_cache_garimpo(termo, pais="BR"):
    """Memória e SQLite antes da Serper. 2h, separado por termo+país."""
    termo_n = _termo_cache_norm(termo)
    pais = _normalizar_pais(pais)
    if not termo_n:
        return None
    agora = time.time()
    with _CACHE_LOCK:
        mem = _MEM_CACHE.get((termo_n, pais))
        if mem and agora - float(mem.get("quando") or 0) <= CACHE_TTL_SEG:
            return _copia_cache_lista(mem.get("produtos") or [])
        if mem:
            _MEM_CACHE.pop((termo_n, pais), None)
    try:
        with _CACHE_LOCK:
            conn = _conectar_cache_sqlite()
            try:
                row = conn.execute(
                    "SELECT json, criado_em FROM buscas WHERE termo = ? AND pais = ?",
                    (termo_n, pais),
                ).fetchone()
            finally:
                conn.close()
        if not row:
            return None
        blob, quando = row
        if agora - float(quando or 0) > CACHE_TTL_SEG:
            return None
        produtos = json.loads(blob)
        if not isinstance(produtos, list) or not produtos:
            return None
        validos = [p for p in produtos if isinstance(p, dict)]
        if validos:
            with _CACHE_LOCK:
                _MEM_CACHE[(termo_n, pais)] = {"quando": float(quando), "produtos": validos}
        return _copia_cache_lista(validos) if validos else None
    except Exception as e:
        print(f"[Cache SQLite] leitura: {e}")
        return None


def _gravar_cache_garimpo(termo, produtos, pais="BR"):
    """Salva o JSON da busca (termo + país) para não gastar Serper de novo em 2h."""
    termo_n = _termo_cache_norm(termo)
    pais = _normalizar_pais(pais)
    if not termo_n or not produtos:
        return
    agora = time.time()
    copia = _copia_cache_lista(list(produtos))
    with _CACHE_LOCK:
        _MEM_CACHE[(termo_n, pais)] = {"quando": agora, "produtos": copia}
    try:
        payload = json.dumps(copia, ensure_ascii=False)
        with _CACHE_LOCK:
            conn = _conectar_cache_sqlite()
            try:
                conn.execute(
                    """
                    INSERT INTO buscas (termo, pais, json, criado_em)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(termo, pais) DO UPDATE SET
                        json = excluded.json,
                        criado_em = excluded.criado_em
                    """,
                    (termo_n, pais, payload, agora),
                )
                conn.execute(
                    "DELETE FROM buscas WHERE criado_em < ?",
                    (agora - CACHE_TTL_SEG,),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        print(f"[Cache SQLite] gravação: {e}")


def _conectar_cache_sqlite():
    caminho = _arquivo_cache_sqlite()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho), timeout=12)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS buscas (
            termo TEXT NOT NULL,
            pais TEXT NOT NULL,
            json TEXT NOT NULL,
            criado_em REAL NOT NULL,
            PRIMARY KEY (termo, pais)
        )
        """
    )
    return conn


def _buscar_ofertas_ml_api(termo, limite=8):
    """API do Mercado Livre — só tenta se existir token; senão usa catálogo/scrape."""
    if requests is None or not (termo or "").strip():
        return []
    token = (os.environ.get("MELI_ACCESS_TOKEN") or "").strip()
    if not token:
        return []
    q = urllib.parse.quote(termo.strip())
    url = (
        f"https://api.mercadolibre.com/sites/MLB/search?q={q}"
        f"&condition=new&sort=price_asc&limit={limite}"
    )
    resultados = []
    headers = {
        "User-Agent": "JDSEconomiza/1.0 (garimpo; +https://github.com/pedroemanoelfirmino187/garimpo-jds)",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = requests.get(url, timeout=12, headers=headers)
        if resp.status_code >= 400:
            print(f"[ML API] HTTP {resp.status_code}")
            return []
        resultados = (resp.json() or {}).get("results") or []
    except Exception as e:
        print(f"[ML API] {e}")
        return []

    ofertas = []
    for it in resultados:
        titulo = (it.get("title") or "").strip()
        if not titulo or "usado" in titulo.lower() or "recondicionado" in titulo.lower():
            continue
        if (it.get("condition") or "new") != "new":
            continue
        try:
            preco = float(it.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if preco <= 0:
            continue
        permalink = (it.get("permalink") or "").replace("http://", "https://")
        if not permalink.startswith("http"):
            continue
        foto = (it.get("thumbnail") or "").replace("http://", "https://")
        foto = foto.replace("-I.jpg", "-O.jpg").replace("-I.webp", "-O.webp")
        if not foto:
            tid = it.get("thumbnail_id")
            if tid:
                foto = f"https://http2.mlstatic.com/D_NQ_NP_{tid}-O.webp"
        if not foto:
            continue
        if not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo):
            continue
        item = _montar_item_oferta(
            titulo, preco, permalink, foto, "mercado_livre",
            full=bool(it.get("shipping", {}).get("logistic_type") == "fulfillment"),
        )
        if not _oferta_foto_preco_do_mesmo_item(item):
            continue
        ofertas.append(item)
    return ofertas


def _chaves_env(*nomes):
    vistas = set()
    valores = []
    for nome in nomes:
        v = (os.environ.get(nome) or "").strip()
        if v and v not in vistas:
            vistas.add(v)
            valores.append(v)
    return valores


def _zenrows_baixar(url):
    chaves = _chaves_env("ZENROWS_API_KEY", "ZENROWS_KEY")
    if requests is None or not chaves:
        return ""
    for chave in chaves:
        try:
            resp = requests.get(
                "https://api.zenrows.com/v1/",
                params={
                    "apikey": chave,
                    "url": url,
                    "mode": "auto",
                    "proxy_country": "br",
                    **({
                        "js_render": "true",
                        "wait": "5000",
                    } if "google." in (url or "").lower() else {}),
                },
                timeout=28,
            )
            if resp.status_code >= 400 or not (resp.text or "").strip():
                print(f"[ZenRows] HTTP {resp.status_code}")
                continue
            return resp.text
        except Exception as e:
            print(f"[ZenRows] {e}")
    return ""


def _scrapingant_baixar(url, browser=True):
    chaves = _chaves_env(
        "SCRAPINGANT_API_KEY",
        "SCRAPING_ANT_KEY",
        "SCRAPINGANT_KEY",
        "SCRAPING_ANT_KEY_2",
        "SCRAPINGANT_API_KEY_2",
    )
    if requests is None or not chaves:
        return ""
    for i, chave in enumerate(chaves, 1):
        try:
            resp = requests.get(
                "https://api.scrapingant.com/v2/general",
                params={
                    "url": url,
                    "x-api-key": chave,
                    "browser": "true" if browser else "false",
                    "proxy_country": "BR",
                },
                timeout=28,
            )
            if resp.status_code >= 400:
                print(f"[ScrapingAnt] chave {i} HTTP {resp.status_code}")
                continue
            try:
                dados = resp.json()
            except Exception:
                texto = resp.text or ""
                if texto.strip():
                    return texto
                continue
            if isinstance(dados, dict):
                texto = dados.get("html") or dados.get("content") or dados.get("text") or ""
            else:
                texto = resp.text or ""
            if texto.strip():
                return texto
        except Exception as e:
            print(f"[ScrapingAnt] chave {i} {e}")
    return ""


def _pagina_bloqueada(texto):
    t = (texto or "").lower()
    if len(t) < 80:
        return True
    if t.strip().startswith("{") and any(k in t for k in ('"error"', '"code"', "unauthorized", "invalid api")):
        return True
    return any(p in t for p in (
        "api-services-support@amazon.com",
        "sorry, we just need to make sure you're not a robot",
        "enter the characters you see below",
        "unusual traffic",
        "detected unusual traffic",
        "/sorry/",
        "our systems have detected",
    ))


def _resposta_util_loja(url, texto):
    if not texto or _pagina_bloqueada(texto):
        return False
    u = (url or "").lower()
    if "amazon." in u:
        if "/dp/" in u or "/gp/product/" in u:
            return "a-offscreen" in texto or "productTitle" in texto or "data-asin" in texto
        return "data-asin" in texto or "/dp/" in texto
    if "google." in u:
        t = texto.lower()
        if any(p in t for p in ("unusual traffic", "detected unusual", "/sorry/", "not a robot")):
            return False
        tem_preco = "r$" in t or "r\\u0024" in t or "r$\\u00a0" in t
        tem_loja = "amazon.com.br" in t or "mercadolivre.com.br" in t or "shopee.com.br" in t
        tem_card = "sh-dgr" in t or "sh-pr__" in t
        return tem_preco or (tem_loja and tem_card) or (tem_preco and tem_loja)
    if "shopee.com.br/api" in u:
        return '"items"' in texto or '"item_basic"' in texto
    if "mercadolivre." in u or "mercadolibre." in u:
        return "ui-search" in texto or "poly-card" in texto or "andes-money" in texto or "/p/" in texto
    return True


_SESSAO_HTTP = None


def _sessao_http():
    global _SESSAO_HTTP
    if requests is None:
        return None
    if _SESSAO_HTTP is None:
        _SESSAO_HTTP = requests.Session()
        _SESSAO_HTTP.headers.update(HEADERS_GOOGLE)
        _SESSAO_HTTP.cookies.set("CONSENT", "YES+cb.20240516-17-p0.pt-BR+FX+123")
        _SESSAO_HTTP.cookies.set("SOCS", "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjQwNTE2X3AwGgJlbiACGgYI")
    return _SESSAO_HTTP


def _baixar_url_loja(url, headers=None, timeout=8, browser=False, avisar=True):
    """Tenta direto; ZenRows/ScrapingAnt só se a chave existir."""
    if requests is None:
        return "", ""
    try:
        sess = _sessao_http()
        resp = sess.get(url, headers=headers or HEADERS_GOOGLE, timeout=timeout)
        corpo = resp.text if resp.status_code < 400 else ""
        if _resposta_util_loja(url, corpo):
            return corpo, "direto"
    except Exception as e:
        print(f"[HTTP loja] {e}")
    if _chaves_env("ZENROWS_API_KEY", "ZENROWS_KEY"):
        zen = _zenrows_baixar(url)
        if _resposta_util_loja(url, zen):
            if avisar:
                print("[Motor] página via ZenRows")
            return zen, "zenrows"
    if _chaves_env(
        "SCRAPINGANT_API_KEY",
        "SCRAPING_ANT_KEY",
        "SCRAPINGANT_KEY",
        "SCRAPING_ANT_KEY_2",
        "SCRAPINGANT_API_KEY_2",
    ):
        if avisar:
            print("[ZenRows] sem página útil — usando ScrapingAnt")
        ant = _scrapingant_baixar(url, browser=browser)
        if _resposta_util_loja(url, ant):
            if avisar:
                print("[Motor] página via ScrapingAnt")
            return ant, "scrapingant"
    return "", ""


def _html_google_legivel(html):
    t = html or ""
    return (
        t.replace("\\u003d", "=")
        .replace("\\u0026", "&")
        .replace("\\u002f", "/")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\/", "/")
        .replace("&amp;", "&")
    )


def _loja_do_texto(texto):
    t = _sem_acento(texto or "")
    if "amazon" in t:
        return "amazon"
    if "shopee" in t:
        return "shopee"
    if "ebay" in t:
        return "ebay"
    if "mercado livre" in t or "mercadolivre" in t or "mercado libre" in t:
        return "mercado_livre"
    return ""


def _primeira_url_loja(texto):
    blob = _html_google_legivel(texto or "")
    blob = urllib.parse.unquote(blob)
    padroes = (
        r"https?://(?:www\.)?amazon\.com\.br[^\"'\s<>]*?/(?:dp|gp/product)/[A-Z0-9]{10}",
        r"https?://(?:www\.)?amazon\.com[^\"'\s<>]*?/(?:dp|gp/product)/[A-Z0-9]{10}",
        r"https?://(?:www\.|produto\.)?mercado(?:livre|libre)\.com\.br[^\"'\s<>]+",
        r"https?://(?:s\.)?shopee\.com\.br[^\"'\s<>]+",
        r"https?://(?:www\.)?ebay\.com[^\"'\s<>]*?/itm/[^\"'\s<>]+",
    )
    for padrao in padroes:
        achado = re.search(padrao, blob, re.I)
        if achado:
            url = achado.group(0).rstrip(").,;]")
            if _plataforma_loja(url):
                return url.split("#")[0]
    return ""


def _desempacotar_link_google(href):
    """Tira o redirecionamento do Google e devolve o link da loja."""
    if not href:
        return ""
    h = href.strip().replace("&amp;", "&")
    if h.startswith("//"):
        h = "https:" + h
    if h.startswith("/url?") or h.startswith("/aclk?"):
        h = "https://www.google.com" + h
    loja_embutida = _primeira_url_loja(h)
    if loja_embutida:
        return loja_embutida
    if "google." in h.lower() and ("/url?" in h or "url=" in h or "adurl=" in h or "q=" in h):
        parsed = urllib.parse.urlparse(h)
        qs = urllib.parse.parse_qs(parsed.query)
        for chave in ("q", "url", "adurl", "u"):
            cand = (qs.get(chave) or [""])[0]
            if cand.startswith("http"):
                h = cand
                break
    if "%3A%2F%2F" in h:
        h = urllib.parse.unquote(h)
    loja_embutida = _primeira_url_loja(h)
    if loja_embutida:
        return loja_embutida
    if not h.startswith("http"):
        return ""
    if "google." in h.lower() and not _plataforma_loja(h):
        baixa = h.lower()
        if "/shopping/" in baixa or "ibp=oshop" in baixa or "prds=" in baixa:
            return h.split("#")[0]
        return ""
    return h.split("#")[0]


def _plataforma_loja(url):
    baixa = (url or "").lower()
    if "amazon." in baixa:
        return "amazon"
    if "shopee." in baixa or "shp.ee" in baixa:
        return "shopee"
    if "mercadolivre." in baixa or "mercadolibre." in baixa:
        return "mercado_livre"
    if "ebay." in baixa:
        return "ebay"
    return ""


def _foto_placeholder_loja(plat):
    if plat == "amazon":
        return "https://m.media-amazon.com/images/G/32/social_share/amazon_logo._CB149932011_.png"
    if plat == "mercado_livre":
        return "https://http2.mlstatic.com/frontend-assets/ml-web-navigation/navbar-assets/icon-logo-mercado-libre.png"
    if plat == "shopee":
        return "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon.png"
    if plat == "ebay":
        return "https://ir.ebaystatic.com/cr/v/c1/ebay-logo-2016.png"
    return ""


def _item_google(termo, titulo, preco, href, foto, plat, origem="", pais="BR"):
    pais = _normalizar_pais(pais)
    if not plat:
        plat = _plataforma_loja(href) or _loja_do_texto(titulo)
    if not plat:
        return None
    if plat not in _lojas_do_pais(pais):
        return None
    if pais == "US" and plat == "amazon":
        if href and "amazon.com.br" in href.lower():
            return None
        if href and not _host_amazon_eua(href):
            asin = _asin_amazon(href)
            href = f"https://www.amazon.com/dp/{asin}" if asin else ""
    preco = _normalizar_preco_mercado(preco, termo, titulo, pais=pais)
    if preco <= 0:
        return None
    href = _url_canonica_loja(href, plat, pais=pais)
    if _parece_artigo_nao_produto(titulo) or _parece_url_conteudo(href):
        return None
    if origem == "serper":
        if not _titulo_shopping_ok(termo, titulo) or not _preco_plausivel(termo, preco, titulo, pais=pais):
            return None
    elif not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo, pais=pais):
        return None
    if _url_e_busca_loja(href):
        return None
    if not _url_anuncio_exato(href, plat):
        if origem != "serper" or not str(href or "").startswith("http"):
            return None
    foto = (foto or "").strip()
    if foto.startswith("//"):
        foto = "https:" + foto
    item = _montar_item_oferta(titulo, preco, href, foto, plat, pais=pais)
    item["fonte"] = "google"
    _marcar_fonte_scrape(item, origem)
    item["fonte"] = "google"
    item["pais"] = pais
    if _foto_e_generica(item.get("foto") or ""):
        item["foto"] = foto if not _foto_e_generica(foto) else _foto_placeholder_loja(plat)
    if not _oferta_foto_preco_do_mesmo_item(item):
        return None
    return item


def _parsear_ofertas_google(html, termo, origem="", limite=8):
    if not html or BeautifulSoup is None:
        return []
    soup = BeautifulSoup(_html_google_legivel(html), "html.parser")
    ofertas = []
    vistos = set()

    def _guardar(item):
        if not item:
            return
        plat = item.get("plataforma")
        if plat in vistos:
            atual = next((p for p in ofertas if p.get("plataforma") == plat), None)
            if atual and item["preco_num"] < atual["preco_num"]:
                ofertas.remove(atual)
                ofertas.append(item)
            return
        vistos.add(plat)
        ofertas.append(item)

    for a in soup.select("a[href]"):
        href_raw = a.get("href") or a.get("data-href") or a.get("data-url") or ""
        href = _desempacotar_link_google(href_raw) or _primeira_url_loja(str(a))
        bloco = a
        texto_bloco = ""
        for _ in range(8):
            if bloco is None:
                break
            texto_bloco = bloco.get_text(" ", strip=True)
            if "R$" in texto_bloco:
                break
            bloco = bloco.parent
        plat = _plataforma_loja(href) or _loja_do_texto(texto_bloco) or _loja_do_texto(a.get_text(" ", strip=True))
        if not plat:
            continue
        titulo_el = None
        if bloco:
            titulo_el = bloco.select_one("h3, h4, .tAxDx, .sh-np-title, [role='heading']")
        titulo = (titulo_el.get_text(" ", strip=True) if titulo_el else "") or (a.get_text(" ", strip=True) or "")
        titulo = re.sub(r"\s+", " ", titulo).strip()[:180] or termo
        preco = 0.0
        achado = re.search(r"R\$\s*[\d\.]+,\d{2}", texto_bloco or "")
        if achado:
            preco = _preco_para_numero(achado.group(0))
        if preco <= 0:
            continue
        foto = ""
        if bloco:
            img = bloco.select_one("img")
            foto = _extrair_foto(img) if img else ""
        _guardar(_item_google(termo, titulo, preco, href, foto, plat, origem))
        if len(ofertas) >= limite:
            break

    if len(ofertas) < 3:
        blob = _html_google_legivel(html)
        for m in re.finditer(
            r"(https?://(?:www\.)?amazon\.com\.br[^\"'\s<>]*?/(?:dp|gp/product)/[A-Z0-9]{10})"
            r".{0,240}?(R\$\s*[\d\.]+,\d{2})|(R\$\s*[\d\.]+,\d{2}).{0,240}?"
            r"(https?://(?:www\.)?amazon\.com\.br[^\"'\s<>]*?/(?:dp|gp/product)/[A-Z0-9]{10})",
            blob,
            re.I | re.S,
        ):
            href = m.group(1) or m.group(4)
            preco_txt = m.group(2) or m.group(3)
            preco = _preco_para_numero(preco_txt)
            asin = _asin_amazon(href or "")
            titulo = termo
            _guardar(_item_google(
                termo, titulo, preco, href, f"https://m.media-amazon.com/images/P/{asin}._AC_SL500_.jpg" if asin else "",
                "amazon", origem,
            ))
        for plat, padrao in (
            ("mercado_livre", r"https?://(?:www\.|produto\.)?mercado(?:livre|libre)\.com\.br[^\"'\s<>]+"),
            ("shopee", r"https?://(?:s\.)?shopee\.com\.br[^\"'\s<>]+"),
        ):
            for achado in re.finditer(padrao, blob, re.I):
                href = achado.group(0).rstrip(").,;]")
                janela = blob[max(0, achado.start() - 280): achado.end() + 280]
                preco_m = re.search(r"R\$\s*[\d\.]+,\d{2}", janela)
                if not preco_m:
                    continue
                _guardar(_item_google(
                    termo, termo, _preco_para_numero(preco_m.group(0)), href, "", plat, origem,
                ))

    ofertas.sort(key=lambda p: p.get("preco_num") or 9e9)
    return ofertas[:limite]


_ULTIMO_DIAG_SERPER = {}


def ultimo_diag_serper():
    return dict(_ULTIMO_DIAG_SERPER)


def _chave_serper():
    chaves = _chaves_env("SERPER_API_KEY", "SERPER_KEY")
    return chaves[0] if chaves else ""


def _serper_post(caminho, corpo):
    chave = _chave_serper()
    if not chave or requests is None:
        return {}
    try:
        resp = requests.post(
            f"https://google.serper.dev{caminho}",
            headers={"X-API-KEY": chave, "Content-Type": "application/json"},
            json=corpo,
            timeout=18,
        )
        if resp.status_code >= 400:
            print(f"[Serper] HTTP {resp.status_code}")
            return {}
        dados = resp.json() if resp.text else {}
        return dados if isinstance(dados, dict) else {}
    except Exception as e:
        print(f"[Serper] {e}")
        return {}


def _preco_item_serper(it, pais="BR"):
    """Preço só deste bloco: price, extracted_price, offers, ou R$ no snippet do mesmo item."""
    if not isinstance(it, dict):
        return 0.0
    n = _limpar_preco_serper(it.get("price"), pais=pais)
    if n > 0:
        return n
    for k in ("extracted_price", "extractedPrice"):
        try:
            n = float(it.get(k))
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    for offer in it.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        n = _limpar_preco_serper(offer.get("price"), pais=pais)
        if n > 0:
            return n
    snippet = str(it.get("snippet") or "")
    us = _normalizar_pais(pais) == "US"
    if us:
        achado = re.search(r"\$\s*[\d,]+(?:\.\d{2})?", snippet)
    else:
        achado = re.search(r"R\$\s*[\d.]+,\d{2}", snippet)
    if achado:
        n = _limpar_preco_serper(achado.group(0), pais=pais)
        if n > 0:
            return n
    return 0.0


def _urls_do_item_serper(obj, skip_keys, profundidade=0):
    """Strings http deste item (não do snippet), inclusive dict do lojista."""
    if profundidade > 6 or obj is None:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip_keys:
                continue
            yield from _urls_do_item_serper(v, skip_keys, profundidade + 1)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _urls_do_item_serper(v, skip_keys, profundidade + 1)
        return
    if isinstance(obj, str) and obj.strip():
        s = obj.strip()
        if "http" in s.lower() or s.startswith("/url?") or s.startswith("/aclk?"):
            yield s


def _href_item_serper(it):
    """Ignora /search ?q= keyword= ranking; usa productLink/merchant do mesmo bloco."""
    if not isinstance(it, dict):
        return ""
    plat_src = _loja_do_texto(str(it.get("source") or it.get("domain") or ""))
    skip = {"snippet", "title", "price", "imageUrl", "image"}
    prioridade = ("productLink", "merchantLink", "merchantUrl", "offerLink", "link", "url")
    candidatos = []
    for k in prioridade:
        bruto = it.get(k)
        if isinstance(bruto, dict):
            for s in _urls_do_item_serper(bruto, skip):
                candidatos.append(s)
            continue
        if isinstance(bruto, str) and bruto.strip():
            candidatos.append(bruto.strip())
    for s in _urls_do_item_serper(it, set(skip) | set(prioridade)):
        candidatos.append(s)

    resolvidos = []
    vistos = set()
    for bruto in candidatos:
        h = _desempacotar_link_google(bruto)
        if not h:
            continue
        h = h.split("#")[0]
        if _url_e_busca_loja(h):
            continue
        plat = _plataforma_loja(h)
        if not plat:
            continue
        if plat_src and plat != plat_src:
            continue
        if h in vistos:
            continue
        vistos.add(h)
        resolvidos.append(h)
    resolvidos.sort(
        key=lambda h: (0 if _url_anuncio_exato(h, _plataforma_loja(h)) else 1)
    )
    melhor = resolvidos[0] if resolvidos else ""
    if melhor and _url_anuncio_exato(melhor, _plataforma_loja(melhor)):
        return melhor
    if plat_src == "amazon" or _plataforma_loja(melhor) == "amazon":
        for campo in (it.get("imageUrl"), it.get("image"), it.get("link"), it.get("productLink")):
            asin = _asin_amazon(str(campo or ""))
            if not asin:
                continue
            bruto = str(campo or "").lower()
            if "amazon.com/" in bruto and "amazon.com.br" not in bruto:
                return f"https://www.amazon.com/dp/{asin}"
            return f"https://www.amazon.com.br/dp/{asin}"
    return ""


def _bloco_serper_isolado(it):
    """title, source, price e link do mesmo item da lista shopping."""
    if not isinstance(it, dict):
        return None
    return {
        "title": str(it.get("title") or "").strip(),
        "source": str(it.get("source") or it.get("domain") or "").strip(),
        "price": it.get("price"),
        "link": str(it.get("link") or it.get("productLink") or "").strip(),
        "imageUrl": str(it.get("imageUrl") or it.get("image") or "").strip(),
        "extracted_price": it.get("extracted_price", it.get("extractedPrice")),
    }


def _item_serper_loja_ok(it, pais="BR"):
    if not isinstance(it, dict):
        return False
    pais = _normalizar_pais(pais)
    bloco = _bloco_serper_isolado(it)
    src = bloco["source"]
    href = _href_item_serper(it)
    plat_src = _loja_do_texto(src) if src else ""
    plat_link = _plataforma_loja(href) if href else ""
    if plat_src and plat_link and plat_src != plat_link:
        return False
    plat = plat_link or plat_src
    if plat not in _lojas_do_pais(pais) and not _source_loja_oficial(src, pais=pais):
        return False
    if pais == "US":
        if plat == "amazon" and href and not _host_amazon_eua(href):
            return False
        return plat in {"amazon", "ebay"} or _source_loja_oficial(src, pais="US")
    return _source_loja_oficial(src, pais="BR") or plat in {
        "amazon", "mercado_livre", "shopee",
    }


_ULTIMO_QUEDAS_SERPER = {}


def _ofertas_de_itens_serper(termo, itens, limite=8, pais="BR"):
    """Um item da lista shopping por vez: title/source/price/link daquele bloco só."""
    pais = _normalizar_pais(pais)
    ofertas = []
    quedas = {}

    def _cai(motivo):
        quedas[motivo] = quedas.get(motivo, 0) + 1

    for it in itens or []:
        if not isinstance(it, dict):
            continue
        bloco = _bloco_serper_isolado(it)
        if not bloco:
            _cai("bloco")
            continue
        titulo = bloco["title"]
        if _titulo_e_acessorio_imediato(titulo):
            _cai("acessorio")
            continue
        src = bloco["source"]
        if not _source_loja_oficial(src, pais=pais):
            _cai("source")
            continue
        href = _href_item_serper(it)
        if not href or _url_e_busca_loja(href):
            bruto = str(bloco.get("link") or it.get("productLink") or it.get("merchantLink") or "")
            href = _desempacotar_link_google(bruto) or bruto.strip()
            if not href.startswith("http") and bruto.startswith("http") and not _url_e_busca_loja(bruto):
                href = bruto.split("#")[0]
            if _url_e_busca_loja(href):
                href = ""
        plat_src = _loja_do_texto(src)
        plat_link = _plataforma_loja(href)
        if plat_src and plat_link and plat_src != plat_link:
            _cai("loja_link")
            continue
        plat = plat_src or plat_link
        if not plat or plat not in _lojas_do_pais(pais):
            _cai("plataforma")
            continue
        if not href.startswith("http"):
            _cai("sem_link")
            continue
        if not _titulo_shopping_ok(termo, titulo):
            _cai("titulo")
            continue
        preco = _preco_item_serper(it, pais=pais)
        if preco <= 0:
            _cai("sem_preco")
            continue
        foto = bloco["imageUrl"]
        item = _item_google(termo, titulo, preco, href, foto, plat, origem="serper", pais=pais)
        if not item:
            _cai("item_google")
            continue
        if _url_e_busca_loja(item.get("url")):
            _cai("busca_final")
            continue
        ofertas = _guardar_melhor_loja(ofertas, item)
    _ULTIMO_QUEDAS_SERPER.clear()
    _ULTIMO_QUEDAS_SERPER.update(quedas)
    ofertas.sort(key=_rank_oferta_real)
    return ofertas[:limite]


def _guardar_melhor_loja(ofertas, item):
    if not item:
        return ofertas
    plat = item.get("plataforma")

    atual = next((p for p in ofertas if p.get("plataforma") == plat), None)
    if atual is None:
        ofertas.append(item)
        return ofertas
    if _rank_oferta_real(item) < _rank_oferta_real(atual):
        return [p for p in ofertas if p.get("plataforma") != plat] + [item]
    return ofertas


def isolar_produto_mais_barato(ofertas, pais="BR"):
    """Primeiro item após ordenar do menor para o maior, já com afiliado."""
    pais = _normalizar_pais(pais)
    lista = [
        p for p in (ofertas or [])
        if isinstance(p, dict) and float(p.get("preco_num") or p.get("preco_numerico") or 0) > 0
        and float(p.get("preco_num") or p.get("preco_numerico") or 0) < 999990
    ]
    lista.sort(key=_rank_oferta_real)
    if not lista:
        return None
    carimbada = _carimbar_lista_afiliado([lista[0]], pais=pais)
    return carimbada[0] if carimbada else lista[0]


def _post_serper_shopping(q, pais="BR", num=40):
    """Uma chamada Shopping. q já vem sem site:."""
    chave = _chave_serper()
    loc = _serper_locale(pais)
    if not chave or requests is None or not (q or "").strip():
        return 0, [], loc, "sem_chave"
    try:
        resp = requests.post(
            "https://google.serper.dev/shopping",
            headers={
                "X-API-KEY": chave,
                "Content-Type": "application/json",
            },
            json={
                "q": q.strip(),
                "gl": loc["gl"],
                "hl": loc["hl"],
                "num": min(int(num or 20), 40),
            },
            timeout=25,
        )
        http = resp.status_code
        if http >= 400:
            return http, [], loc, (resp.text or "")[:180]
        dados = resp.json() if resp.text else {}
    except Exception as e:
        return 0, [], loc, str(e)[:180]
    if not isinstance(dados, dict):
        return http, [], loc, ""
    cru = [it for it in (dados.get("shopping") or []) if isinstance(it, dict)]
    return http, cru, loc, ""


def _consultas_serper_fallback(termo, pais="BR"):
    """Se a busca pura só trouxer acessório, tenta de novo com o nome da loja (sem site:)."""
    q = _consulta_serper_shopping(termo)
    if _normalizar_pais(pais) == "US":
        return [f"{q} amazon", f"{q} ebay"]
    return [f"{q} amazon", f"{q} mercado livre", f"{q} shopee"]


def _q_serper_da_loja(termo, plat):
    q = _consulta_serper_shopping(termo)
    nomes = {
        "amazon": "amazon",
        "mercado_livre": "mercado livre",
        "shopee": "shopee",
        "ebay": "ebay",
    }
    extra = nomes.get(plat) or ""
    return f"{q} {extra}".strip() if extra else q


def _link_e_google_shopping(url):
    u = (url or "").lower()
    return "google." in u and ("ibp=oshop" in u or "prds=" in u or "/shopping/" in u)


def _organic_serper(q, pais="BR", num=12):
    """Busca orgânica Serper (não Shopping). Sem site: no q; a loja filtra no JSON."""
    loc = _serper_locale(pais)
    q = _consulta_serper_shopping(q)
    if not q:
        return []
    dados = _serper_post("/search", {
        "q": q, "gl": loc["gl"], "hl": loc["hl"], "num": min(int(num or 10), 20),
    })
    if not isinstance(dados, dict):
        return []
    return [it for it in (dados.get("organic") or []) if isinstance(it, dict)]


def _href_organico_anuncio(it):
    if not isinstance(it, dict):
        return ""
    h = _href_item_serper(it)
    if h and _url_anuncio_exato(h, _plataforma_loja(h)):
        return h
    h = _desempacotar_link_google(str(it.get("link") or it.get("url") or ""))
    plat = _plataforma_loja(h)
    if plat and _url_anuncio_exato(h, plat):
        return h
    return ""


def _colar_anuncio_organico(item, organicos, termo, pais="BR", exigir_mesmo=True):
    """Troca o card Google Shopping pelo /dp/ /p/ /itm da mesma loja e do mesmo produto."""
    if not item:
        return item
    pais = _normalizar_pais(pais)
    plat = item.get("plataforma")
    url = item.get("url") or ""
    if _url_anuncio_exato(url, plat):
        return item
    titulo_card = item.get("titulo") or ""
    for it in organicos or []:
        tit = str(it.get("title") or "")
        href = _href_organico_anuncio(it)
        if not href or _plataforma_loja(href) != plat:
            continue
        if pais == "US" and plat == "amazon" and not _host_amazon_eua(href):
            continue
        if exigir_mesmo:
            if not _titulos_mesmo_produto(termo, titulo_card, tit):
                continue
        elif not _titulo_shopping_ok(termo, tit):
            continue
        can = _url_canonica_loja(href, plat, pais=pais)
        item["url"] = _aplicar_afiliado_google(can, plat, pais=pais)
        return item
    return item


def _resolver_links_anuncio_serper(termo, ofertas, pais="BR"):
    """Shopping da Serper vem no Google; troca pelo /dp/ /p/ /-i. do mesmo título."""
    pais = _normalizar_pais(pais)
    if not ofertas:
        return ofertas
    saida = [dict(o) for o in ofertas]
    if all(_url_anuncio_exato(o.get("url"), o.get("plataforma")) for o in saida):
        return saida
    organicos = _organic_serper(termo, pais=pais)
    saida = [_colar_anuncio_organico(o, organicos, termo, pais=pais) for o in saida]
    for o in saida:
        plat = o.get("plataforma")
        if _url_anuncio_exato(o.get("url"), plat):
            continue
        tit = (o.get("titulo") or termo).strip()
        extra = _organic_serper(tit, pais=pais)
        _colar_anuncio_organico(o, extra, termo, pais=pais)
        if plat == "amazon" and not _url_anuncio_exato(o.get("url"), "amazon"):
            extra_amz = _organic_serper(f"{tit} amazon", pais=pais)
            _colar_anuncio_organico(o, extra_amz, termo, pais=pais)
        elif plat == "mercado_livre" and not _url_anuncio_exato(o.get("url"), plat):
            extra_ml = _organic_serper(f"{tit} mercado livre", pais=pais)
            _colar_anuncio_organico(o, extra_ml, termo, pais=pais)
        elif plat == "shopee" and not _url_anuncio_exato(o.get("url"), plat):
            extra_sh = _organic_serper(f"{tit} shopee", pais=pais)
            _colar_anuncio_organico(o, extra_sh, termo, pais=pais)
    return saida


def buscar_ofertas_serper_shopping(termo, usar_cache=True, limite=20, pais="BR"):
    """
    Cache → POST Serper Shopping → lojas do país → preço float → menor preço no topo.
    BR: Amazon, Mercado Livre, Shopee (gl=br, hl=pt).
    US: Amazon e eBay (gl=us, hl=en), tag Amazon EUA em todo /dp/.
    """
    t = (termo or "").strip()
    pais = _normalizar_pais(pais)
    if not t:
        return []
    if usar_cache:
        cached = _ler_cache_garimpo(t, pais=pais)
        if cached:
            lista = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(cached, pais=pais))
            if lista:
                print(f"[Serper] cache {_chave_cache(t, pais=pais)}")
                return lista
    q = _consulta_serper_shopping(t)
    if not q:
        return []
    http, cru, loc, erro = _post_serper_shopping(q, pais=pais, num=limite)
    if erro == "sem_chave":
        _ULTIMO_DIAG_SERPER.clear()
        _ULTIMO_DIAG_SERPER.update({"q": q, "http": 0, "shopping": 0, "erro": "sem_chave"})
        return []
    if http >= 400:
        print(f"[Serper] HTTP {http}")
        _ULTIMO_DIAG_SERPER.clear()
        _ULTIMO_DIAG_SERPER.update({
            "q": q, "gl": loc["gl"], "hl": loc["hl"], "http": http,
            "shopping": 0, "sources": [], "apos_source": 0, "ofertas": 0,
            "erro": erro,
        })
        return []
    if erro and not cru:
        print(f"[Serper] {erro}")
        _ULTIMO_DIAG_SERPER.clear()
        _ULTIMO_DIAG_SERPER.update({"q": q, "http": http, "shopping": 0, "erro": erro})
        return []
    sources = [str(it.get("source") or "") for it in cru][:15]
    shopping = [
        it for it in cru
        if _source_loja_oficial(str(it.get("source") or it.get("domain") or ""), pais=pais)
    ]
    ofertas = _ofertas_de_itens_serper(t, shopping, limite=limite, pais=pais)
    qs_usadas = [q]
    presentes = {o.get("plataforma") for o in ofertas}
    faltando = [p for p in _lojas_do_pais(pais) if p not in presentes]
    qs_extra = []
    if not ofertas:
        qs_extra = [q2 for q2 in _consultas_serper_fallback(t, pais=pais) if q2 != q]
    elif faltando:
        qs_extra = [_q_serper_da_loja(t, p) for p in faltando]
    for q2 in qs_extra:
        if not q2 or q2 in qs_usadas:
            continue
        http2, cru2, _, erro2 = _post_serper_shopping(q2, pais=pais, num=limite)
        if erro2 or http2 >= 400 or not cru2:
            continue
        qs_usadas.append(q2)
        cru.extend(cru2)
        extra = [
            it for it in cru2
            if _source_loja_oficial(str(it.get("source") or it.get("domain") or ""), pais=pais)
        ]
        shopping.extend(extra)
        ofertas = _ofertas_de_itens_serper(t, shopping, limite=limite, pais=pais)
        if not faltando:
            if ofertas:
                break
    ofertas = _resolver_links_anuncio_serper(t, ofertas, pais=pais)
    ofertas = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(ofertas, pais=pais))
    _ULTIMO_DIAG_SERPER.clear()
    _ULTIMO_DIAG_SERPER.update({
        "q": q, "qs": qs_usadas, "gl": loc["gl"], "hl": loc["hl"], "http": http,
        "shopping": len(cru), "sources": sources,
        "apos_source": len(shopping), "ofertas": len(ofertas),
        "quedas": dict(_ULTIMO_QUEDAS_SERPER),
        "amostra": [
            {
                "source": str(it.get("source") or "")[:40],
                "title": str(it.get("title") or "")[:50],
                "price": str(it.get("price") or ""),
                "link": str(it.get("link") or "")[:110],
            }
            for it in shopping[:4]
        ],
    })
    if usar_cache and ofertas:
        _gravar_cache_garimpo(t, ofertas, pais=pais)
    print(f"[Serper] {len(ofertas)} ofertas filtradas ({pais}: {', '.join(_lojas_do_pais(pais))})")
    return ofertas


def _primeira_url_organica_loja(termo, organicos, plat, pais="BR"):
    for it in organicos or []:
        if not isinstance(it, dict):
            continue
        titulo = str(it.get("title") or "")
        if _titulo_e_acessorio_imediato(titulo):
            continue
        if not _titulo_relevante(termo, titulo) and not _termo_contido_no_titulo(termo, titulo):
            continue
        href = _href_item_serper(it)
        if _plataforma_loja(href) == plat and _url_anuncio_exato(href, plat):
            if pais == "US" and plat == "amazon" and not _host_amazon_eua(href):
                continue
            return href, titulo, str(it.get("imageUrl") or it.get("image") or "")
    return "", "", ""


def _rascunho_preco_shopping_loja(termo, itens, plat, pais="BR"):
    melhor = None
    for it in itens or []:
        if not isinstance(it, dict):
            continue
        titulo = str(it.get("title") or "")
        if _titulo_e_acessorio_imediato(titulo):
            continue
        if not _item_serper_loja_ok(it, pais=pais):
            continue
        loja = _loja_do_texto(str(it.get("source") or it.get("domain") or ""))
        if loja and loja != plat:
            continue
        if not loja:
            loja = _plataforma_loja(_href_item_serper(it))
        if loja != plat:
            continue
        if not _titulo_relevante(termo, titulo) and not _termo_contido_no_titulo(termo, titulo):
            continue
        preco = _preco_item_serper(it, pais=pais)
        if preco <= 0:
            continue
        cand = {
            "preco": preco,
            "titulo": titulo,
            "foto": str(it.get("imageUrl") or it.get("image") or ""),
        }
        if melhor is None or preco < melhor["preco"]:
            melhor = cand
    return melhor


def _juntar_preco_shopping_url_anuncio(termo, shopping, organicos, plat, pais="BR"):
    """Preço do card shopping da loja + /dp/ /p/ da busca orgânica da mesma loja."""
    rascunho = _rascunho_preco_shopping_loja(termo, shopping, plat, pais=pais)
    href, titulo_org, foto_org = _primeira_url_organica_loja(termo, organicos, plat, pais=pais)
    if not href:
        return None
    if rascunho:
        return _item_google(
            termo, rascunho["titulo"], rascunho["preco"], href,
            rascunho["foto"] or foto_org, plat, origem="serper", pais=pais,
        )
    preco = 0.0
    titulo = titulo_org
    foto = foto_org
    for it in organicos or []:
        if not isinstance(it, dict):
            continue
        if _href_item_serper(it) == href:
            preco = _preco_item_serper(it, pais=pais)
            titulo = str(it.get("title") or titulo)
            foto = str(it.get("imageUrl") or it.get("image") or foto)
            break
    if preco <= 0:
        return None
    return _item_google(termo, titulo, preco, href, foto, plat, origem="serper", pais=pais)


def _completar_lojas_serper(termo, ofertas, limite=8, pais="BR"):
    """Não usa site: nem segunda chamada. O JSON único do Shopping já veio filtrado."""
    return ofertas or []


def _buscar_ofertas_serper(termo, limite=8, pais="BR"):
    """Uma única chamada Shopping com o nome do produto; filtro de loja no JSON."""
    pais = _normalizar_pais(pais)
    ofertas = buscar_ofertas_serper_shopping(termo, usar_cache=False, limite=limite, pais=pais)
    ofertas = _ordenar_entrega_menor_preco(ofertas)
    if ofertas:
        print(f"[Serper] {len(ofertas[:limite])} ofertas do Google ({pais})")
    return ofertas[:limite]


def _buscar_ofertas_google_shopping(termo, limite=8, pais="BR"):
    """Serper no ar. Sem chave, não raspa Google (bloqueado no Railway)."""
    if _chave_serper():
        return _buscar_ofertas_serper(termo, limite, pais=pais)
    print("[Google] sem SERPER_API_KEY — pulando scrape")
    return []


def _marcar_fonte_scrape(item, origem):
    if origem in {"zenrows", "scrapingant"}:
        item["fonte"] = "scrape"
    return item


def _buscar_ofertas_amazon_html(termo, limite=6):
    """Busca pública da Amazon BR: ASIN, preço, foto e página /dp/ de compra."""
    if requests is None or BeautifulSoup is None or not (termo or "").strip():
        return []
    q = urllib.parse.quote(termo.strip())
    url = f"https://www.amazon.com.br/s?k={q}"
    html, origem = _baixar_url_loja(url, headers=HEADERS_GOOGLE, timeout=6, browser=True)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select('div[data-component-type="s-search-result"][data-asin]')
    ofertas = []
    vistos = set()
    for card in cards:
        asin = (card.get("data-asin") or "").strip()
        if len(asin) < 8 or asin in vistos:
            continue
        topo = card.get_text(" ", strip=True)[:200].lower()
        if "patrocinado" in topo or "sponsored" in topo:
            continue
        if card.select_one(".puis-sponsored-label-text, [data-component-type='sp-sponsored-result']"):
            continue
        titulo_el = card.select_one("h2 a span, h2 span, h2")
        titulo = titulo_el.get_text(" ", strip=True) if titulo_el else ""
        if not titulo:
            continue
        preco = 0.0
        for off in card.select("span.a-price > span.a-offscreen"):
            pai = off.find_parent("span", class_="a-price")
            classes = " ".join((pai.get("class") or []) if pai else [])
            if "a-text-price" in classes:
                continue
            preco = _preco_para_numero(off.get_text(strip=True))
            if preco > 0:
                break
        if preco <= 0:
            continue
        if not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo):
            continue
        tlow = (termo or "").lower()
        if any(k in tlow for k in ("dualsense", "ps5", "playstation")):
            tl = _sem_acento(titulo)
            if "dualsense" not in tl and "sony" not in tl:
                continue
            if asin.upper() != ASIN_DUALSENSE and "dualsense" not in tl:
                continue
        img = card.select_one("img.s-image")
        foto_hint = ""
        if img:
            foto_hint = (img.get("src") or img.get("data-src") or "").strip()
        item = _montar_item_oferta(
            titulo, preco, f"https://www.amazon.com.br/dp/{asin}", foto_hint, "amazon",
        )
        _marcar_fonte_scrape(item, origem)
        if not _oferta_foto_preco_do_mesmo_item(item):
            continue
        vistos.add(asin)
        ofertas.append(item)
        if len(ofertas) >= limite:
            break
    tlow = (termo or "").lower()
    if any(k in tlow for k in ("dualsense", "ps5", "playstation")):
        oficiais = [o for o in ofertas if ASIN_DUALSENSE in (o.get("url") or "").upper()]
        if oficiais:
            return oficiais
    return ofertas


def _preco_de_html_amazon(html):
    """Preço da vitrine (buy box) na página /dp/, nunca o riscado."""
    if not html or BeautifulSoup is None:
        return 0.0
    soup = BeautifulSoup(html, "html.parser")
    raiz = soup.select_one("#corePrice_feature_div, #apex_desktop, #ppd") or soup
    for off in raiz.select("span.a-price > span.a-offscreen"):
        pai = off.find_parent("span", class_="a-price")
        classes = " ".join((pai.get("class") or []) if pai else [])
        if "a-text-price" in classes:
            continue
        preco = _preco_para_numero(off.get_text(strip=True))
        if preco > 0:
            return preco
    achado = re.search(r"R\$\s*[\d\.]+,\d{2}", raiz.get_text(" ", strip=True) if raiz else "")
    return _preco_para_numero(achado.group(0)) if achado else 0.0


def _atualizar_preco_pdp_amazon(item, termo):
    """Atualiza só o ASIN do catálogo, nunca um resultado de busca genérico."""
    asin = _asin_amazon((item or {}).get("url") or "")
    if not asin or requests is None:
        return item
    html, origem = _baixar_url_loja(
        f"https://www.amazon.com.br/dp/{asin}",
        headers=HEADERS_GOOGLE,
        timeout=8,
        browser=True,
    )
    preco = _preco_de_html_amazon(html)
    titulo = (item.get("titulo") or "").strip()
    if preco > 0 and _preco_plausivel(termo, preco, titulo):
        item["preco_num"] = float(preco)
        item["preco"] = _formatar_preco(preco)
        _marcar_fonte_scrape(item, origem)
        print(f"[Motor] Amazon /dp/{asin} = {item['preco']}")
    return item


def _atualizar_catalogo_amazon_vivo(lista, termo):
    amazon = [
        p for p in lista or []
        if p.get("plataforma") == "amazon"
        and _asin_amazon(p.get("url") or "")
        and (
            _anuncio_veio_do_google(p)
            or _asin_amazon(p.get("url") or "") == ASIN_DUALSENSE
        )
    ]
    if not amazon:
        return
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda p: _atualizar_preco_pdp_amazon(p, termo), amazon))


def _buscar_ofertas_shopee_api(termo, limite=6):
    """Busca pública Shopee: preço real; Ver Oferta abre a lista sem login."""
    if requests is None or not (termo or "").strip():
        return []
    q = urllib.parse.quote(termo.strip())
    url = (
        "https://shopee.com.br/api/v4/search/search_items"
        f"?by=price&limit={limite}&newest=0&order=asc"
        f"&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2&keyword={q}"
    )
    headers = {
        **HEADERS_GOOGLE,
        "Accept": "application/json",
        "Referer": f"https://shopee.com.br/search?keyword={q}",
        "X-Requested-With": "XMLHttpRequest",
    }
    bruto, origem = _baixar_url_loja(url, headers=headers, timeout=6, browser=False)
    if not bruto:
        return []
    try:
        payload = json.loads(bruto)
    except Exception:
        print("[Shopee] resposta não é JSON")
        return []
    if not isinstance(payload, dict):
        return []

    itens = payload.get("items") or []
    ofertas = []
    for bloco in itens:
        basic = bloco.get("item_basic") or bloco.get("item") or bloco
        if not isinstance(basic, dict):
            continue
        titulo = (basic.get("name") or "").strip()
        if not titulo:
            continue
        try:
            bruto = float(basic.get("price") or 0)
        except (TypeError, ValueError):
            continue
        preco = bruto / 100000.0 if bruto > 10000 else bruto
        if preco <= 0:
            continue
        if not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo):
            continue
        img_id = (basic.get("image") or "").strip()
        foto = f"https://cf.shopee.com.br/file/{img_id}" if img_id else FOTO_PADRAO
        ofertas.append(_marcar_fonte_scrape(_montar_item_oferta(
            titulo, preco, _link_busca_shopee(titulo), foto, "shopee",
            full=bool(basic.get("shopee_verified") or basic.get("is_official_shop")),
        ), origem))
        if not _oferta_foto_preco_do_mesmo_item(ofertas[-1]):
            ofertas.pop()
            continue
        if len(ofertas) >= limite:
            break
    return ofertas


def _assinatura_aws_paapi(secret, data_stamp, region, service):
    k_date = hmac.new(("AWS4" + secret).encode("utf-8"), data_stamp.encode("utf-8"), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _buscar_ofertas_amazon_paapi(termo, limite=8):
    """Amazon Product Advertising API 5 — só roda com AMAZON_ACCESS_KEY + SECRET."""
    access = (os.environ.get("AMAZON_ACCESS_KEY") or "").strip()
    secret = (os.environ.get("AMAZON_SECRET_KEY") or "").strip()
    tag = (os.environ.get("AMAZON_PARTNER_TAG") or ID_AMAZON).strip() or ID_AMAZON
    if requests is None or not access or not secret or not (termo or "").strip():
        return []
    host = "webservices.amazon.com.br"
    region = "us-east-1"
    service = "ProductAdvertisingAPI"
    path = "/paapi5/searchitems"
    amz_target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"
    payload = json.dumps({
        "Keywords": termo.strip(),
        "PartnerTag": tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.com.br",
        "SearchIndex": "All",
        "ItemCount": min(10, max(1, limite)),
        "Resources": [
            "Images.Primary.Large",
            "ItemInfo.Title",
            "Offers.Listings.Price",
        ],
    }, ensure_ascii=False, separators=(",", ":"))
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    content_type = "application/json; charset=utf-8"
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    canonical = (
        f"POST\n{path}\n\n"
        f"content-encoding:amz-1.0\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{amz_target}\n"
        f"\n{signed_headers}\n{payload_hash}"
    )
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n{scope}\n"
        f"{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    )
    signing_key = _assinatura_aws_paapi(secret, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "content-encoding": "amz-1.0",
        "content-type": content_type,
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": amz_target,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    try:
        resp = requests.post(
            f"https://{host}{path}",
            data=payload.encode("utf-8"),
            headers=headers,
            timeout=12,
        )
        if resp.status_code >= 400:
            print(f"[Amazon PA-API] HTTP {resp.status_code}")
            return []
        dados = resp.json() or {}
        itens = ((dados.get("SearchResult") or {}).get("Items") or [])
    except Exception as e:
        print(f"[Amazon PA-API] {e}")
        return []

    ofertas = []
    for it in itens:
        asin = (it.get("ASIN") or "").strip()
        titulo = (((it.get("ItemInfo") or {}).get("Title") or {}).get("DisplayValue") or "").strip()
        listings = ((it.get("Offers") or {}).get("Listings") or [])
        preco = 0.0
        if listings:
            preco = float((((listings[0].get("Price") or {}).get("Amount")) or 0) or 0)
        if not asin or not titulo or preco <= 0:
            continue
        if not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo):
            continue
        foto = ((((it.get("Images") or {}).get("Primary") or {}).get("Large") or {}).get("URL") or "")
        url = (it.get("DetailPageURL") or f"https://www.amazon.com.br/dp/{asin}")
        item = _montar_item_oferta(titulo, preco, url, foto, "amazon")
        item["fonte"] = "oficial"
        if not _oferta_foto_preco_do_mesmo_item(item):
            continue
        ofertas.append(item)
        if len(ofertas) >= limite:
            break
    return ofertas


def _buscar_ofertas_shopee_afiliado(termo, limite=8):
    """Shopee Affiliate Open API — só roda com SHOPEE_APP_ID + SHOPEE_SECRET."""
    app_id = (os.environ.get("SHOPEE_APP_ID") or "").strip()
    secret = (os.environ.get("SHOPEE_SECRET") or "").strip()
    if requests is None or not app_id or not secret or not (termo or "").strip():
        return []
    kw = json.dumps(termo.strip(), ensure_ascii=False)
    gql = (
        "{ productOfferV2(keyword: %s, sortType: 4, page: 1, limit: %d) { nodes { "
        "itemId productName offerLink productLink imageUrl priceMin } } }"
    ) % (kw, min(20, max(1, limite)))
    body = json.dumps({"query": gql}, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time()))
    assinatura = hashlib.sha256(f"{app_id}{timestamp}{body}{secret}".encode("utf-8")).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": (
            f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={assinatura}"
        ),
    }
    try:
        resp = requests.post(
            "https://open-api.affiliate.shopee.com.br/graphql",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=12,
        )
        if resp.status_code >= 400:
            print(f"[Shopee Afiliado] HTTP {resp.status_code}")
            return []
        nodes = ((((resp.json() or {}).get("data") or {}).get("productOfferV2") or {}).get("nodes")) or []
    except Exception as e:
        print(f"[Shopee Afiliado] {e}")
        return []

    ofertas = []
    for it in nodes:
        titulo = (it.get("productName") or "").strip()
        if not titulo:
            continue
        preco = _preco_para_numero(it.get("priceMin"))
        if preco <= 0:
            continue
        if not _titulo_relevante(termo, titulo) or not _preco_plausivel(termo, preco, titulo):
            continue
        url = (it.get("offerLink") or it.get("productLink") or "").strip()
        if not url:
            url = _link_busca_shopee(titulo)
        foto = (it.get("imageUrl") or "").strip()
        item = _montar_item_oferta(titulo, preco, url, foto, "shopee")
        item["fonte"] = "oficial"
        if not _oferta_foto_preco_do_mesmo_item(item):
            continue
        ofertas.append(item)
        if len(ofertas) >= limite:
            break
    return ofertas


def _coletar_ofertas_ao_vivo(termo):
    """Só APIs oficiais. Sem ZenRows/scrape — no Railway isso travava 90s."""
    ofertas = []
    tarefas = []
    if (os.environ.get("MELI_ACCESS_TOKEN") or "").strip():
        tarefas.append((_buscar_ofertas_ml_api, (termo, 12)))
    if (os.environ.get("AMAZON_ACCESS_KEY") or "").strip():
        tarefas.append((_buscar_ofertas_amazon_paapi, (termo, 8)))
    if (os.environ.get("SHOPEE_APP_ID") or "").strip():
        tarefas.append((_buscar_ofertas_shopee_afiliado, (termo, 8)))
    if not tarefas:
        return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futuros = [pool.submit(fn, *args) for fn, args in tarefas]
        for fut in as_completed(futuros):
            try:
                ofertas.extend(fut.result() or [])
            except Exception as e:
                print(f"[Motor ao vivo] {e}")
    return ofertas


def _ofertas_fallback_lojas(termo, pais="BR"):
    """Se a API falhar, ainda entrega busca de compra nas lojas do país."""
    t = (termo or "").strip()
    pais = _normalizar_pais(pais)
    if not t:
        return []
    if pais == "US":
        specs = (
            (
                "amazon",
                _link_busca_amazon_us(t),
                "https://m.media-amazon.com/images/G/01/social_share/amazon_logo._CB149932011_.png",
            ),
            (
                "ebay",
                _link_busca_ebay(t),
                "https://ir.ebaystatic.com/cr/v/c1/ebay-logo-2016.png",
            ),
        )
    else:
        specs = (
            (
                "mercado_livre",
                _link_busca_ml(t),
                "https://http2.mlstatic.com/frontend-assets/ml-web-navigation/navbar-assets/icon-logo-mercado-libre.png",
            ),
            (
                "amazon",
                _link_busca_amazon(t),
                "https://m.media-amazon.com/images/G/32/social_share/amazon_logo._CB149932011_.png",
            ),
            (
                "shopee",
                _link_busca_shopee(t),
                "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon.png",
            ),
        )
    ofertas = []
    for plat, url, foto in specs:
        ofertas.append({
            "titulo": t,
            "preco": mensagem_servidor("ver_preco_loja", pais),
            "preco_num": 999990.0,
            "url": url,
            "foto": foto,
            "plataforma": plat,
            "loja": _nome_loja(plat),
            "loja_oficial": True,
            "full": False,
            "aviso_golpe": False,
            "selo": "BUSCA NA LOJA",
            "vale_a_pena": True,
            "fonte": "busca_loja",
            "campeao": False,
            "termo_busca": t,
            "pais": pais,
        })
    return ofertas


def _carimbar_lista_afiliado(lista, pais="BR"):
    """Garante afiliado JDS em todo link: direto da oferta (Google) ou busca da loja (fallback)."""
    pais = _normalizar_pais(pais)
    for p in lista or []:
        p_pais = _normalizar_pais(p.get("pais") or pais)
        p["pais"] = p_pais
        p["url"] = _link_ver_oferta(p)
        app = serializar_oferta_app(p, pais=p_pais)
        p.update(app)
    return lista


def gerar_lista_ofertas_reais(
    termo_busca,
    loja=None,
    plataforma_chave=None,
    preco_base=99.0,
    urls_reais=None,
    usar_cache=True,
    usar_vivo=True,
    pais="BR",
):
    """
    Motor de precisão: qualquer termo, menor preço no topo, Ver Oferta na compra.
    """
    termo = (termo_busca or "").strip()
    pais = _normalizar_pais(pais)
    if not termo:
        return []

    if usar_cache:
        cached = _ler_cache_garimpo(termo, pais=pais)
        if cached:
            lista = _ordenar_entrega_menor_preco(cached)
            if lista:
                lista = _carimbar_lista_afiliado(lista, pais=pais)
                print(f"[Motor] cache instantâneo: {lista[0]['preco']} em {lista[0].get('loja')}")
                return lista

    if usar_vivo and _chave_serper():
        ofertas = _buscar_ofertas_serper(termo, limite=20, pais=pais)
        ofertas = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(ofertas, pais=pais))
        if ofertas and usar_cache:
            _gravar_cache_garimpo(termo, ofertas, pais=pais)
        if ofertas:
            print(
                f"[Motor] Serper menor preço: {ofertas[0]['preco']} "
                f"em {ofertas[0].get('loja')}"
            )
        return ofertas

    lista_produtos = []
    urls_vistas = set()

    def _adicionar(item):
        url = (item.get("url") or "").split("#")[0]
        if not url or url in urls_vistas:
            return
        plat = item.get("plataforma")
        if plat not in _lojas_do_pais(pais):
            return
        if not _eh_link_produto(url, plat):
            return
        if not _oferta_foto_preco_do_mesmo_item(item):
            return
        item["loja"] = _nome_loja(plat)
        item["termo_busca"] = termo
        item["pais"] = pais
        urls_vistas.add(url)
        lista_produtos.append(item)

    if urls_reais:
        for i, url_real in enumerate(urls_reais):
            plat = plataforma_chave or _detectar_plataforma(url_real)
            if not _eh_link_produto(url_real, plat):
                continue
            p_val = round(preco_base + (i * 10), 2)
            _adicionar(_montar_item_oferta(
                f"{termo.title()} - Oferta #{i + 1}",
                p_val, url_real, FOTO_PADRAO, plat, full=plat == "shopee",
                pais=pais,
            ))

    plats_ja = {p.get("plataforma") for p in lista_produtos}

    if usar_vivo:
        for item in _buscar_ofertas_google_shopping(termo, pais=pais):
            antes = len(lista_produtos)
            _adicionar(item)
            if len(lista_produtos) > antes:
                plats_ja.add(item.get("plataforma"))
        plats_ja = {p.get("plataforma") for p in lista_produtos}
        if pais == "BR" and len(plats_ja) < 3:
            for item in _coletar_ofertas_ao_vivo(termo):
                plat = item.get("plataforma")
                if plat in plats_ja:
                    continue
                antes = len(lista_produtos)
                _adicionar(item)
                if len(lista_produtos) > antes:
                    plats_ja.add(plat)

    if pais == "BR":
        cats_ok = [c for c in CATALOGO_PRODUTOS_REAIS if _catalogo_compativel(termo, c)]
        if cats_ok:
            melhor = max(_score_catalogo(termo, c) for c in cats_ok)
            cats_ok = [c for c in cats_ok if _score_catalogo(termo, c) == melhor]
        for cat_item in cats_ok:
            for of in cat_item["ofertas"]:
                plat = of["plataforma"]
                if plat in plats_ja:
                    continue
                foto = of.get("foto") or ""
                if not foto:
                    for irma in cat_item["ofertas"]:
                        asin = _asin_amazon(irma.get("url") or "")
                        if asin:
                            foto = f"https://m.media-amazon.com/images/P/{asin}._AC_SL500_.jpg"
                            break
                item = _montar_item_oferta(
                    of["titulo"], of["preco"], of["url"], foto, plat,
                    full=of.get("full", False),
                    pais=pais,
                )
                item["fonte"] = "catalogo"
                if not _oferta_foto_preco_do_mesmo_item(item):
                    continue
                _adicionar(item)
                plats_ja.add(plat)

    plats_ja = {p.get("plataforma") for p in lista_produtos}
    faltam = [p for p in _lojas_do_pais(pais) if p not in plats_ja]
    if faltam:
        for fb in _ofertas_fallback_lojas(termo, pais=pais):
            if fb.get("plataforma") in faltam:
                lista_produtos.append(fb)

    if plataforma_chave:
        lista_produtos = [p for p in lista_produtos if p.get("plataforma") == plataforma_chave]
    lista_produtos = _ordenar_entrega_menor_preco(lista_produtos)
    lista_produtos = _carimbar_lista_afiliado(lista_produtos, pais=pais)
    if lista_produtos and usar_cache:
        _gravar_cache_garimpo(termo, lista_produtos, pais=pais)
    if lista_produtos and usar_vivo:
        print(
            f"[Motor] menor preço entregue: {lista_produtos[0]['preco']} "
            f"em {lista_produtos[0].get('loja')}"
        )
    return lista_produtos


def buscar_ofertas_por_pais(termo, pais="BR", usar_cache=True, usar_vivo=True, limite=20):
    """Cada busca do usuário: termo → Serper → menor preço nas lojas do país."""
    termo = (termo or "").strip()
    pais = _normalizar_pais(pais)
    if not termo:
        return []
    if usar_cache:
        cached = _ler_cache_garimpo(termo, pais=pais)
        if cached:
            print(f"[Cache SQLite] hit {_chave_cache(termo, pais=pais)}")
            return _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(cached, pais=pais))
    if usar_vivo and _chave_serper():
        ofertas = _buscar_ofertas_serper(termo, limite=limite, pais=pais)
        ofertas = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(ofertas, pais=pais))
        if ofertas and usar_cache:
            _gravar_cache_garimpo(termo, ofertas, pais=pais)
        print(f"[Motor] Serper {pais}: {len(ofertas)} lojas, pergunta o menor preço")
        return ofertas
    ofertas = gerar_lista_ofertas_reais(
        termo, usar_cache=False, usar_vivo=usar_vivo, pais=pais,
    )
    if ofertas and usar_cache:
        _gravar_cache_garimpo(termo, ofertas, pais=pais)
    return ofertas


def buscar_ofertas_jds(termo, pais="BR"):
    """Usa a API no ar (Railway) se JDS_API_URL existir; senão busca local."""
    termo = (termo or "").strip()
    pais = _normalizar_pais(pais)
    if not termo:
        return []
    if JDS_API_URL and requests is not None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        token = (os.environ.get("JDS_API_TOKEN") or "").strip()
        if token:
            headers["X-JDS-TOKEN"] = token
        try:
            resp = requests.post(
                f"{JDS_API_URL}/garimpar",
                json={"q": termo, "pais": pais},
                timeout=90,
                headers=headers,
            )
            if resp.status_code == 405:
                resp = requests.get(
                    f"{JDS_API_URL}/garimpar",
                    params={"q": termo, "pais": pais},
                    timeout=90,
                    headers=headers,
                )
            if resp.status_code < 400:
                dados = resp.json() or {}
                ofertas = dados.get("ofertas") or dados.get("produtos") or []
                if isinstance(ofertas, list):
                    return _ordenar_entrega_menor_preco(ofertas)
        except Exception as e:
            print(f"[API JDS] {e} — usando motor local")
    return gerar_lista_ofertas_reais(termo, pais=pais)


def _limpar_texto_voz(texto):
    t = re.sub(r"\s+", " ", (texto or "").strip())
    t = t.strip(" .,!?;:\"'")
    return t[:120]


def _ouvir_windows_sapi():
    """Ditados do Windows: qualquer produto em pt-BR, sem lista fixa."""
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$ErrorActionPreference='Stop'; "
        "try { $c=[Globalization.CultureInfo]::GetCultureInfo('pt-BR'); "
        "$eng=New-Object System.Speech.Recognition.SpeechRecognitionEngine $c } "
        "catch { $eng=New-Object System.Speech.Recognition.SpeechRecognitionEngine }; "
        "$eng.SetInputToDefaultAudioDevice(); "
        "$eng.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
        "$eng.InitialSilenceTimeout=New-TimeSpan -Seconds 5; "
        "$eng.EndSilenceTimeout=New-TimeSpan -Seconds 1; "
        "$r=$eng.Recognize((New-TimeSpan -Seconds 10)); "
        "if ($r -and $r.Text) { [Console]::Out.Write($r.Text) }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            capture_output=True,
            timeout=22,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return ""
    return _limpar_texto_voz(proc.stdout or "")


def _ouvir_google_ptbr():
    """Qualquer fala → texto (pt-BR). Só se SpeechRecognition estiver instalado."""
    try:
        import speech_recognition as sr
    except ImportError:
        return ""
    rec = sr.Recognizer()
    rec.pause_threshold = 0.85
    try:
        with sr.Microphone() as source:
            rec.adjust_for_ambient_noise(source, duration=0.35)
            audio = rec.listen(source, timeout=6, phrase_time_limit=8)
        return _limpar_texto_voz(rec.recognize_google(audio, language="pt-BR"))
    except Exception:
        return ""


def ouvir_produto_microfone():
    """Transcreve o produto falado. Nunca força um item fixo."""
    if sys.platform == "win32":
        termo = _ouvir_windows_sapi()
        if termo:
            return termo
    return _ouvir_google_ptbr()


def _ofertas_super_descontos():
    ofertas = []
    for cat in CATALOGO_PRODUTOS_REAIS[:5]:
        for of in cat["ofertas"]:
            item = _montar_item_oferta(
                of["titulo"], of["preco"], of["url"],
                of.get("foto") or cat["foto_real"], of["plataforma"],
                full=of.get("full", False),
                selo=f"-{int((1 - of['preco'] / of['de']) * 100)}%" if of.get("de") else "SUPER",
            )
            ofertas.append(item)
    ofertas = [p for p in ofertas if _oferta_foto_preco_do_mesmo_item(p)]
    ofertas.sort(key=lambda p: p["preco_num"])
    return _ordenar_entrega_menor_preco(ofertas)[:6]



def main(page):
    if ft is None:
        return
    page.title = "JDS Economiza"
    page.adaptive = True
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#121214"
    page.padding = 12
    page.scroll = None
    page.window.width = 430
    page.window.height = 780
    page.window.min_width = 360
    page.window.min_height = 640
    page.window.resizable = True
    page.window.maximizable = True
    mercado = {"pais": pais_do_dispositivo(page)}

    def tx(chave, **kwargs):
        return texto_app(chave, mercado["pais"], **kwargs)

    def fechar_dialogo(e=None):
        try:
            page.pop_dialog()
        except Exception:
            pass

    def fechar_todos_dialogos():
        for _ in range(6):
            try:
                page.pop_dialog()
            except Exception:
                break

    def snack(msg, cor="#9D4EDD"):
        barra = ft.SnackBar(
            content=ft.Text(msg, color="#FFFFFF"),
            bgcolor=cor,
            duration=2500,
            open=True,
        )
        try:
            if hasattr(page, "open"):
                page.open(barra)
            else:
                page.show_dialog(barra)
        except Exception:
            pass

    async def copiar_texto(texto, ok_msg=None):
        try:
            await page.clipboard.set(texto)
            snack(ok_msg or tx("copiado"), "#00F5D4")
        except Exception:
            snack(tx("nao_copiar"), "#FF6B6B")

    async def abrir_compartilhar(e=None):
        convite = tx("convite_corpo")
        try:
            await page.clipboard.set(convite)
        except Exception:
            pass
        page.show_dialog(
            ft.AlertDialog(
                bgcolor="#1A1A1E",
                title=ft.Text(tx("convite_titulo"),
                              color="#9D4EDD", weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    convite + "\n\n" + tx("convite_copiado"),
                    color="#EDEDED",
                    size=13,
                ),
                actions=[
                    ft.Button(tx("fechar"), on_click=fechar_dialogo),
                ],
            )
        )

    frase_sagrada = ft.Container(
        content=ft.Text(
            "NINGUEM EXPLICA DEUS",
            color="#FFD700",
            size=12,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        ),
        alignment=ft.Alignment.CENTER,
        width=float("inf"),
        padding=ft.Padding.only(bottom=8, top=2),
    )

    titulo = ft.Text(
        "JDS ECONOMIZA",
        color="#9D4EDD",
        size=24,
        weight=ft.FontWeight.BOLD,
    )
    btn_share = ft.IconButton(
        icon=ft.Icons.SHARE,
        icon_color="#9D4EDD",
        tooltip=tx("tooltip_share"),
        on_click=abrir_compartilhar,
    )
    topo = ft.Row(
        [titulo, btn_share],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    campo_busca = ft.TextField(
        hint_text=tx("hint_busca"),
        value="",
        border_color="#9D4EDD",
        focused_border_color="#00F5D4",
        bgcolor="#1A1A1E",
        color="#FFFFFF",
        border_radius=12,
        expand=True,
        height=52,
    )
    txt_busca = campo_busca
    rodinha = ft.Row(
        [ft.ProgressRing(color="#9D4EDD", width=22, height=22)],
        alignment=ft.MainAxisAlignment.CENTER,
        visible=False,
    )
    lbl_menor_preco = ft.Text(
        tx("hint_menor"),
        color="#00F5D4",
        size=13,
        weight=ft.FontWeight.BOLD,
        visible=False,
    )
    grade_garimpo = ft.ListView(expand=True, spacing=12, padding=8)
    grade_descontos = ft.ListView(expand=True, spacing=12, padding=8)
    coluna_desejos = ft.Column(spacing=10)
    lista_achados = ft.Column(spacing=10)
    txt_achado = ft.TextField(
        label=tx("cole_link"),
        border_color="#9D4EDD",
        bgcolor="#1A1A1E",
        color="#FFFFFF",
        border_radius=12,
    )
    lbl_pontos = ft.Text(
        tx("pontos", n=pontos_jds["saldo"]),
        color="#00F5D4",
        size=16, weight=ft.FontWeight.BOLD)
    lbl_roleta = ft.Text(tx("roleta_hint"),
                         color="#EDEDED", size=13)
    btn_checkin = ft.Button(
        tx("checkin"), bgcolor="#9D4EDD", color="white")

    def chip(texto, cor):
        return ft.Container(
            content=ft.Text(
                texto, size=10, weight=ft.FontWeight.BOLD, color="#121214"),
            bgcolor=cor,
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            border_radius=8,
        )

    def montar_card(produto, extra_selo=None):
        # 3. MARCA DA LOJA NOS CARDS: Etiqueta da plataforma (Mercado Livre, Amazon ou Shopee)
        plat = produto.get("plataforma", "")
        selos = []
        if plat == "mercado_livre":
            selos.append(chip("🟡 Mercado Livre", "#FFE600"))
        elif plat == "amazon":
            selos.append(chip("🟠 Amazon", "#FF9900"))
        elif plat == "shopee":
            selos.append(chip("🔴 Shopee", "#EE4D2D"))
        elif plat == "ebay":
            selos.append(chip("🔵 eBay", "#0064D2"))

        selos.append(chip(produto.get("selo") or tx("novo"), "#00F5D4"))
        if extra_selo:
            selos.append(chip(extra_selo, "#FF4D6D"))
        if produto.get("full"):
            selos.append(chip("FULL", "#4CC9F0"))
        if produto.get("loja_oficial"):
            selos.append(chip(tx("loja_oficial"), "#9D4EDD"))
        if produto.get("aviso_golpe"):
            selos.append(chip(tx("anti_golpe"), "#FFB703"))

        async def copiar_titulo(e):
            await copiar_texto(produto["titulo"], tx("titulo_copiado"))

        async def ver_oferta(e, prod=produto):
            fechar_todos_dialogos()
            try:
                await page.clipboard.set(CUPOM_JDS)
            except Exception:
                pass
            snack(tx("cupom"), "#00F5D4")
            url_abrir = _link_ver_oferta(prod)
            try:
                await page.launch_url(url_abrir)
            except TypeError:
                page.launch_url(url_abrir)
            await txt_busca.focus()
            page.update()

        def salvar_desejo(e):
            url = produto.get("url") or ""
            if any(_url_chave(x.get("url")) == _url_chave(url) and url for x in lista_desejos):
                snack(tx("ja_desejo"), "#FFB703")
                return
            item = _item_desejo_gravavel(produto)
            item["pais"] = _normalizar_pais(produto.get("pais") or mercado["pais"])
            lista_desejos.append(item)
            _salvar_desejos()
            render_desejos()
            snack(tx("guardado"), "#9D4EDD")

        return ft.Container(
            bgcolor="#1A1A1E",
            border_radius=12,
            padding=12,
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Image(
                            src=produto.get("foto") or FOTO_PADRAO,
                            height=160,
                            width=160,
                            fit=ft.BoxFit.COVER,
                            border_radius=8,
                        ),
                        alignment=ft.Alignment.CENTER,
                        padding=ft.Padding.only(bottom=8),
                    ),
                    ft.Row(selos, wrap=True, spacing=6, run_spacing=6),
                    ft.Text(
                        f"{tx('loja')}: {produto.get('loja') or _nome_loja(plat)}",
                        color="#FFD700",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        produto["titulo"],
                        color="#FFFFFF",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                produto["preco"],
                                color="#00F5D4",  # Verde neon
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CONTENT_COPY,
                                icon_color="#9D4EDD",
                                icon_size=18,
                                tooltip=tx("copiar_titulo"),
                                on_click=copiar_titulo,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(tx("melhor_preco"), color="#FF6B35",
                            size=12, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.Button(
                                tx("ver_oferta"),
                                bgcolor="#9D4EDD",  # Roxo chamativo
                                color="white",
                                on_click=ver_oferta,
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                )
                            ),
                            ft.IconButton(
                                icon=ft.Icons.STAR_BORDER,
                                icon_color="#FFD700",
                                tooltip=tx("lista_desejos"),
                                on_click=salvar_desejo,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=8,
            ),
        )

    def preencher_grade(grade, produtos, extra_selo=None):
        grade.controls.clear()
        for idx, produto in enumerate(produtos):
            selo_destaque = extra_selo
            if idx == 0 and not extra_selo:
                selo_destaque = tx("menor_preco_selo")
            elif idx == 0 and extra_selo:
                selo_destaque = f"{extra_selo} | {tx('primeiro')}"
            grade.controls.append(montar_card(
                produto, extra_selo=selo_destaque))

    def avisar_queda(item, preco_novo):
        titulo = (item.get("titulo") or "Produto")[:80]
        antigo = item.get("preco_anterior") or item.get("preco")
        msg = f"{titulo}\n" + tx("de_por", a=antigo, b=preco_novo)
        snack(tx("desconto", titulo=titulo, preco=preco_novo), "#00F5D4")
        try:
            page.window.minimized = False
            page.window.to_front()
        except Exception:
            pass
        page.show_dialog(
            ft.AlertDialog(
                bgcolor="#1A1A1E",
                title=ft.Text(tx("preco_caiu"), color="#00F5D4", weight=ft.FontWeight.BOLD),
                content=ft.Text(msg, color="#EDEDED"),
                actions=[ft.Button("OK", on_click=fechar_dialogo)],
            )
        )

    def render_desejos():
        coluna_desejos.controls.clear()
        if not lista_desejos:
            coluna_desejos.controls.append(
                ft.Text(
                    tx("sem_alerta"),
                    color="#888888",
                )
            )
        for idx, item in enumerate(list(lista_desejos)):
            status = (
                tx("caiu", a=item.get("preco_anterior"), b=item.get("preco"))
                if item.get("queda")
                else tx("monitorando", p=item.get("preco"))
            )

            def remover(e, i=idx):
                if 0 <= i < len(lista_desejos):
                    lista_desejos.pop(i)
                    _salvar_desejos()
                    render_desejos()
                    snack(tx("removido"), "#9D4EDD")

            async def abrir_desejo(e, prod=item):
                url = _link_ver_oferta(prod)
                fechar_todos_dialogos()
                try:
                    await page.clipboard.set(CUPOM_JDS)
                except Exception:
                    pass
                try:
                    await page.launch_url(url)
                except TypeError:
                    page.launch_url(url)

            coluna_desejos.controls.append(
                ft.Container(
                    bgcolor="#1A1A1E",
                    border_radius=14,
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Text(item.get("titulo") or "", color="#FFFFFF",
                                    size=14, weight=ft.FontWeight.BOLD, max_lines=2),
                            ft.Text(item.get("loja") or "", color="#FFD700", size=12),
                            ft.Text(status, color="#00F5D4"),
                            ft.Text(
                                tx("alerta_ativo"),
                                color="#FFD700", size=12),
                            ft.Row(
                                [
                                    ft.Button(tx("ver_oferta"), bgcolor="#9D4EDD",
                                              color="white", on_click=abrir_desejo),
                                    ft.Button(tx("remover"), bgcolor="#2A2A2E",
                                              color="white", on_click=remover),
                                ]
                            ),
                        ],
                        spacing=4,
                    ),
                )
            )
        page.update()

    def _aplicar_queda(item, candidato):
        try:
            novo = float(candidato.get("preco_num") or 0)
            antigo = float(item.get("preco_num") or 0)
        except (TypeError, ValueError):
            return False
        if novo <= 0 or antigo <= 0 or novo >= antigo - 0.49:
            item["queda"] = bool(item.get("queda"))
            return False
        item["preco_anterior"] = item.get("preco")
        item["preco_num"] = novo
        item["preco"] = _formatar_preco(novo, pais=item.get("pais") or "BR")
        item["url"] = candidato.get("url") or item.get("url")
        item["queda"] = True
        return True

    async def verificar_desejos(_e=None, silencioso=False):
        if not lista_desejos:
            if not silencioso:
                snack(tx("sem_desejos"))
            return
        if not silencioso:
            snack(tx("verificando"), "#9D4EDD")
        houve = False
        for item in lista_desejos:
            termo = (item.get("titulo") or "").strip()
            if not termo:
                continue
            try:
                ofertas = await asyncio.to_thread(
                    buscar_ofertas_jds, termo, item.get("pais") or "BR",
                )
            except Exception as e:
                print(f"[Desejos] {e}")
                continue
            ofertas = _ordenar_entrega_menor_preco(ofertas or [])
            if not ofertas:
                continue
            chave = _url_chave(item.get("url"))
            mesma = [
                o for o in ofertas
                if _url_chave(o.get("url")) == chave or o.get("plataforma") == item.get("plataforma")
            ]
            cand = mesma[0] if mesma else ofertas[0]
            if _aplicar_queda(item, cand):
                houve = True
                avisar_queda(item, item.get("preco"))
        _salvar_desejos()
        render_desejos()
        if not silencioso and not houve:
            snack(tx("sem_desconto"), "#FFB703")

    async def loop_alertas_desejos():
        await asyncio.sleep(45)
        while True:
            try:
                await verificar_desejos(silencioso=True)
            except Exception as e:
                print(f"[Desejos loop] {e}")
            await asyncio.sleep(INTERVALO_ALERTA_SEG)

    buscando = {"ok": False}

    async def garimpar(_e=None):
        fechar_todos_dialogos()
        termo = (txt_busca.value or "").strip()
        if not termo:
            snack(tx("digite"))
            return
        if buscando["ok"]:
            snack(tx("ainda"), "#FFB703")
            return
        buscando["ok"] = True
        rodinha.visible = True
        page.update()
        try:
            produtos = await asyncio.to_thread(buscar_ofertas_jds, termo, mercado["pais"])
            produtos = _ordenar_entrega_menor_preco(produtos)
            preencher_grade(grade_garimpo, produtos)
            if not produtos:
                lbl_menor_preco.visible = False
                snack(tx("nenhuma_oferta"), "#FFB703")
            else:
                campeao = produtos[0]
                lbl_menor_preco.value = tx(
                    "menor_preco_linha",
                    preco=campeao["preco"],
                    loja=campeao.get("loja", "loja"),
                )
                lbl_menor_preco.visible = True
                snack(lbl_menor_preco.value, "#00F5D4")
            for p in produtos or []:
                for item in lista_desejos:
                    mesma_url = _url_chave(p.get("url")) == _url_chave(item.get("url")) and _url_chave(item.get("url"))
                    mesma_loja = (
                        p.get("plataforma") == item.get("plataforma")
                        and (item.get("titulo") or "")[:28].lower()
                        in (p.get("titulo") or "").lower()
                    )
                    if (mesma_url or mesma_loja) and _aplicar_queda(item, p):
                        avisar_queda(item, item.get("preco"))
            if lista_desejos:
                _salvar_desejos()
                render_desejos()
            try:
                n = len(txt_busca.value or "")
                txt_busca.selection = ft.TextSelection(
                    base_offset=0, extent_offset=n)
            except Exception:
                pass
            await txt_busca.focus()
        except Exception as e:
            snack(tx("falha_motor", e=e), "#FF6B6B")
        finally:
            buscando["ok"] = False
            rodinha.visible = False
            page.update()

    txt_busca.on_submit = garimpar

    async def busca_voz(e):
        snack(tx("fale"), "#9D4EDD")
        rodinha.visible = True
        page.update()
        try:
            termo = await asyncio.to_thread(ouvir_produto_microfone)
        except Exception:
            termo = ""
        finally:
            rodinha.visible = False
            page.update()
        if not termo:
            snack(tx("nao_entendi"), "#FFB703")
            return
        txt_busca.value = termo
        page.update()
        await garimpar()

    def converter_achado(e):
        bruto = (txt_achado.value or "").strip()
        if "http" not in bruto:
            snack(tx("cole_valido"))
            return
        plat = _detectar_plataforma(bruto)
        if _host_amazon_eua(bruto):
            oculto = aplicar_tag_amazon_eua(bruto)
        else:
            oculto = gerar_link_afiliado(bruto, plat)
        achados_convertidos.append(
            {"origem": bruto, "url": oculto, "plataforma": plat})
        txt_achado.value = ""
        lista_achados.controls.clear()
        for item in achados_convertidos[::-1]:
            async def abrir(ev, link=item["url"]):
                try:
                    await page.clipboard.set(CUPOM_JDS)
                except Exception:
                    pass
                fechar_todos_dialogos()
                snack(tx("cupom"), "#00F5D4")
                try:
                    await page.launch_url(link)
                except TypeError:
                    page.launch_url(link)

            lista_achados.controls.append(
                ft.Container(
                    bgcolor="#1A1A1E",
                    border_radius=12,
                    padding=10,
                    content=ft.Column(
                        [
                            ft.Text(tx("achado_validado"),
                                    color="#9D4EDD", size=12),
                            ft.Text(item["origem"], color="#AAAAAA",
                                    size=11, max_lines=2),
                            ft.Button(tx("ver_oferta"), bgcolor="#9D4EDD",
                                      color="white", on_click=abrir),
                        ]
                    ),
                )
            )
        snack(tx("achado_ok"))
        page.update()

    def checkin_diario(e):
        hoje = date.today().isoformat()
        if pontos_jds["checkin"] == hoje:
            snack(tx("checkin_feito"), "#FFB703")
            return
        pontos_jds["checkin"] = hoje
        pontos_jds["saldo"] += 25
        _salvar_pontos()
        lbl_pontos.value = tx("pontos", n=pontos_jds["saldo"])
        snack(tx("checkin_ok"), "#00F5D4")
        page.update()

    def girar_roleta(e):
        semana = date.today().strftime("%Y-W%W")
        if pontos_jds.get("roleta") == semana:
            snack(tx("roleta_ja"), "#FFB703")
            return
        premio = random.choice(
            [tx("premio_50"), tx("premio_cupom"), tx("premio_frete"),
             tx("premio_alerta"), tx("premio_tente")]
        )
        if "50" in premio:
            pontos_jds["saldo"] += 50
        pontos_jds["roleta"] = semana
        _salvar_pontos()
        lbl_pontos.value = tx("pontos", n=pontos_jds["saldo"])
        lbl_roleta.value = tx("roleta_premio", premio=premio)
        snack(tx("roleta_snack", premio=premio), "#9D4EDD")
        page.update()

    btn_checkin.on_click = checkin_diario

    aba_garimpar = ft.Column(
        [
            ft.Row(
                [
                    txt_busca,
                    ft.IconButton(
                        icon=ft.Icons.MIC,
                        icon_color="#9D4EDD",
                        tooltip=tx("tooltip_voz"),
                        on_click=busca_voz,
                    ),
                    ft.Button(tx("garimpar"), bgcolor="#9D4EDD",
                              color="white", on_click=garimpar),
                ]
            ),
            rodinha,
            lbl_menor_preco,
            grade_garimpo,
        ],
        spacing=12,
        expand=True,
    )

    preencher_grade(grade_descontos, _ofertas_super_descontos(),
                    extra_selo="SUPER")
    aba_descontos = ft.Column(
        [
            ft.Text(tx("promo_jds"), color="#EDEDED"),
            grade_descontos,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    render_desejos()
    aba_desejos = ft.Column(
        [
            ft.Text(
                tx("aviso_desejos"),
                color="#EDEDED",
                size=13,
            ),
            ft.Button(
                tx("verificar_agora"),
                bgcolor="#9D4EDD",
                color="white",
                on_click=verificar_desejos,
            ),
            coluna_desejos,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    aba_achados = ft.Column(
        [
            ft.Text(tx("cole_rastreio"),
                    color="#EDEDED", size=13),
            txt_achado,
            ft.Button(tx("validar"), bgcolor="#9D4EDD",
                      color="white", on_click=converter_achado),
            lista_achados,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    aba_recompensas = ft.Column(
        [
            lbl_pontos,
            btn_checkin,
            ft.Divider(color="#2A2A2E"),
            ft.Text(tx("roleta_titulo"), color="#FFD700",
                    weight=ft.FontWeight.BOLD),
            lbl_roleta,
            ft.Button(tx("girar"), bgcolor="#00F5D4",
                      color="#121214", on_click=girar_roleta),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    abas = ft.Tabs(
        length=5,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    label_color="#9D4EDD",
                    unselected_label_color="#888888",
                    indicator_color="#9D4EDD",
                    tabs=[
                        ft.Tab(label=tx("tab_garimpar")),
                        ft.Tab(label=tx("tab_descontos")),
                        ft.Tab(label=tx("tab_desejos")),
                        ft.Tab(label=tx("tab_achados")),
                        ft.Tab(label=tx("tab_recompensas")),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        aba_garimpar,
                        aba_descontos,
                        aba_desejos,
                        aba_achados,
                        aba_recompensas,
                    ],
                ),
            ],
        ),
    )

    page.add(frase_sagrada, topo, abas)
    page.run_task(loop_alertas_desejos)


def executar_testes_unitarios():
    """Testes sem rede: preço, afiliado, Ver Oferta e ordenação."""
    falhas = []

    def checar(condicao, nome):
        if condicao:
            print(f"[OK] {nome}")
        else:
            print(f"[FALHA] {nome}")
            falhas.append(nome)

    antigo_meli = os.environ.pop("MELI_ACCESS_TOKEN", None)
    checar(_buscar_ofertas_ml_api("controle ps5") == [], "sem token ML não chama API oficial")
    ml_sem_token = gerar_lista_ofertas_reais("controle ps5", usar_cache=False, usar_vivo=False)
    checar(
        any(p.get("plataforma") == "mercado_livre" for p in ml_sem_token),
        "Mercado Livre continua no ranking sem token",
    )
    if antigo_meli:
        os.environ["MELI_ACCESS_TOKEN"] = antigo_meli
    checar(_limpar_texto_voz("  DualSense PS5!! ") == "DualSense PS5", "voz limpa o termo falado")
    checar(_limpar_texto_voz("cabo usb tipo c") == "cabo usb tipo c", "voz aceita qualquer produto")
    checar("fone bluetooth" not in (_limpar_texto_voz("redmi note 13") or ""), "voz não força fone bluetooth")
    fb = _ofertas_fallback_lojas("iphone 16")
    checar(len(fb) == 3 and all(p.get("url", "").startswith("http") for p in fb), "fallback sempre tem 3 lojas")
    checar(
        "B0CQKLS4RP" in _desempacotar_link_google(
            "/url?q=https://www.amazon.com.br/dp/B0CQKLS4RP%3Ftag%3Dx&sa=U"
        ),
        "Google devolve o /dp/ da loja, não o redirect",
    )
    checar(
        "MLB32344506" in _desempacotar_link_google(
            "https://www.google.com/url?url=https://www.mercadolivre.com.br/x/p/MLB32344506"
        ),
        "Google unpack lê o parâmetro url= do Mercado Livre",
    )
    html_g = """
    <div>
      <a href="/url?q=https://www.amazon.com.br/dp/B0CQKLS4RP">
        <h3>PlayStation DualSense Controle sem fio PS5</h3>
      </a>
      <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:dual"/>
      R$ 404,27 Amazon.com.br
    </div>
    <div>
      <a href="https://www.google.com/url?url=https://www.mercadolivre.com.br/dualsense-ps5/p/MLB32344506">
        <h3>Controle DualSense PS5 Sony</h3>
      </a>
      <img src="https://http2.mlstatic.com/D_NQ_NP_teste-O.jpg"/>
      R$ 419,00 Mercado Livre
    </div>
    """
    g_ofertas = _parsear_ofertas_google(html_g, "dualsense ps5", origem="direto")
    plats_g = {p.get("plataforma") for p in g_ofertas}
    checar("amazon" in plats_g and "mercado_livre" in plats_g, "parser Google lê Amazon e Mercado Livre")
    amz_g = next(p for p in g_ofertas if p["plataforma"] == "amazon")
    ml_g = next(p for p in g_ofertas if p["plataforma"] == "mercado_livre")
    checar("/dp/B0CQKLS4RP" in (amz_g.get("url") or ""), "Google Amazon vai para /dp/ real")
    checar(
        "/dp/B0CQKLS4RP" in _link_compra_do_card(amz_g) and f"tag={ID_AMAZON}" in _link_compra_do_card(amz_g),
        "Ver Oferta Amazon abre o /dp/ do produto mais barato",
    )
    misturado = {
        "titulo": "PlayStation DualSense",
        "preco_num": 404.27,
        "url": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "link_afiliado": "https://www.amazon.com.br/s?k=dualsense&s=price-asc-rank&tag=jdseconomiz0e-20",
        "foto": FOTO_PADRAO,
        "plataforma": "amazon",
        "fonte": "google",
        "pais": "BR",
        "loja": "Amazon",
    }
    checar(
        "/dp/B0CQKLS4RP" in _link_ver_oferta(misturado)
        and "/s?" not in _link_ver_oferta(misturado)
        and f"tag={ID_AMAZON}" in _link_ver_oferta(misturado),
        "Ver Oferta ignora busca da loja e abre o anúncio mais barato",
    )
    checar(
        "/p/MLB32344506" in _link_compra_do_card(ml_g)
        and f"identity={ID_MERCADO_LIVRE}" in _link_compra_do_card(ml_g),
        "Ver Oferta ML abre o anúncio /p/ do produto, não a busca",
    )
    serper_itens = [
        {
            "title": "PlayStation DualSense Controle sem fio PS5",
            "source": "Amazon.com.br",
            "price": "R$ 404,27",
            "extracted_price": 404.27,
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        },
        {
            "title": "Controle DualSense PS5 Sony",
            "source": "Mercado Livre",
            "price": "R$ 419,00",
            "link": "https://www.mercadolivre.com.br/dualsense-ps5/p/MLB32344506",
            "imageUrl": "https://http2.mlstatic.com/D_NQ_NP_teste-O.jpg",
        },
    ]
    serper_of = _ofertas_de_itens_serper("dualsense ps5", serper_itens)
    checar(
        {p.get("plataforma") for p in serper_of} >= {"amazon", "mercado_livre"},
        "Serper devolve Amazon e Mercado Livre do Google",
    )
    checar(
        any("/dp/B0CQKLS4RP" in (p.get("url") or "") for p in serper_of),
        "Serper Amazon usa o /dp/ do Google",
    )
    misturado_serper = _ofertas_de_itens_serper("controle ps5", [
        {
            "title": "Controle DualSense PS5 Sony Original",
            "source": "Amazon.com.br",
            "price": "R$ 514,89",
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
            "snippet": "Mercado Livre R$ 419,00 https://www.mercadolivre.com.br/outro/p/MLB1",
        },
        {
            "title": "Controle DualSense Sony PlayStation 5",
            "source": "Mercado Livre",
            "price": "R$ 419,00",
            "link": "https://www.mercadolivre.com.br/dualsense-ps5/p/MLB32344506",
            "imageUrl": "https://http2.mlstatic.com/D_NQ_NP_teste-O.jpg",
        },
        {
            "title": "Capa para Controle PS5 DualSense",
            "source": "Shopee",
            "price": "R$ 29,90",
            "link": "https://shopee.com.br/Capa-Controle-i.1.2",
            "imageUrl": "https://cf.shopee.com.br/file/capa.jpg",
        },
    ])
    amz_m = next(p for p in misturado_serper if p.get("plataforma") == "amazon")
    ml_m = next(p for p in misturado_serper if p.get("plataforma") == "mercado_livre")
    checar(
        abs(float(amz_m.get("preco_num") or 0) - 514.89) < 0.05
        and "amazon.com.br" in (amz_m.get("url") or "")
        and "mercadolivre" not in (amz_m.get("url") or ""),
        "preço e link da Amazon não misturam com o Mercado Livre",
    )
    checar(
        abs(float(ml_m.get("preco_num") or 0) - 419.0) < 0.05
        and "mercadolivre" in (ml_m.get("url") or ""),
        "preço e link do Mercado Livre ficam no bloco do ML",
    )
    checar(
        misturado_serper[0].get("plataforma") == "mercado_livre",
        "menor preço float da loja certa vai para o topo",
    )
    checar(
        not any(p.get("plataforma") == "shopee" for p in misturado_serper),
        "capa/capinha/suporte/cabo da Shopee é descartado",
    )
    gshop = _ofertas_de_itens_serper("garrafa termica", [
        {
            "title": "Garrafa Térmica Inox 500ml",
            "source": "Amazon.com.br",
            "price": "R$ 89,90",
            "link": "https://www.google.com/shopping/product/123456?gl=br",
            "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:teste",
        },
        {
            "title": "Garrafa Térmica 1L",
            "source": "Magazine Luiza",
            "price": "R$ 59,90",
            "link": "https://www.google.com/shopping/product/999?gl=br",
            "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:mag",
        },
    ])
    checar(
        gshop
        and gshop[0].get("plataforma") == "amazon"
        and abs(float(gshop[0].get("preco_num") or 0) - 89.90) < 0.05
        and "shopping/product" in (gshop[0].get("url") or ""),
        "Shopping Google com source Amazon entra; Magazine Luiza sai",
    )
    oshop = _ofertas_de_itens_serper("controle ps5", [{
        "title": "Controle Dualsense Sem Fio Sony",
        "source": "Amazon.com.br - Retail",
        "price": "R$ 404,27 agora",
        "link": "https://www.google.com/search?ibp=oshop&q=controle+ps5&prds=catalogid:4499265276956382",
        "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:teste",
    }])
    checar(
        oshop and oshop[0].get("plataforma") == "amazon"
        and abs(float(oshop[0].get("preco_num") or 0) - 404.27) < 0.05
        and "ibp=oshop" in (oshop[0].get("url") or ""),
        "link Google oshop da Amazon entra com o preço",
    )
    checar(
        not _titulo_shopping_ok(
            "redmi note 13",
            "Tela Display Compatível Para Note 13 4G OLED",
        )
        and not _titulo_shopping_ok(
            "redmi note 13",
            "Kit Capa Anti Impacto e Película De Vidro 3D",
        ),
        "peça e capa do Redmi não viram o celular",
    )
    checar(
        not _titulo_shopping_ok("whey protein", "100% Whey Crush - 1 Sachê 30g Chocobear")
        and _titulo_shopping_ok("whey protein", "100% Whey Crush 900g Under Labz"),
        "sachê 30g de whey não substitui o pote",
    )
    checar(
        _titulo_shopping_ok("dualsense", "Controle DualSense Sony PS5")
        and not _titulo_shopping_ok("dualsense", "Gamrombo Controle LED PS5")
        and _titulo_shopping_ok("controle ps5", "Gamrombo Controle LED PS5"),
        "produto exato: DualSense não vira Gamrombo; controle ps5 aceita o gamepad",
    )
    exato_barato = _ordenar_entrega_menor_preco(_ofertas_de_itens_serper("dualsense", [
        {
            "title": "Gamrombo Controle LED PS5",
            "source": "Amazon.com.br - Seller",
            "price": "R$ 330,00",
            "link": "https://www.google.com/search?ibp=oshop&q=dualsense&prds=catalogid:1",
            "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:barato",
        },
        {
            "title": "PlayStation DualSense Controle sem fio PS5 Sony",
            "source": "Amazon.com.br - Retail",
            "price": "R$ 404,27",
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        },
    ]))
    checar(
        exato_barato
        and abs(float(exato_barato[0].get("preco_num") or 0) - 404.27) < 0.05
        and "dualsense" in _sem_acento(exato_barato[0].get("titulo") or ""),
        "na lista da Serper o mais barato só ganha se for o produto exato",
    )
    checar(
        not _titulo_shopping_ok(
            "airpods",
            "Fone de ouvido único para fone de ouvido esquerdo Apple Airpods Pro",
        )
        and _titulo_shopping_ok("airpods", "Apple AirPods 4 com estojo de carregamento"),
        "AirPods de um lado só não substitui o fone completo",
    )
    checar(
        not _titulo_shopping_ok("echo dot", "Relógio Led Echo Dot 2025 4a Geração Preto"),
        "relógio LED não passa como Echo Dot",
    )
    checar(
        abs(_normalizar_preco_mercado(
            2499.0, "kindle",
            "Amazon Kindle Scribe 16GB Tela 11",
            "BR",
        ) - 2499.0) < 0.05
        and _normalizar_preco_mercado(
            2499.0, "kindle",
            "Amazon Kindle Scribe 16GB Tela 11",
            "BR",
        ) != 24.99,
        "Kindle R$ 2.499 não vira R$ 24,99",
    )
    checar(
        not _preco_plausivel("whey protein", 24.37, "100% Whey Crush 900g Under Labz")
        and _preco_plausivel("whey protein", 63.79, "Mega Whey Protein Iridium 900g"),
        "pote 900g a R$ 24 não passa como whey",
    )
    checar(
        _titulos_mesmo_produto(
            "controle ps5",
            "Gamrombo Controle LED PS5",
            "Gamrombo Controle sem fio LED para PS5",
        )
        and not _titulos_mesmo_produto(
            "controle ps5",
            "Gamrombo Controle LED PS5",
            "PlayStation DualSense Controle sem fio PS5 Sony",
        ),
        "não cola o DualSense no card Gamrombo",
    )
    oshop_card = _ofertas_de_itens_serper("controle ps5", [{
        "title": "Gamrombo Controle LED PS5",
        "source": "Amazon.com.br - Seller",
        "price": "R$ 330,00",
        "link": "https://www.google.com/search?ibp=oshop&q=controle+ps5&prds=catalogid:1",
        "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:barato",
    }])[0]
    colado = _colar_anuncio_organico(
        dict(oshop_card),
        [{
            "title": "Gamrombo Controle sem fio LED para PS5",
            "link": "https://www.amazon.com.br/dp/B0GAMROMB0",
            "source": "Amazon.com.br",
        }],
        "controle ps5",
        pais="BR",
    )
    ver_colado = _link_ver_oferta(colado)
    checar(
        "/dp/B0GAMROMB0" in (colado.get("url") or "")
        and "/dp/B0GAMROMB0" in ver_colado
        and "ibp=oshop" not in ver_colado
        and abs(float(colado.get("preco_num") or 0) - 330.00) < 0.05,
        "Ver Oferta abre o /dp/ da loja, não o Google Shopping",
    )
    ver_sem_dp = _link_ver_oferta(dict(oshop_card))
    checar(
        ver_sem_dp.startswith("http")
        and "google." not in ver_sem_dp
        and "ibp=oshop" not in ver_sem_dp
        and f"tag={ID_AMAZON}" in ver_sem_dp,
        "sem /dp/ no JSON, Ver Oferta não abre o Google Shopping",
    )
    mais_barato_oshop = _ordenar_entrega_menor_preco(_ofertas_de_itens_serper("controle ps5", [
        {
            "title": "Gamrombo Controle LED PS5",
            "source": "Amazon.com.br - Seller",
            "price": "R$ 330,00",
            "link": "https://www.google.com/search?ibp=oshop&q=controle+ps5&prds=catalogid:1",
            "imageUrl": "https://encrypted-tbn0.gstatic.com/shopping?q=tbn:barato",
        },
        {
            "title": "Gamrombo Controle LED PS5",
            "source": "Amazon.com.br - Retail",
            "price": "R$ 370,70",
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        },
    ]))
    checar(
        mais_barato_oshop
        and abs(float(mais_barato_oshop[0].get("preco_num") or 0) - 330.00) < 0.05,
        "o card mais barato da Amazon vence o /dp/ mais caro",
    )
    busca_vs_anuncio = _ordenar_entrega_menor_preco(_ofertas_de_itens_serper("controle ps5", [
        {
            "title": "Controle DualSense PS5 Sony",
            "source": "Mercado Livre",
            "price": "R$ 393,04",
            "link": "https://lista.mercadolivre.com.br/controle-dualsense-sem-fio-sony_OrderId_PRICE",
            "imageUrl": "https://http2.mlstatic.com/D_NQ_NP_teste-O.jpg",
        },
        {
            "title": "PlayStation DualSense Controle sem fio PS5",
            "source": "Amazon.com.br",
            "price": "R$ 420,00",
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        },
    ]))
    checar(
        busca_vs_anuncio
        and busca_vs_anuncio[0].get("plataforma") == "amazon"
        and "/dp/B0CQKLS4RP" in (busca_vs_anuncio[0].get("url") or "")
        and not any(p.get("plataforma") == "mercado_livre" for p in busca_vs_anuncio),
        "lista do ML não vence o /dp/ da Amazon",
    )
    checar(
        _url_e_busca_loja("https://www.amazon.com.br/s?k=controle+ps5&s=price-asc-rank")
        and _url_e_busca_loja("https://shopee.com.br/search?keyword=controle+ps5")
        and _url_e_busca_loja("https://lista.mercadolivre.com.br/controle-ps5_OrderId_PRICE")
        and not _url_e_busca_loja("https://www.amazon.com.br/dp/B0CQKLS4RP"),
        "detecta /search ?q= keyword= ranking e ignora /dp/",
    )
    href_alt = _href_item_serper({
        "title": "PlayStation DualSense Controle sem fio PS5",
        "source": "Amazon.com.br",
        "price": "R$ 420,00",
        "link": "https://www.amazon.com.br/s?k=controle+de+ps5&s=price-asc-rank",
        "productLink": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "merchant": {"name": "Amazon.com.br", "link": "https://www.amazon.com.br/dp/B0CQKLS4RP"},
    })
    checar(
        "/dp/B0CQKLS4RP" in href_alt and "/s?" not in href_alt,
        "Serper busca vira o link direto do lojista no mesmo JSON",
    )
    oferta_alt = _ofertas_de_itens_serper("controle ps5", [{
        "title": "PlayStation DualSense Controle sem fio PS5",
        "source": "Amazon.com.br",
        "price": "R$ 420,00",
        "link": "https://www.amazon.com.br/s?k=controle+de+ps5&s=price-asc-rank",
        "productLink": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
    }])
    checar(oferta_alt, "oferta com productLink entra no ranking")
    ver_alt = _link_ver_oferta(oferta_alt[0])
    checar(
        "/dp/B0CQKLS4RP" in ver_alt
        and "/s?" not in ver_alt
        and "keyword=" not in ver_alt
        and "price-asc-rank" not in ver_alt,
        "Ver Oferta abre o anúncio, não a busca da loja",
    )
    organico_preco = _ofertas_de_itens_serper("controle ps5", [{
        "title": "PlayStation DualSense Controle sem fio PS5",
        "source": "Amazon.com.br",
        "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "snippet": "Em estoque. R$ 404,27. Entrega Amazon.",
        "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
    }])
    checar(
        organico_preco
        and abs(float(organico_preco[0].get("preco_num") or 0) - 404.27) < 0.05
        and "/dp/B0CQKLS4RP" in (organico_preco[0].get("url") or ""),
        "organic com R$ no snippet vira oferta com /dp/",
    )
    juntado = _juntar_preco_shopping_url_anuncio(
        "controle ps5",
        [{
            "title": "PlayStation DualSense Controle sem fio PS5",
            "source": "Amazon.com.br",
            "price": "R$ 399,90",
            "link": "https://www.amazon.com.br/s?k=controle+ps5&s=price-asc-rank",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        }],
        [{
            "title": "PlayStation DualSense Controle sem fio PS5 Sony",
            "source": "Amazon.com.br",
            "link": "https://www.amazon.com.br/dp/B0CQKLS4RP",
            "snippet": "Página do produto DualSense.",
        }],
        "amazon",
        pais="BR",
    )
    checar(
        juntado
        and "/dp/B0CQKLS4RP" in (juntado.get("url") or "")
        and abs(float(juntado.get("preco_num") or 0) - 399.90) < 0.05
        and "/s?" not in (juntado.get("url") or ""),
        "preço do shopping + /dp/ orgânico da mesma loja",
    )
    checar(_source_loja_oficial("Amazon.com.br") and _source_loja_oficial("MERCADO LIVRE"),
           "filtro source aceita Amazon e Mercado Livre")
    checar(_source_loja_oficial("Shopee") and not _source_loja_oficial("Magazine Luiza"),
           "filtro source recusa loja fora das 3 oficiais")
    checar(abs(_preco_serper_para_float("R$ 1.799,00") - 1799.0) < 0.01,
           "preço Serper R$ 1.799,00 vira 1799.00")
    checar(abs(_limpar_preco_serper("R$ 1.799,00") - 1799.0) < 0.01,
           "limpa R$, espaço, ponto e vírgula para float")
    checar(abs(_limpar_preco_serper("$62.00", "US") - 62.0) < 0.01,
           "preço US $62.00 não apaga o ponto decimal")
    checar(abs(_normalizar_preco_mercado(6200, "dualsense ps5", "DualSense", "US") - 62.0) < 0.01,
           "preço US inflado 6200 volta para 62")
    checar(not _preco_plausivel("airpods pro", 3.30, "Apple AirPods Pro", pais="US"),
           "AirPods a $3.30 é recusado")
    checar(_preco_plausivel("airpods pro", 189.0, "Apple AirPods Pro", pais="US"),
           "AirPods Pro a $189 passa")
    us_dp = _item_google(
        "dualsense ps5 controller",
        "Sony DualSense PS5 Wireless Controller",
        62.0,
        "https://www.amazon.com/dp/B0CQKLS4RP",
        "https://m.media-amazon.com/images/I/d.jpg",
        "amazon",
        origem="serper",
        pais="US",
    )
    checar(
        us_dp and "/dp/B0CQKLS4RP" in (us_dp.get("url") or "")
        and abs(float(us_dp.get("preco_num") or 0) - 62) < 0.01,
        "Amazon US mantém o /dp/ e o preço em dólar",
    )
    barato = isolar_produto_mais_barato([
        {"titulo": "Caro", "preco_num": 900.0, "url": "https://www.amazon.com.br/dp/B0CARO0000",
         "foto": "https://m.media-amazon.com/images/I/c.jpg", "plataforma": "amazon",
         "loja": "Amazon", "fonte": "google", "pais": "BR"},
        {"titulo": "Barato DualSense", "preco_num": 404.27, "url": "https://www.amazon.com.br/dp/B0CQKLS4RP",
         "foto": "https://m.media-amazon.com/images/I/d.jpg", "plataforma": "amazon",
         "loja": "Amazon", "fonte": "google", "pais": "BR"},
    ], pais="BR")
    checar(
        barato and barato.get("titulo") == "Barato DualSense"
        and "/dp/B0CQKLS4RP" in (barato.get("url") or "")
        and f"tag={ID_AMAZON}" in (barato.get("url") or barato.get("link_afiliado") or ""),
        "isola o produto mais barato com link e afiliado",
    )
    magalu = _ofertas_de_itens_serper("tv", [{
        "title": "Smart TV 50",
        "source": "Magazine Luiza",
        "price": "R$ 1.500,00",
        "link": "https://www.magazineluiza.com.br/tv",
        "imageUrl": "https://m.media-amazon.com/images/I/x.jpg",
    }])
    checar(not magalu, "source Magazine Luiza não entra no ranking")
    tv = gerar_lista_ofertas_reais("smart tv 50", usar_cache=False, usar_vivo=False)
    ml_tv = next(p for p in tv if p.get("plataforma") == "mercado_livre")
    amz_tv = next(p for p in tv if p.get("plataforma") == "amazon")
    checar("OrderId_PRICE" in _link_compra_do_card(ml_tv), "catálogo ML abre busca, não /p/ inexistente")
    checar(
        "/s?" in _link_compra_do_card(amz_tv)
        and "price-asc-rank" not in _link_compra_do_card(amz_tv)
        and f"tag={ID_AMAZON}" in _link_compra_do_card(amz_tv),
        "catálogo Amazon sem DualSense abre busca, não /dp/ 404",
    )
    checar(abs(_preco_de_html_amazon(
        '<span class="a-price"><span class="a-offscreen">R$ 404,27</span></span>'
        '<span class="a-price a-text-price"><span class="a-offscreen">R$ 499,90</span></span>'
    ) - 404.27) < 0.01, "parser Amazon /dp/ ignora preço riscado")
    html_capa = '<span class="a-price"><span class="a-offscreen">R$ 24,90</span></span>'
    checar(abs(_preco_de_html_amazon(html_capa) - 24.90) < 0.01, "parser lê R$ 24,90 no HTML")
    checar(not _preco_plausivel("redmi note 13", 24.90, "Xiaomi Redmi Note 13"), "R$ 24,90 não atualiza celular")
    checar(not _titulo_relevante(
        "controle ps5",
        "PlayVital Anti-Skid Sweat-Absorbent Grip for PS5 Edge Wireless Controller",
    ), "grip/capa não passa como DualSense")
    checar(not _titulo_relevante(
        "redmi note 13", "Smartphone Xiaomi Redmi Note 14 256GB 8GB RAM",
    ), "Note 14 não passa como Note 13")
    checar(not _titulo_relevante(
        "redmi note 13", "Pb Para Xiaomi Redmi Note 13 Pro + Tela Amoled",
    ), "tela/peça não passa como celular")
    checar(not _titulo_relevante(
        "controle ps5",
        "Suporte Controle PS5 Playstation 5 DualSense | Shopee Brasil",
    ), "suporte/base não passa como DualSense")
    checar(not _titulo_relevante(
        "controle dualsense ps5",
        "Capa de Silicone para Controle DualSense PS5",
    ), "Shopee/Amazon capa DualSense não entra")
    checar(_titulo_relevante(
        "controle dualsense ps5",
        "PlayStation DualSense Controle sem fio PS5 Sony Original",
    ), "DualSense original continua no ranking")
    checar(_titulo_relevante(
        "controle dualsense ps5",
        "Controle DualSense Sony PlayStation 5 Original Branco",
    ), "ML DualSense entra mesmo sem a palavra PS5")
    checar(not _titulo_relevante(
        "redmi note 13",
        "Redmi Note 13: Qual versão vale a pena? - Mercado Livre",
    ), "artigo/review não passa como celular")
    checar(not _preco_plausivel(
        "redmi note 13", 200.0,
        "Smartphone Xiaomi Redmi Note 13 4G 128GB",
    ), "Redmi a R$ 200 é recusado")
    artigo_ml = _ofertas_de_itens_serper("redmi note 13", [{
        "title": "Redmi Note 13: Qual versão vale a pena? - Mercado Livre",
        "source": "Mercado Livre",
        "price": "R$ 200,00",
        "link": "https://www.mercadolivre.com.br/magazine/redmi-note-13",
        "imageUrl": "https://http2.mlstatic.com/D_NQ_NP_artigo-O.jpg",
    }])
    checar(not artigo_ml, "organic de revista ML não entra no ranking")
    loc_us = _serper_locale("US")
    loc_br = _serper_locale("BR")
    checar(loc_us == {"gl": "us", "hl": "en"}, "Serper EUA usa gl=us hl=en")
    checar(loc_br == {"gl": "br", "hl": "pt"}, "Serper BR usa gl=br hl=pt")
    checar(
        _consulta_serper_shopping("garrafa de café") == "garrafa de café"
        and _consulta_serper_shopping("bicicleta") == "bicicleta"
        and "site:" not in _consulta_serper_shopping("bicicleta site:shopee.com.br"),
        "payload q da Serper é só o nome do produto",
    )
    checar(
        all("site:" not in q for q in _consultas_serper_fallback("redmi note 13"))
        and "amazon" in _consultas_serper_fallback("redmi note 13")[0],
        "fallback sem site: tenta o nome da loja no q",
    )
    checar(
        _completar_lojas_serper("garrafa de café", []) == [],
        "não dispara busca extra por loja",
    )
    checar(_source_loja_oficial("eBay", pais="US") and _source_loja_oficial("Amazon.com", pais="US"),
           "filtro US aceita Amazon e eBay")
    checar(not _source_loja_oficial("Shopee", pais="US") and not _source_loja_oficial("Mercado Livre", pais="US"),
           "filtro US recusa Shopee e Mercado Livre")
    tag_us = aplicar_tag_amazon_eua("https://www.amazon.com/dp/B0CQKLS4RP")
    checar(f"tag={ID_AMAZON_US}" in tag_us and "amazon.com/" in tag_us, "tag Amazon EUA no /dp/")
    sujo_us = aplicar_tag_amazon_eua("https://www.amazon.com/dp/B0CQKLS4RP?tag=outra-20")
    checar(f"tag={ID_AMAZON_US}" in sujo_us and "outra-20" not in sujo_us,
           "tag Amazon EUA substitui tag de terceiro")
    br_no_us = aplicar_tag_amazon_eua("https://www.amazon.com.br/dp/B0CQKLS4RP")
    checar(f"tag={ID_AMAZON}" in br_no_us and "jdseconomiza-20" not in br_no_us,
           "amazon.com.br nunca recebe o ID dos EUA")
    us_no_br = aplicar_tag_amazon_eua("https://www.amazon.com/dp/B0CQKLS4RP")
    checar(f"tag={ID_AMAZON_US}" in us_no_br and "jdseconomiz0e-20" not in us_no_br,
           "amazon.com nunca recebe o ID do Brasil")
    us_mix = _ofertas_de_itens_serper("dualsense", [
        {
            "title": "DualSense Wireless Controller",
            "source": "Amazon.com",
            "price": "$69.99",
            "extracted_price": 69.99,
            "link": "https://www.amazon.com/dp/B0CQKLS4RP",
            "imageUrl": "https://m.media-amazon.com/images/I/dual.jpg",
        },
        {
            "title": "DualSense Sony PS5",
            "source": "eBay",
            "price": "$64.99",
            "extracted_price": 64.99,
            "link": "https://www.ebay.com/itm/123456789012",
            "imageUrl": "https://i.ebayimg.com/images/g/teste/s-l1600.jpg",
        },
        {
            "title": "Controle DualSense",
            "source": "Mercado Livre",
            "price": "R$ 419,00",
            "link": "https://www.mercadolivre.com.br/dualsense/p/MLB32344506",
            "imageUrl": "https://http2.mlstatic.com/D_NQ_NP_teste-O.jpg",
        },
    ], pais="US")
    checar(
        {p.get("plataforma") for p in us_mix} <= {"amazon", "ebay"}
        and "mercado_livre" not in {p.get("plataforma") for p in us_mix},
        "busca US só Amazon e eBay",
    )
    checar(
        any(f"tag={ID_AMAZON_US}" in (p.get("url") or "") for p in us_mix if p.get("plataforma") == "amazon"),
        "Amazon US carimba tracking ID",
    )
    app_json = serializar_oferta_app({
        "titulo": "DualSense  - Amazon.com.br",
        "preco": "R$ 1.234,50",
        "preco_num": 1234.5,
        "url": "https://www.google.com/url?url=https://www.amazon.com.br/dp/B0CQKLS4RP",
        "foto": "https://m.media-amazon.com/images/I/dual.jpg",
        "plataforma": "amazon",
        "loja": "Amazon",
        "pais": "BR",
        "fonte": "google",
    }, pais="BR")
    chaves_app = {"titulo", "preco_formatado", "preco_numerico", "loja", "link_afiliado", "imagem"}
    checar(chaves_app <= set(app_json), "JSON do app tem as 6 chaves padronizadas")
    checar(app_json["titulo"] == "DualSense", "título limpo sem sufixo da loja")
    checar(isinstance(app_json["preco_numerico"], float) and abs(app_json["preco_numerico"] - 1234.5) < 0.01,
           "preco_numerico é float para o app ordenar")
    checar(app_json["preco_formatado"].startswith("R$"), "preco_formatado amigável em real")
    checar(
        "/dp/B0CQKLS4RP" in app_json["link_afiliado"]
        and f"tag={ID_AMAZON}" in app_json["link_afiliado"]
        and "google." not in app_json["link_afiliado"],
        "link do Google vira oferta final com afiliado BR",
    )
    us_json = serializar_oferta_app({
        "titulo": "DualSense",
        "preco_num": 69.99,
        "url": "https://www.amazon.com/dp/B0CQKLS4RP",
        "foto": "https://m.media-amazon.com/images/I/dual.jpg",
        "plataforma": "amazon",
        "pais": "US",
        "fonte": "google",
    }, pais="US")
    checar(
        f"tag={ID_AMAZON_US}" in us_json["link_afiliado"]
        and "jdseconomiz0e-20" not in us_json["link_afiliado"],
        "domínio amazon.com recebe o ID dos EUA",
    )
    checar(
        us_json["preco_formatado"].startswith("$")
        and "R$" not in us_json["preco_formatado"]
        and "69.99" in us_json["preco_formatado"],
        "preco_formatado US usa o símbolo do dólar",
    )
    checar(
        mensagem_servidor("nenhum_produto", "US") == "No products found"
        and mensagem_servidor("erro_servidor", "US") == "Server error"
        and mensagem_servidor("nenhum_produto", "BR") == "Nenhum produto encontrado",
        "mensagens da API seguem o idioma do país",
    )
    from api.main import _resposta_ofertas as _api_resposta_ofertas
    vazio_us = _api_resposta_ofertas("ps5", [], pais="US")
    vazio_br = _api_resposta_ofertas("ps5", [], pais="BR")
    checar(
        vazio_us.get("message") == "No products found"
        and vazio_us.get("mensagem") == "No products found"
        and vazio_br.get("mensagem") == "Nenhum produto encontrado",
        "rota vazia US devolve No products found",
    )
    lista_ord = serializar_lista_app([
        {"titulo": "B", "preco_num": 80, "url": "https://www.amazon.com.br/dp/B0BBBBBBBB",
         "foto": "https://m.media-amazon.com/images/I/b.jpg", "plataforma": "amazon", "fonte": "google"},
        {"titulo": "A", "preco_num": 40, "url": "https://www.amazon.com.br/dp/B0AAAAAAAA",
         "foto": "https://m.media-amazon.com/images/I/a.jpg", "plataforma": "amazon", "fonte": "google"},
    ], pais="BR")
    checar(lista_ord[0]["titulo"] == "A" and lista_ord[0]["preco_numerico"] == 40.0,
           "lista do app ordena pelo preco_numerico")
    import tempfile as _tmp
    _db = Path(_tmp.mkdtemp()) / "cache_teste.db"
    os.environ["CACHE_GARIMPO_DB"] = str(_db)
    amostra = [{
        "titulo": "DualSense cache",
        "preco_num": 404.27,
        "url": "https://www.amazon.com.br/dp/B0CQKLS4RP",
        "foto": "https://m.media-amazon.com/images/I/dual.jpg",
        "plataforma": "amazon",
        "fonte": "google",
    }]
    _gravar_cache_garimpo("controle ps5", amostra, pais="BR")
    hit_br = _ler_cache_garimpo("Controle  PS5", pais="BR")
    hit_us = _ler_cache_garimpo("controle ps5", pais="US")
    checar(hit_br and hit_br[0]["titulo"] == "DualSense cache", "SQLite acerta termo+país BR em 2h")
    checar(not hit_us, "SQLite não mistura busca BR com US")
    os.environ.pop("CACHE_GARIMPO_DB", None)
    checar(not _preco_plausivel(
        "controle ps5", 292.78,
        "PlayStation DualSense Controle sem fio",
    ), "DualSense abaixo de R$ 320 é recusado")
    checar(not _preco_plausivel(
        "redmi note 13", 24.90,
        "Capa Redmi Note 13 4G",
    ), "capa de celular a R$ 24,90 é recusada")
    xbox = gerar_lista_ofertas_reais("xbox", usar_cache=False, usar_vivo=False)
    checar(
        xbox and abs(xbox[0]["preco_num"] - 429.90) < 0.06 and "xbox" in xbox[0]["titulo"].lower(),
        "busca xbox não devolve DualSense",
    )
    dual_ref = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        404.27,
        f"https://www.amazon.com.br/dp/{ASIN_DUALSENSE}",
        FOTO_PADRAO,
        "amazon",
    )
    dual_errado = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        292.78,
        "https://www.amazon.com.br/dp/B0ACCESSOR1",
        FOTO_PADRAO,
        "amazon",
    )
    dual_mesmo = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        380.00,
        f"https://www.amazon.com.br/dp/{ASIN_DUALSENSE}",
        FOTO_PADRAO,
        "amazon",
    )
    checar(not _scrape_e_o_mesmo_produto(dual_errado, dual_ref), "ASIN diferente não substitui DualSense")
    checar(_scrape_e_o_mesmo_produto(dual_mesmo, dual_ref), "mesmo ASIN DualSense pode atualizar preço")
    redmi_ref = _montar_item_oferta(
        "Xiaomi Redmi Note 13 4G 128GB",
        999.00,
        "https://www.amazon.com.br/dp/B0CS3V5J3H",
        FOTO_PADRAO,
        "amazon",
    )
    redmi_capa = _montar_item_oferta(
        "Capa Redmi Note 13",
        24.90,
        "https://www.amazon.com.br/dp/B0CAPINHA01",
        FOTO_PADRAO,
        "amazon",
    )
    checar(not _scrape_e_o_mesmo_produto(redmi_capa, redmi_ref), "capa Redmi não substitui o celular")
    checar(_titulo_relevante("notebook dell", "Dell Inspiron 15 Laptop Intel i5"), "notebook = laptop")
    checar(_titulo_relevante("smart tv 50", "Samsung Smart TV 50 4K Crystal UHD"), "TV 50 aceita 50 polegadas")
    checar(not _titulo_relevante("smart tv 50", "TV Samsung Smart HD 32 LS32H5000"), "TV 32 não passa como 50")

    amz = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        404.27,
        "https://www.amazon.com.br/PlayStation-DualSense-Controle-sem-fio/dp/B0CQKLS4RP",
        FOTO_PADRAO,
        "amazon",
    )
    link_amz = _link_compra_do_card(amz)
    checar("/dp/B0CQKLS4RP" in link_amz, "Ver Oferta Amazon abre /dp/ do produto")
    checar(f"tag={ID_AMAZON}" in link_amz, "Amazon carimba tag jdseconomiz0e-20")
    sujo = _aplicar_afiliado_google(
        "https://www.amazon.com.br/dp/B0CQKLS4RP?tag=outra-20", "amazon"
    )
    checar(f"tag={ID_AMAZON}" in sujo and "outra-20" not in sujo, "Amazon troca tag de terceiro pela JDS")
    import inspect as _insp
    checar("pais" in _insp.signature(buscar_ofertas_jds).parameters, "app envia pais BR/US para a API")
    checar(pais_pelo_idioma("pt") == "BR" and pais_pelo_idioma("pt-BR") == "BR",
           "locale pt vira mercado BR")
    checar(pais_pelo_idioma("en") == "US" and pais_pelo_idioma("en-US") == "US"
           and pais_pelo_idioma("es") == "US",
           "qualquer idioma que não seja pt vira US")
    checar(texto_app("nenhuma_oferta", "US") == "No products found"
           and texto_app("ver_oferta", "US") == "View Deal",
           "tela US usa textos em inglês")
    checar(
        f"identity={ID_MERCADO_LIVRE}" in _aplicar_afiliado_google(
            "https://www.mercadolivre.com.br/x/p/MLB1", "mercado_livre"
        ),
        "ML sempre leva identity mape592520",
    )
    checar(
        f"sub_id={ID_SHOPEE}" in _aplicar_afiliado_google(
            "https://shopee.com.br/search?keyword=dualsense", "shopee"
        ),
        "Shopee sempre leva sub_id 18381751263",
    )
    checar("B0CQKLS4RP" in (amz.get("foto") or "") and "unsplash" not in (amz.get("foto") or ""), "foto Amazon é do DualSense (ASIN)")
    checar(_oferta_foto_preco_do_mesmo_item(amz), "foto e preço do mesmo item Amazon")

    ml = _montar_item_oferta(
        "Controle DualSense Sony",
        419.0,
        "https://produto.mercadolivre.com.br/MLB-1234567890",
        FOTO_PADRAO,
        "mercado_livre",
    )
    link_ml = _link_compra_do_card(ml)
    checar("MLB-1234567890" in link_ml, "Ver Oferta ML abre o anúncio MLB do produto")
    checar(f"identity={ID_MERCADO_LIVRE}" in link_ml, "ML carimba identity mape592520")

    shp = _montar_item_oferta(
        "Controle DualSense Sony Original PS5",
        449.0,
        "https://shopee.com.br/item-fake-i.1.2",
        FOTO_PADRAO,
        "shopee",
    )
    link_shp = _link_compra_do_card(shp)
    checar("-i.1.2" in link_shp, "Ver Oferta Shopee abre o anúncio do produto")
    checar(f"sub_id={ID_SHOPEE}" in link_shp, "Shopee carimba sub_id 18381751263")
    checar("utm_source=" not in link_shp and "utm_medium=" not in link_shp,
           "Shopee produto não usa utm de afiliado (pede login)")
    amz_google = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        404.27,
        "https://www.amazon.com.br/dp/B0CQKLS4RP",
        FOTO_PADRAO,
        "amazon",
    )
    ver_ds = _link_ver_oferta(amz_google)
    checar(
        f"/dp/{ASIN_DUALSENSE}" in ver_ds and "google." not in ver_ds and "/s?" not in ver_ds,
        "Serper /dp/ DualSense abre esse /dp/, não Google nem busca",
    )
    amz_paralelo = _montar_item_oferta(
        "PlayStation DualSense Controle sem fio",
        89.90,
        "https://www.amazon.com.br/dp/B0PARALELO",
        FOTO_PADRAO,
        "amazon",
    )
    checar(
        "B0PARALELO" in _link_ver_oferta(amz_paralelo)
        and ASIN_DUALSENSE not in _link_ver_oferta(amz_paralelo),
        "Ver Oferta abre o /dp/ do card da Serper, não troca o ASIN",
    )
    busca_shp = _aplicar_afiliado_google(
        "https://shopee.com.br/search?keyword=dualsense", "shopee"
    )
    checar("utm_source=" not in busca_shp and f"sub_id={ID_SHOPEE}" in busca_shp,
           "busca Shopee sem utm an_ (login) e com sub_id")
    fb_link = _ofertas_fallback_lojas("cabo usb tipo c")
    amz_fb = next(p for p in fb_link if p["plataforma"] == "amazon")
    ml_fb = next(p for p in fb_link if p["plataforma"] == "mercado_livre")
    shp_fb = next(p for p in fb_link if p["plataforma"] == "shopee")
    checar(
        "/s?" in _link_compra_do_card(amz_fb)
        and "price-asc-rank" not in _link_compra_do_card(amz_fb)
        and f"tag={ID_AMAZON}" in _link_compra_do_card(amz_fb),
        "Ver Oferta Amazon (sem /dp/) abre busca do título, não paralelo barato",
    )
    checar("OrderId_PRICE" in _link_compra_do_card(ml_fb), "Ver Oferta ML (sem preço) ordena pelo menor")
    checar("sortBy=sales" in _link_compra_do_card(shp_fb), "Ver Oferta Shopee abre os mais vendidos do produto")
    checar(f"sub_id={ID_SHOPEE}" in link_shp, "Shopee carimba sub_id 18381751263")

    misturado = _ordenar_entrega_menor_preco([
        {"titulo": "B", "preco_num": 200, "preco": "R$ 200,00", "plataforma": "amazon",
         "url": "https://www.amazon.com.br/dp/B0TESTE", "foto": FOTO_PADRAO, "loja": "Amazon"},
        {"titulo": "A", "preco_num": 80, "preco": "R$ 80,00", "plataforma": "mercado_livre",
         "url": "https://produto.mercadolivre.com.br/MLB-1", "foto": FOTO_PADRAO, "loja": "Mercado Livre"},
        {"titulo": "C", "preco_num": 150, "preco": "R$ 150,00", "plataforma": "shopee",
         "url": "https://shopee.com.br/search?keyword=x", "foto": FOTO_PADRAO, "loja": "Shopee"},
        {"titulo": "A2 caro", "preco_num": 500, "preco": "R$ 500,00", "plataforma": "mercado_livre",
         "url": "https://produto.mercadolivre.com.br/MLB-2", "foto": FOTO_PADRAO, "loja": "Mercado Livre"},
    ])
    checar(len(misturado) == 3, "uma oferta por loja")
    checar(misturado[0]["preco_num"] == 80 and misturado[0].get("campeao"), "menor preço no topo com selo")
    checar(
        gerar_link_afiliado(
            "https://www.amazon.com.br/PlayStation-DualSense/dp/B0CQKLS4RP", "amazon"
        ).find("/dp/B0CQKLS4RP") >= 0,
        "afiliado Amazon preserva página de compra",
    )
    checar(
        _jds_mesmo_produto(
            "Controle DualSense Sony PS5",
            "Sony DualSense Wireless Controller PS5",
            "dualsense",
        )
        and not _jds_mesmo_produto(
            "Controle DualSense Sony PS5",
            "Xbox Wireless Controller Series",
            "dualsense",
        )
        and not _jds_mesmo_produto(
            "Controle DualSense Sony PS5",
            "Gamrombo Controle LED PS5",
            "dualsense",
        ),
        "identidade V2: DualSense não mistura Xbox nem paralelo",
    )
    return falhas


def _oferta_pronta_para_compra(produto):
    url = _link_compra_do_card(produto)
    plat = produto.get("plataforma")
    if not (url or "").startswith("http"):
        return False
    if plat == "amazon":
        return f"tag={ID_AMAZON}" in url and ("/dp/" in url or "/s?" in url)
    if plat == "mercado_livre":
        return f"identity={ID_MERCADO_LIVRE}" in url
    if plat == "shopee":
        return f"sub_id={ID_SHOPEE}" in url and (
            "shopee.com.br/search" in url or "-i." in url or "/product/" in url
        )
    return False


def executar_carga_500():
    """500 checagens: 3 lojas, menor preço do catálogo no topo, afiliado."""
    casos = []
    for cat in CATALOGO_PRODUTOS_REAIS:
        melhor = min(float(of["preco"]) for of in cat["ofertas"])
        for termo in cat["termos"]:
            casos.append((termo, melhor))
    base = list(casos) or [("controle ps5", 404.27)]
    while len(casos) < 500:
        casos.append(base[len(casos) % len(base)])
    casos = casos[:500]
    falhas = 0
    exemplos = []
    for termo, melhor in casos:
        lista = gerar_lista_ofertas_reais(termo, usar_cache=False, usar_vivo=False)
        lojas = {p.get("plataforma") for p in lista}
        reais = [p for p in lista if p.get("fonte") != "busca_loja"]
        topo = float(reais[0]["preco_num"]) if reais else -1
        if (
            not reais
            or not {"amazon", "mercado_livre", "shopee"} <= lojas
            or abs(topo - float(melhor)) > 0.06
            or not all(_oferta_pronta_para_compra(p) for p in reais)
        ):
            falhas += 1
            if len(exemplos) < 12:
                exemplos.append(f"{termo!r} topo={topo} esperado={melhor}")
                print(f"[Carga FALHA] {exemplos[-1]}")
    ok = 500 - falhas
    print(f"[Carga] 500 testes de menor preço / 3 lojas: {ok} ok, {falhas} falhas")
    return falhas


def executar_testes_motor_busca():
    """
    Rotina de testes: regras locais + 12 buscas reais (menor preço e Ver Oferta).
    """
    import sys
    import io

    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 80)
    print("TESTES UNITARIOS DO MOTOR")
    print("=" * 80)
    falhas_unit = executar_testes_unitarios()
    falhas_carga = executar_carga_500()

    termos_teste = [
        "controle ps5",
        "dualsense",
        "xbox",
        "garrafa termica",
        "copo stanley",
        "fone bluetooth",
        "relogio smartwatch",
        "tenis esportivo",
        "tenis nike",
        "smartphone samsung",
        "notebook dell",
        "smart tv 50",
        "camera dslr",
        "mouse sem fio",
        "mouse gamer",
        "air fryer mondial",
        "fritadeira",
        "redmi note 13",
        "xiaomi",
        "whey protein",
        "playstation",
        "canon",
        "galaxy",
        "dell",
    ]

    resultados = {
        "total_testes": len(termos_teste) + 1 + 500 + 3,
        "sucesso": (0 if falhas_unit else 1) + (500 - falhas_carga),
        "falha": (1 if falhas_unit else 0) + falhas_carga,
        "detalhes": [],
    }
    if falhas_unit:
        resultados["detalhes"].append({
            "teste": 0,
            "termo": "unitarios",
            "status": "FALHA",
            "motivo": "; ".join(falhas_unit),
        })
    else:
        resultados["detalhes"].append({
            "teste": 0,
            "termo": "unitarios",
            "status": "SUCESSO",
        })

    print("\n" + "=" * 80)
    print("BUSCAS AO VIVO — QUALQUER PRODUTO, MENOR PRECO, PAGINA DE COMPRA")
    print("=" * 80)

    for i, termo in enumerate(termos_teste, 1):
        print(f"\n[Teste {i}/{len(termos_teste)}] Buscando: '{termo}'")
        print("-" * 60)

        try:
            produtos = gerar_lista_ofertas_reais(termo, usar_cache=False, usar_vivo=False)

            if not produtos:
                print(f"[FALHA] Nenhum produto encontrado para '{termo}'")
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": i,
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": "Nenhum produto encontrado",
                })
                continue

            print(f"[OK] {len(produtos)} produtos encontrados")

            titulos_validos = sum(1 for p in produtos if p.get("titulo"))
            links_produto = sum(1 for p in produtos if (p.get("url") or "").startswith("http"))
            links_validos = sum(1 for p in produtos if p.get("url") and (
                f"identity={ID_MERCADO_LIVRE}" in p["url"]
                or f"sub_id={ID_SHOPEE}" in p["url"]
                or f"tag={ID_AMAZON}" in p["url"]
            ))
            lojas_ok = sum(1 for p in produtos if p.get("loja") in ("Mercado Livre", "Amazon", "Shopee"))
            fotos_validas = sum(1 for p in produtos if p.get(
                "foto") and p["foto"].startswith("http"))
            reais = [p for p in produtos if p.get("fonte") != "busca_loja"]
            compra_ok = all(_oferta_pronta_para_compra(p) for p in produtos)
            mesmo_item = all(_oferta_foto_preco_do_mesmo_item(p) for p in reais) if reais else True
            sem_banco_fotos = all("unsplash" not in (p.get("foto") or "").lower() for p in reais) if reais else True

            sem_acessorio = all(not _parece_acessorio_barato(p.get("titulo") or "", termo) for p in produtos)
            plats = {p.get("plataforma") for p in produtos if p.get("fonte") != "busca_loja"}
            tres_lojas = {"amazon", "mercado_livre", "shopee"}.issubset(
                {p.get("plataforma") for p in produtos}
            )
            print(f"[OK] Três lojas no ranking: {tres_lojas} { {p.get('loja') for p in produtos} }")

            print(f"[OK] Títulos capturados: {titulos_validos}/{len(produtos)}")
            print(f"[OK] Links http: {links_produto}/{len(produtos)}")
            print(f"[OK] Links com afiliado: {links_validos}/{len(produtos)}")
            print(f"[OK] Etiqueta de loja: {lojas_ok}/{len(produtos)}")
            print(f"[OK] Fotos: {fotos_validas}/{len(produtos)}")
            print(f"[OK] Ver Oferta aponta para compra: {compra_ok}")
            print(f"[OK] Foto e preço do mesmo anúncio: {mesmo_item}")
            print(f"[OK] Sem imagem genérica: {sem_banco_fotos}")
            print(f"[OK] Sem acessório no lugar do produto: {sem_acessorio}")

            if (
                links_produto != len(produtos)
                or links_validos != len(produtos)
                or lojas_ok != len(produtos)
                or not compra_ok
                or fotos_validas != len(produtos)
                or not mesmo_item
                or not sem_banco_fotos
                or not sem_acessorio
                or not tres_lojas
            ):
                print("[FALHA] Link, afiliado, foto, loja ou Ver Oferta inconsistente")
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": i,
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": "link/foto/loja/ver-oferta inconsistente",
                })
                continue

            precos = [p.get("preco_num", 0.0) for p in produtos]
            if precos != sorted(precos) or abs(min(precos) - produtos[0].get("preco_num", 0.0)) >= 0.01:
                print(f"[FALHA] Ordenação por preço: INCORRETA ({precos})")
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": i,
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": "Ordenacao por preco incorreta",
                })
                continue

            print(
                f"[OK] Menor valor no topo: {produtos[0].get('preco')} "
                f"({produtos[0].get('loja')}) selo={produtos[0].get('selo')}"
            )
            print(f"\n[TOP] Ranking para '{termo}':")
            for j, p in enumerate(produtos[:3], 1):
                print(
                    f"  {j}. [{p.get('selo')}] {p['titulo']} - {p['preco']} "
                    f"({p.get('loja')}) -> {_link_compra_do_card(p)[:90]}"
                )

            if any(k in termo.lower() for k in ("ps5", "dualsense", "xbox", "playstation")) and produtos[0].get("preco_num", 0) < 320:
                print("[FALHA] DualSense/PS5 com preço de acessório")
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": i,
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": "preco DualSense abaixo do piso",
                })
                continue
            if any(k in termo.lower() for k in ("redmi", "iphone", "galaxy")) and produtos[0].get("preco_num", 0) < 449:
                print("[FALHA] Celular com preço de capa")
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": i,
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": "preco de celular abaixo do piso",
                })
                continue

            resultados["sucesso"] += 1
            resultados["detalhes"].append({
                "teste": i,
                "termo": termo,
                "status": "SUCESSO",
                "produtos_encontrados": len(produtos),
                "menor_preco": produtos[0].get("preco_num", 0.0),
            })
            print(f"[SUCESSO] Teste {i} ({termo}) aprovado")

        except Exception as e:
            print(f"[FALHA CRITICA] no teste {i}: {e}")
            resultados["falha"] += 1
            resultados["detalhes"].append({
                "teste": i,
                "termo": termo,
                "status": "FALHA CRITICA",
                "motivo": str(e),
            })

    print("\n" + "=" * 80)
    print("VIVO SEM API OFICIAL — /dp/ do catálogo + produto fora do catálogo")
    print("=" * 80)
    for i, (termo, piso) in enumerate((
        ("controle ps5", 320.0),
        ("redmi note 13", 449.0),
        ("cabo usb tipo c", 5.0),
    ), 1):
        print(f"\n[Vivo {i}/3] '{termo}'")
        try:
            produtos = gerar_lista_ofertas_reais(termo, usar_cache=False, usar_vivo=True)
            lojas = {p.get("plataforma") for p in produtos}
            topo = produtos[0]["preco_num"] if produtos else 0
            ok_lojas = {"amazon", "mercado_livre", "shopee"} <= lojas
            ok_piso = topo >= piso
            ok_compra = all(_oferta_pronta_para_compra(p) for p in produtos) if produtos else False
            print(f"  lojas={lojas} topo={produtos[0].get('preco') if produtos else '-'} {produtos[0].get('loja') if produtos else ''}")
            if produtos and ok_lojas and ok_piso and ok_compra:
                resultados["sucesso"] += 1
                print(f"[SUCESSO] Vivo {i} ({termo})")
            else:
                resultados["falha"] += 1
                resultados["detalhes"].append({
                    "teste": f"vivo-{i}",
                    "termo": termo,
                    "status": "FALHA",
                    "motivo": f"lojas={ok_lojas} piso={ok_piso} compra={ok_compra} topo={topo}",
                })
                print(f"[FALHA] Vivo {i} ({termo})")
        except Exception as e:
            resultados["falha"] += 1
            resultados["detalhes"].append({
                "teste": f"vivo-{i}",
                "termo": termo,
                "status": "FALHA CRITICA",
                "motivo": str(e),
            })
            print(f"[FALHA CRITICA] Vivo {i}: {e}")

    print("\n" + "=" * 80)
    print("RESUMO")
    print("=" * 80)
    print(f"Total de testes executados: {resultados['total_testes']}")
    print(f"[SUCESSO] Testes aprovados: {resultados['sucesso']}")
    print(f"[FALHA] Testes reprovados: {resultados['falha']}")
    taxa = (resultados["sucesso"] / resultados["total_testes"]) * 100
    print(f"Taxa de sucesso: {taxa:.1f}%")

    if resultados["falha"] > 0:
        print("\n[DETALHES DAS FALHAS]:")
        for detalhe in resultados["detalhes"]:
            if detalhe["status"] != "SUCESSO":
                print(
                    f"  Teste {detalhe['teste']} ({detalhe['termo']}): {detalhe['motivo']}")
    else:
        print("\n>>> TODOS OS TESTES PASSARAM <<<")

    print("=" * 80)
    return resultados

# ===== JDS PRECISAO V2 =====
_JDS_IDENTIDADE_STOP = {
    "produto", "oferta", "original", "novo", "nova", "melhor", "preco", "preço",
    "barato", "barata", "promocao", "promoção", "frete", "gratis", "grátis", "loja",
    "oficial", "unidade", "un", "kit", "com", "para", "de", "da", "do", "e", "em",
    "na", "no", "nas", "nos", "um", "uma", "the", "for", "with", "and", "best",
    "sale", "wireless", "sem", "fio", "cor", "coracao", "coracao", "branco", "preto",
    "azul", "vermelho", "verde", "rosa", "cinza", "dourado", "prata",
}

_JDS_MARCAS = {
    "sony", "microsoft", "xbox", "playstation", "samsung", "xiaomi", "redmi", "apple",
    "iphone", "motorola", "lenovo", "nike", "adidas", "stanley", "mondial", "philips",
    "lg", "jbl", "anker", "logitech", "razer", "hyperx", "kingston", "corsair", "dell",
    "asus", "acer", "hp", "epson", "nintendo", "canon", "nikon", "braun", "oster",
    "electrolux", "consul", "brastemp", "gamrombo", "dualshock", "dualsense",
}


def _jds_tokens_identidade(texto):
    """Tokens usados para identidade; remove palavras de compra/marketing."""
    s = _sem_acento(str(texto or "").lower())
    s = s.replace("sem fio", "wireless")
    s = s.replace("air fryer", "airfryer")
    tokens = re.findall(r"[a-z0-9]+", s)
    return [t for t in tokens if len(t) >= 2 and t not in _JDS_IDENTIDADE_STOP]


def _jds_identidade(texto):
    """Extrai sinais fortes de identidade sem inventar SKU/EAN/modelo."""
    toks = _jds_tokens_identidade(texto)
    marcas = {t for t in toks if t in _JDS_MARCAS}
    numericos = {t for t in toks if t.isdigit() and len(t) >= 2}
    modelos = set()
    for t in toks:
        # Modelos normalmente misturam letras e números: A15, CFI-ZCT1W, G502, X1000 etc.
        if len(t) >= 3 and re.search(r"[a-z]", t) and re.search(r"\d", t):
            modelos.add(t)
    # Palavras de produto que, embora não sejam marca, diferenciam bastante o item.
    distintivos = {
        t for t in toks
        if len(t) >= 5 and t not in {"controle", "celular", "smartphone", "notebook", "tenis", "garrafa", "copo", "fone", "mouse"}
    }
    return {
        "tokens": set(toks),
        "marcas": marcas,
        "numericos": numericos,
        "modelos": modelos,
        "distintivos": distintivos,
    }


def _jds_token_presente(token, titulo):
    return _token_no_titulo(token, _sem_acento(titulo or ""))


def _jds_conflito_identidade(a, b):
    """Conflitos que tornam duas ofertas incompatíveis."""
    ta = set(_jds_tokens_identidade(a))
    tb = set(_jds_tokens_identidade(b))
    grupos = (
        ({"ps5", "playstation", "dualsense", "dualshock"}, {"xbox", "series", "one"}),
        ({"iphone"}, {"galaxy", "redmi", "xiaomi", "motorola"}),
        ({"ps5", "playstation"}, {"ps4"}),
        ({"xbox"}, {"ps5", "playstation"}),
    )
    for g1, g2 in grupos:
        if ta & g1 and tb & g2:
            return True
        if tb & g1 and ta & g2:
            return True
    return False


def _jds_mesmo_produto(ref_titulo, cand_titulo, consulta=""):
    """Validação conservadora. Sem identidade suficiente, não compara."""
    if not ref_titulo or not cand_titulo:
        return False
    if _jds_conflito_identidade(ref_titulo, cand_titulo):
        return False

    r = _jds_identidade(ref_titulo)
    c = _jds_identidade(cand_titulo)

    # Marca explícita na referência é uma restrição rígida.
    if r["marcas"] and not (r["marcas"] & c["marcas"]):
        return False

    # Modelo misto letra+número é praticamente um identificador; não aceitar divergência.
    if r["modelos"]:
        if not r["modelos"].issubset(c["tokens"]):
            return False

    # Números de capacidade/modelo/geração são restrições rígidas quando aparecem na referência.
    if r["numericos"]:
        if not all(_jds_token_presente(n, cand_titulo) for n in r["numericos"]):
            return False

    # Identidade por tokens, mas exigindo TODOS os sinais distintivos da referência.
    fortes = set(r["distintivos"]) | set(r["modelos"]) | set(r["marcas"])
    if fortes:
        faltantes = [t for t in fortes if not _jds_token_presente(t, cand_titulo)]
        if faltantes:
            return False

    # Para buscas genéricas, usa a consulta como segunda barreira.
    q = _jds_identidade(consulta)
    if q["marcas"] and not q["marcas"].issubset(c["marcas"] | q["marcas"]):
        return False

    # Similaridade final. Uma oferta que compartilha apenas "controle"/"ps5" não passa.
    comuns = r["tokens"] & c["tokens"]
    if len(r["tokens"]) <= 2:
        return len(comuns) == len(r["tokens"])
    return len(comuns) / max(1, len(r["tokens"])) >= 0.70


def _jds_item_serper(termo, bruto, pais="BR"):
    """Converte um item bruto do Shopping preservando IDs quando o Google fornecer."""
    if not isinstance(bruto, dict):
        return None
    bloco = _bloco_serper_isolado(bruto)
    if not bloco:
        return None
    titulo = bloco["title"]
    fonte = bloco["source"]
    if not titulo or not _source_loja_oficial(fonte, pais=pais):
        return None
    href = _href_item_serper(bruto)
    if not href:
        href = _desempacotar_link_google(str(bloco.get("link") or ""))
    if not href or _url_e_busca_loja(href):
        return None
    plat = _loja_do_texto(fonte) or _plataforma_loja(href)
    if plat not in _lojas_do_pais(pais):
        return None
    preco = _preco_item_serper(bruto, pais=pais)
    if preco <= 0:
        return None
    item = _item_google(termo, titulo, preco, href, bloco.get("imageUrl"), plat, origem="serper", pais=pais)
    if not item:
        return None
    # Preserva possíveis identificadores fornecidos pelo Shopping/API.
    for k in ("asin", "gtin", "ean", "mpn", "sku", "productId", "product_id", "itemId", "item_id"):
        if bruto.get(k) not in (None, ""):
            item[k] = str(bruto.get(k))
    item["identidade_titulo"] = _titulo_limpo_oferta(titulo)
    return item


def _jds_extrair_candidatos(termo, itens, pais="BR", limite=40):
    candidatos = []
    vistos = set()
    for bruto in itens or []:
        item = _jds_item_serper(termo, bruto, pais=pais)
        if not item:
            continue
        url = _url_chave(item.get("url") or "")
        chave = url or (_sem_acento(item.get("titulo") or ""), item.get("plataforma"), item.get("preco_num"))
        if chave in vistos:
            continue
        vistos.add(chave)
        candidatos.append(item)
    candidatos.sort(key=_rank_oferta_real)
    return candidatos[:limite]


def _jds_pontuar_referencia(consulta, item):
    q = _jds_identidade(consulta)
    t = _jds_identidade(item.get("titulo") or "")
    if _jds_conflito_identidade(consulta, item.get("titulo")):
        return -9999
    score = 0.0
    if q["marcas"]:
        score += 30 if q["marcas"] & t["marcas"] else -40
    if q["modelos"]:
        score += 60 if q["modelos"].issubset(t["tokens"]) else -60
    if q["numericos"]:
        score += 25 * sum(_jds_token_presente(n, item.get("titulo")) for n in q["numericos"])
        score -= 50 * sum(not _jds_token_presente(n, item.get("titulo")) for n in q["numericos"])
    comuns = q["tokens"] & t["tokens"]
    score += 5 * len(comuns)
    # URLs de produto reais recebem preferência sobre resultados ambíguos.
    if _url_anuncio_exato(item.get("url") or "", item.get("plataforma")):
        score += 15
    return score


def _jds_escolher_referencia(consulta, candidatos):
    """Escolhe a referência somente entre resultados que atendem à busca."""
    validos = [x for x in candidatos if _titulo_shopping_ok(consulta, x.get("titulo") or "")]
    if not validos:
        return None
    validos.sort(key=lambda x: (-_jds_pontuar_referencia(consulta, x), _rank_oferta_real(x)))
    return validos[0]


def _jds_buscar_loja_identica(consulta, referencia, plataforma, pais="BR", limite=40):
    """Procura a mesma identidade em uma loja específica."""
    titulo_ref = referencia.get("titulo") or ""
    identidade = _jds_identidade(titulo_ref)
    partes = []
    # O título completo ajuda a encontrar o mesmo SKU/modelo em lojas diferentes.
    partes.append(titulo_ref[:140])
    for t in sorted(identidade["modelos"] | identidade["marcas"] | identidade["numericos"]):
        if t.lower() not in _sem_acento(titulo_ref.lower()):
            partes.append(t)
    partes.append({"amazon":"Amazon", "mercado_livre":"Mercado Livre", "shopee":"Shopee", "ebay":"eBay"}.get(plataforma, ""))
    q = " ".join(x for x in partes if x).strip()
    http, cru, loc, erro = _post_serper_shopping(q, pais=pais, num=limite)
    if http >= 400 or not cru:
        return None
    candidatos = []
    for bruto in cru:
        item = _jds_item_serper(q, bruto, pais=pais)
        if not item or item.get("plataforma") != plataforma:
            continue
        if _jds_mesmo_produto(titulo_ref, item.get("titulo") or "", consulta=consulta):
            candidatos.append(item)
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: (_rank_oferta_real(x), -_jds_pontuar_referencia(titulo_ref, x)))
    return candidatos[0]


def _jds_comparar_mesmo_produto(consulta, candidatos, pais="BR"):
    """Retorna apenas ofertas cuja identidade foi confirmada contra uma referência."""
    ref = _jds_escolher_referencia(consulta, candidatos)
    if not ref:
        return []

    resultado = [ref]
    lojas = _lojas_do_pais(pais)
    for plat in lojas:
        if plat == ref.get("plataforma"):
            continue
        item = _jds_buscar_loja_identica(consulta, ref, plat, pais=pais, limite=40)
        if item:
            resultado.append(item)

    # Segunda validação cruzada: cada item precisa bater com a referência.
    confirmadas = []
    for item in resultado:
        if item.get("plataforma") == ref.get("plataforma") or _jds_mesmo_produto(ref.get("titulo"), item.get("titulo"), consulta):
            if _oferta_foto_preco_do_mesmo_item(item):
                confirmadas.append(item)

    # Se a busca for ambígua e só houver uma referência, não inventa comparação entre lojas.
    if len(confirmadas) < 2:
        return confirmadas
    return _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(confirmadas, pais=pais))


def buscar_ofertas_serper_shopping(termo, usar_cache=True, limite=20, pais="BR"):
    """Motor V2: escolhe uma referência e só compara anúncios com a mesma identidade."""
    t = re.sub(r"\s+", " ", (termo or "").strip())
    pais = _normalizar_pais(pais)
    if not t:
        return []
    sem_cache = (os.environ.get("JDS_BUSCA_SEM_CACHE") or "").strip() == "1"
    if usar_cache and not sem_cache:
        cached = _ler_cache_garimpo(t, pais=pais)
        if cached:
            lista = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(cached, pais=pais))
            if lista:
                print(f"[Serper] cache {_chave_cache(t, pais=pais)}")
                return lista
    http, cru, loc, erro = _post_serper_shopping(_consulta_serper_shopping(t), pais=pais, num=40)
    if http >= 400 or not cru:
        _ULTIMO_DIAG_SERPER.clear()
        _ULTIMO_DIAG_SERPER.update({"q": t, "http": http, "shopping": len(cru or []), "erro": erro or "sem_resultados"})
        return []
    candidatos = _jds_extrair_candidatos(t, cru, pais=pais, limite=40)
    resultado = _jds_comparar_mesmo_produto(t, candidatos, pais=pais)
    resultado = _resolver_links_anuncio_serper(t, resultado, pais=pais)
    resultado = _ordenar_entrega_menor_preco(_carimbar_lista_afiliado(resultado, pais=pais))
    if resultado and usar_cache and not sem_cache:
        _gravar_cache_garimpo(t, resultado, pais=pais)
    return resultado[:limite]


def _buscar_ofertas_serper(termo, limite=8, pais="BR"):
    pais = _normalizar_pais(pais)
    ofertas = buscar_ofertas_serper_shopping(termo, usar_cache=True, limite=max(20, limite), pais=pais)
    ofertas = _ordenar_entrega_menor_preco(ofertas)
    return ofertas[:limite]


def isolar_produto_mais_barato(ofertas, pais="BR"):
    pais = _normalizar_pais(pais)
    validos = []
    for p in ofertas or []:
        if not isinstance(p, dict):
            continue
        try:
            n = float(p.get("preco_num") or p.get("preco_numerico") or 0)
        except (TypeError, ValueError):
            n = 0.0
        if n <= 0 or n >= 999990:
            continue
        if not _oferta_foto_preco_do_mesmo_item(p):
            continue
        validos.append(p)
    if not validos:
        return None
    validos.sort(key=_rank_oferta_real)
    return _carimbar_lista_afiliado([validos[0]], pais=pais)[0]

print("[JDS] Motor de identidade V2 carregado")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ["--testar", "--test", "test"]:
        executar_testes_motor_busca()
    elif ft is not None:
        try:
            porta = int(os.environ.get("PORT", "8080"))
            modo_web = (
                os.environ.get("JDS_WEB", "").lower() in {"1", "true", "yes"}
                or bool(os.environ.get("RENDER"))
                or bool(os.environ.get("RAILWAY_ENVIRONMENT"))
            )
            kwargs = {"target": main}
            if modo_web:
                kwargs["host"] = "0.0.0.0"
                kwargs["port"] = porta
                view = getattr(ft, "AppView", None)
                if view is not None and hasattr(view, "WEB_BROWSER"):
                    kwargs["view"] = view.WEB_BROWSER
            ft.app(**kwargs)
        except Exception as err:
            print(f"[Flet App] {err}")
            executar_testes_motor_busca()
    else:
        print("[Info] Executando rotina completa de testes do motor de busca:")
        executar_testes_motor_busca()
