"""Smoke test contra a API já publicada.

Uso:
  JDS_API_URL=https://seu-dominio.up.railway.app python scripts/live_smoke.py

Opcional:
  JDS_API_TOKEN=...   (se a API exigir token)

Este script NÃO imprime nem envia segredos. Ele só valida a resposta JSON e
as invariantes de formato. A qualidade do match é avaliada pelos testes de
casos reais; para isso, use as buscas listadas abaixo e confira o anúncio.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote

import requests

BASE = (os.environ.get("JDS_API_URL") or "").rstrip("/")
TOKEN = (os.environ.get("JDS_API_TOKEN") or "").strip()
QUERIES = [
    "controle ps5",
    "controle ps5 sony",
    "controle ps5 sony branco",
    "iphone 15 128gb",
    "samsung galaxy s24",
    "jbl tune 520bt",
    "ps5",
    "nintendo switch oled",
]

if not BASE:
    print("ERRO: defina JDS_API_URL com a URL pública do Railway.")
    sys.exit(2)

headers = {"X-JDS-TOKEN": TOKEN} if TOKEN else {}

try:
    health = requests.get(f"{BASE}/health", headers=headers, timeout=30)
except requests.RequestException as exc:
    print(f"ERRO DE REDE ao acessar {BASE}/health: {exc}")
    print("Verifique DNS, domínio do Railway e conectividade deste ambiente.")
    sys.exit(3)
print(f"HEALTH {health.status_code}")
health.raise_for_status()

failures = []
for query in QUERIES:
    url = f"{BASE}/garimpar?q={quote(query)}&pais=BR"
    try:
        try:
            r = requests.get(url, headers=headers, timeout=60)
        except requests.RequestException as exc:
            failures.append((query, f"erro de rede: {exc}"))
            continue
        if r.status_code != 200:
            failures.append((query, f"HTTP {r.status_code}"))
            continue
        data = r.json()
        if not isinstance(data, dict) or "ofertas" not in data:
            failures.append((query, "JSON sem campo ofertas"))
            continue
        ofertas = data.get("ofertas") or []
        print(f"OK {query!r}: {len(ofertas)} oferta(s)")
        for i, item in enumerate(ofertas, 1):
            for key in ("titulo", "preco_numerico", "link"):
                if not item.get(key):
                    failures.append((query, f"oferta {i} sem {key}"))
            link = str(item.get("link") or "")
            if any(x in link.lower() for x in ("/search", "/lista/", "google.com/search")):
                failures.append((query, f"oferta {i} parece URL genérica: {link}"))
    except Exception as exc:
        failures.append((query, repr(exc)))

if failures:
    print("\nFALHAS:")
    for q, reason in failures:
        print(f"- {q}: {reason}")
    sys.exit(1)

print("\nLIVE SMOKE: PASS")
