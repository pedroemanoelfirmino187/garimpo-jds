"""API de busca da JDS Economiza — deploy no Railway.

Módulo: api.main (uvicorn api.main:app ou uvicorn api:app).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from garimpo_jds import (  # noqa: E402
    ID_AMAZON,
    ID_AMAZON_US,
    ID_MERCADO_LIVRE,
    ID_SHOPEE,
    _chave_cache,
    _chaves_env,
    _normalizar_pais,
    buscar_ofertas_por_pais,
    buscar_ofertas_serper_shopping,
    serializar_lista_app,
)

app = FastAPI(
    title="JDS Economiza API",
    version="1.2.0",
    description="Garimpa o menor preço no Google (Serper): BR (Amazon/ML/Shopee) ou US (Amazon/eBay).",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class GarimpoPedido(BaseModel):
    q: str = Field(..., min_length=1, max_length=120, description="Produto buscado")
    pais: str = Field(default="BR", max_length=16, description="BR ou US")
    country: str | None = Field(default=None, max_length=16, description="Alias de pais")


def _pais_pedido(pedido: GarimpoPedido) -> str:
    return _normalizar_pais(pedido.country or pedido.pais or "BR")


def _autorizar_app(
    authorization: str | None = Header(default=None),
    x_jds_token: str | None = Header(default=None, alias="X-JDS-TOKEN"),
):
    """Se JDS_API_TOKEN existir, o app móvel precisa enviar o mesmo valor."""
    esperado = (os.environ.get("JDS_API_TOKEN") or "").strip()
    if not esperado:
        return True
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    recebido = (x_jds_token or bearer or "").strip()
    if recebido != esperado:
        raise HTTPException(status_code=401, detail="token inválido")
    return True


def _resposta_ofertas(termo, ofertas, pais="BR"):
    pais = _normalizar_pais(pais)
    lista = serializar_lista_app(ofertas or [], pais=pais)
    campeao = lista[0] if lista else None
    return {
        "termo": termo,
        "pais": pais,
        "total": len(lista),
        "cache": _chave_cache(termo, pais=pais),
        "menor_preco": None if not campeao else {
            "titulo": campeao.get("titulo"),
            "preco_formatado": campeao.get("preco_formatado"),
            "preco_numerico": campeao.get("preco_numerico"),
            "loja": campeao.get("loja"),
            "link_afiliado": campeao.get("link_afiliado"),
            "imagem": campeao.get("imagem"),
        },
        "ofertas": lista,
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "servico": "jds-economiza",
        "afiliados": {
            "amazon_br": ID_AMAZON,
            "amazon_us": ID_AMAZON_US,
            "amazon": ID_AMAZON,
            "shopee": ID_SHOPEE,
            "mercado_livre": ID_MERCADO_LIVRE,
        },
        "chaves": {
            "amazon_paapi": bool(os.environ.get("AMAZON_ACCESS_KEY")),
            "shopee_affiliate": bool(os.environ.get("SHOPEE_APP_ID")),
            "mercadolivre": bool(os.environ.get("MELI_ACCESS_TOKEN")),
            "zenrows": bool(_chaves_env("ZENROWS_API_KEY", "ZENROWS_KEY")),
            "scrapingant": bool(_chaves_env(
                "SCRAPINGANT_API_KEY",
                "SCRAPING_ANT_KEY",
                "SCRAPINGANT_KEY",
                "SCRAPING_ANT_KEY_2",
                "SCRAPINGANT_API_KEY_2",
            )),
            "serper": bool(_chaves_env("SERPER_API_KEY", "SERPER_KEY")),
            "app_token": bool((os.environ.get("JDS_API_TOKEN") or "").strip()),
            "cache_sqlite": True,
            "cache_ttl_horas": 2,
        },
    }


@app.get("/garimpar")
def garimpar_get(
    q: str = Query(..., min_length=1, max_length=120, description="Produto"),
    pais: str = Query("BR", max_length=16, description="BR ou US"),
    country: str | None = Query(None, max_length=16),
    _: bool = Depends(_autorizar_app),
):
    termo = q.strip()
    mercado = _normalizar_pais(country or pais)
    ofertas = buscar_ofertas_por_pais(termo, pais=mercado, usar_cache=True)
    return _resposta_ofertas(termo, ofertas, pais=mercado)


@app.post("/garimpar")
def garimpar_post(pedido: GarimpoPedido, _: bool = Depends(_autorizar_app)):
    """Rota do app: corpo JSON com q e pais (BR|US), token opcional, Serper no servidor."""
    termo = pedido.q.strip()
    mercado = _pais_pedido(pedido)
    ofertas = buscar_ofertas_por_pais(termo, pais=mercado, usar_cache=True)
    return _resposta_ofertas(termo, ofertas, pais=mercado)


@app.post("/shopping")
def shopping_serper(pedido: GarimpoPedido, _: bool = Depends(_autorizar_app)):
    """Só Google Shopping (Serper), cache antes da API, lojas do país."""
    termo = pedido.q.strip()
    mercado = _pais_pedido(pedido)
    ofertas = buscar_ofertas_serper_shopping(termo, usar_cache=True, pais=mercado)
    return _resposta_ofertas(termo, ofertas, pais=mercado)
