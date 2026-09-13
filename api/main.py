"""API de busca da JDS Economiza — deploy no Railway."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

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
    ID_MERCADO_LIVRE,
    ID_SHOPEE,
    gerar_lista_ofertas_reais,
)

app = FastAPI(
    title="JDS Economiza API",
    version="1.0.0",
    description="Garimpa o menor preço em Amazon, Mercado Livre e Shopee.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "servico": "jds-economiza",
        "afiliados": {
            "amazon": ID_AMAZON,
            "shopee": ID_SHOPEE,
            "mercado_livre": ID_MERCADO_LIVRE,
        },
        "chaves": {
            "amazon_paapi": bool(os.environ.get("AMAZON_ACCESS_KEY")),
            "shopee_affiliate": bool(os.environ.get("SHOPEE_APP_ID")),
            "mercadolivre": True,
        },
    }


@app.get("/garimpar")
def garimpar(q: str = Query(..., min_length=1, max_length=120, description="Produto")):
    ofertas = gerar_lista_ofertas_reais(q.strip(), usar_cache=True)
    campeao = ofertas[0] if ofertas else None
    return {
        "termo": q.strip(),
        "total": len(ofertas),
        "menor_preco": None if not campeao else {
            "preco": campeao.get("preco"),
            "loja": campeao.get("loja"),
            "titulo": campeao.get("titulo"),
            "url": campeao.get("url"),
        },
        "ofertas": ofertas,
    }
