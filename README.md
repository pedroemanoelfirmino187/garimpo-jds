# JDS Economiza — ir ao ar

App de menor preço (Amazon, Mercado Livre, Shopee) com afiliados:

- Amazon `tag=jdseconomiz0e-20`
- Shopee `sub_id=18381751263`
- Mercado Livre `identity=mape592520`

## 1. No seu PC

```text
pip install -r requirements.txt
python garimpo_jds.py
```

Testes do motor:

```text
python garimpo_jds.py --testar
```

## 2. API no Railway (GitHub)

Repo: https://github.com/pedroemanoelfirmino187/garimpo-jds

1. No Railway: **New → GitHub Repo** → `garimpo-jds`.
2. Start command (já no `railway.toml` / `Procfile`):  
   `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
3. Generate Domain no serviço.
4. Teste: `https://SEU-DOMINIO.up.railway.app/health`  
   Busca: `https://SEU-DOMINIO.up.railway.app/garimpar?q=controle%20ps5`

Se o deploy falhar, no serviço Railway confira o Start Command (não use `python garimpo_jds.py` — isso abre o Flet, não a API).

## 3. App apontando para a API

No Railway (Variables) ou no `.env` local:

```text
JDS_API_URL=https://SEU-DOMINIO.up.railway.app
```

Aí o Flet só pede o produto; o servidor garimpa.

## 4. Site Flet no ar (opcional)

Segundo serviço no Railway, mesmo repo:

- Start: `JDS_WEB=1 python garimpo_jds.py`
- Variável `JDS_API_URL` = URL do serviço da API
- Variável `JDS_WEB` = `1`

## 5. Para ficar estável 24h

Cadastre as APIs oficiais e cole as chaves no Railway (nunca no código):

| Loja | Onde | Variáveis |
|------|------|-----------|
| Amazon | Associates + Product Advertising API | `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY` |
| Shopee | Affiliate | `SHOPEE_APP_ID`, `SHOPEE_SECRET` |
| Mercado Livre | developers.mercadolivre.com | já usa a search pública MLB |

Sem essas chaves o servidor ainda busca, mas Amazon/Shopee podem bloquear. Com as chaves, o próximo passo é ligar PA-API e Shopee Affiliate no motor.
