"""API de busca da JDS Economiza — deploy no Railway.

Módulo: api.main (uvicorn api.main:app ou uvicorn api:app).
Busca só Serper.dev, mercado BR (pt) ou US (en).
"""
from __future__ import annotations

import hmac
import json
import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    ultimo_diag_serper,
    _arquivo_cache_sqlite,
    _chave_cache,
    _chaves_env,
    _normalizar_pais,
    buscar_ofertas_jds_shopping,
    buscar_ofertas_por_pais,
    buscar_ofertas_serper_shopping,
    isolar_produto_mais_barato,
    mensagem_servidor,
    serializar_lista_app,
    serializar_oferta_app,
)

app = FastAPI(
    title="JDS Economiza API",
    version="1.3.1",
    description="Garimpa o menor preço: SearchApi (BR/US) com fallback Serper.",
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


def _pais_do_request(request: Request) -> str:
    estado = getattr(request.state, "pais", None)
    if estado:
        return _normalizar_pais(estado)
    return _normalizar_pais(
        request.query_params.get("country") or request.query_params.get("pais") or "BR"
    )


def _json_erro(pais, status_http, chave="erro_servidor", extra=None):
    pais = _normalizar_pais(pais)
    texto = mensagem_servidor(chave, pais)
    corpo = {
        "ok": False,
        "status": "error",
        "pais": pais,
        "mensagem": texto,
        "message": texto,
        "detail": texto,
    }
    if extra:
        corpo.update(extra)
    return JSONResponse(status_code=status_http, content=corpo)


@app.middleware("http")
async def _capturar_pais(request: Request, call_next):
    pais = _normalizar_pais(
        request.query_params.get("country") or request.query_params.get("pais") or "BR"
    )
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            bruto = await request.body()
            if bruto:
                dados = json.loads(bruto)
                if isinstance(dados, dict):
                    pais = _normalizar_pais(dados.get("country") or dados.get("pais") or pais)
        except Exception:
            pass
    request.state.pais = pais
    try:
        return await call_next(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return _json_erro(pais, 401, "token_invalido")
        if exc.status_code >= 500:
            return _json_erro(pais, exc.status_code, "erro_servidor")
        detalhe = exc.detail if isinstance(exc.detail, str) else mensagem_servidor("erro_servidor", pais)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "status": "error",
                "pais": pais,
                "mensagem": detalhe,
                "message": detalhe,
                "detail": detalhe,
            },
        )
    except Exception:
        return _json_erro(pais, 500, "erro_servidor")


def _token_recebido(authorization: str | None, x_jds_token: str | None) -> str:
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    return (x_jds_token or bearer or "").strip()


def _autorizar_app(
    request: Request,
    authorization: str | None = Header(default=None),
    x_jds_token: str | None = Header(default=None, alias="X-JDS-TOKEN"),
):
    """Se JDS_API_TOKEN existir, o app móvel precisa enviar o mesmo valor."""
    esperado = (os.environ.get("JDS_API_TOKEN") or "").strip()
    if not esperado:
        return True
    recebido = _token_recebido(authorization, x_jds_token)
    if not recebido or not hmac.compare_digest(recebido, esperado):
        raise HTTPException(
            status_code=401,
            detail=mensagem_servidor("token_invalido", _pais_do_request(request)),
        )
    return True


def _autorizar_garimpar(
    request: Request,
    authorization: str | None = Header(default=None),
    x_jds_token: str | None = Header(default=None, alias="X-JDS-TOKEN"),
):
    """GET/POST /garimpar: 401 sem token ou com token errado quando JDS_API_TOKEN existe."""
    return _autorizar_app(request, authorization=authorization, x_jds_token=x_jds_token)


def _resposta_ofertas(termo, ofertas, pais="BR"):
    pais = _normalizar_pais(pais)
    lista = serializar_lista_app(ofertas or [], pais=pais)
    campeao = isolar_produto_mais_barato(lista, pais=pais)
    if campeao:
        campeao = serializar_oferta_app(campeao, pais=pais)
    vazio = not lista
    texto = mensagem_servidor("nenhum_produto" if vazio else "ok", pais)
    return {
        "ok": not vazio,
        "status": "empty" if vazio else "ok",
        "mensagem": texto,
        "message": texto,
        "termo": termo,
        "pais": pais,
        "total": len(lista),
        "cache": _chave_cache(termo, pais=pais),
        "titulo": None if not campeao else campeao.get("titulo"),
        "loja": None if not campeao else campeao.get("loja"),
        "link": None if not campeao else campeao.get("link_afiliado"),
        "menor_preco": None if not campeao else {
            "titulo": campeao.get("titulo"),
            "loja": campeao.get("loja"),
            "link": campeao.get("link_afiliado"),
            "preco_formatado": campeao.get("preco_formatado"),
            "preco_numerico": campeao.get("preco_numerico"),
            "link_afiliado": campeao.get("link_afiliado"),
            "imagem": campeao.get("imagem"),
        },
        "ofertas": lista,
        "diagnostico": ultimo_diag_serper(),
    }


