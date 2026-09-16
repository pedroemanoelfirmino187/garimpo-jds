"""Pacote da API. Start: uvicorn api.main:app  ou  uvicorn api:app

Rotas BR/US usam Serper + mensagem_servidor / preco_formatado do garimpo_jds.
"""
from api.main import app

__all__ = ["app"]