@app.exception_handler(HTTPException)
async def _http_erro(request: Request, exc: HTTPException):
    pais = _pais_do_request(request)
    if exc.status_code == 401:
        return _json_erro(pais, 401, "token_invalido")
    if exc.status_code >= 500:
        return _json_erro(pais, exc.status_code, "erro_servidor")
    detalhe = exc.detail if isinstance(exc.detail, str) else mensagem_servidor("erro_servidor", pais)
    if _normalizar_pais(pais) == "US":
        mapa = {
            "Nenhum produto encontrado": mensagem_servidor("nenhum_produto", "US"),
            "Erro no servidor": mensagem_servidor("erro_servidor", "US"),
            "token inválido": mensagem_servidor("token_invalido", "US"),
        }
        detalhe = mapa.get(detalhe, detalhe)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "status": "error",
            "pais": pais,
            "mensagem": detalhe,
            "message": detalhe,
            "detail": detalhe,
        },
    )


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return await _http_erro(request, exc)
    return _json_erro(_pais_do_request(request), 500, "erro_servidor")


@app.get("/health")
def health():
    return {
        "ok": True,
        "servico": "jds-economiza",
        "fonte": "searchapi+serper",
        "deploy": "v44",
        "mercados": ["BR", "US"],
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
            "searchapi": bool(_chaves_env("SEARCHAPI_API_KEY", "SEARCHAPI_KEY")),
            "app_token": bool((os.environ.get("JDS_API_TOKEN") or "").strip()),
            "cache_sqlite": True,
            "cache_ttl_horas": 2,
            "cache_arquivo": str(_arquivo_cache_sqlite()),
            "cache_persistente": bool((os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()),
        },
    }


def _buscar_serper_pais(termo, pais):
    try:
        return buscar_ofertas_jds_shopping(termo, usar_cache=True, pais=pais, limite=20)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=mensagem_servidor("erro_servidor", pais),
        )


@app.get("/admin/searchapi")
def admin_searchapi(_: bool = Depends(_autorizar_app)):
    """Uso de créditos SearchApi. Exige JDS_API_TOKEN. Fora do /garimpar."""
    if not (os.environ.get("JDS_API_TOKEN") or "").strip():
        raise HTTPException(status_code=404, detail="not found")
    from jds_searchapi import consultar_uso_searchapi

    return consultar_uso_searchapi()


@app.get("/garimpar")
def garimpar_get(
    q: str = Query(..., min_length=1, max_length=120, description="Produto"),
    pais: str = Query("BR", max_length=16, description="BR ou US"),
    country: str | None = Query(None, max_length=16),
    _: bool = Depends(_autorizar_garimpar),
):
    termo = q.strip()
    mercado = _normalizar_pais(country or pais)
    ofertas = _buscar_serper_pais(termo, mercado)
    return _resposta_ofertas(termo, ofertas, pais=mercado)


@app.post("/garimpar")
def garimpar_post(pedido: GarimpoPedido, _: bool = Depends(_autorizar_garimpar)):
    """Rota do app: corpo JSON com q e pais (BR|US). Token obrigatório se JDS_API_TOKEN existir."""
    termo = pedido.q.strip()
    mercado = _pais_pedido(pedido)
    ofertas = _buscar_serper_pais(termo, mercado)
    return _resposta_ofertas(termo, ofertas, pais=mercado)


@app.post("/shopping")
def shopping_serper(pedido: GarimpoPedido, _: bool = Depends(_autorizar_app)):
    """Só Google Shopping (Serper), cache antes da API, lojas do país."""
    termo = pedido.q.strip()
    mercado = _pais_pedido(pedido)
    try:
        ofertas = buscar_ofertas_serper_shopping(termo, usar_cache=True, pais=mercado)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=mensagem_servidor("erro_servidor", mercado),
        )
    return _resposta_ofertas(termo, ofertas, pais=mercado)
