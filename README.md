# JDS Economiza — ir ao ar

App de menor preço (Amazon, Mercado Livre, Shopee) com afiliados:

- Amazon Brasil `tag=jdseconomiz0e-20` (`AMAZON_PARTNER_TAG`)
- Amazon EUA `tag=jdseconomiza-20` (`AMAZON_TAG_US`)
- Shopee `sub_id=18381751263`
- Mercado Livre `identity=mape592520`
- eBay EUA (EPN) `campid=5339211741` (`EBAY_EPN_CAMPAIGN_ID`), PDP `/itm/{id}`

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

O app móvel chama:

```text
POST /garimpar
Header: X-JDS-TOKEN: (o mesmo de JDS_API_TOKEN no Railway, se você configurar)
Body: {"q": "smart tv 50"}
```

`POST /shopping` é só o Google via Serper (cache antes da API, Amazon/ML/Shopee). A chave Serper nunca sai do servidor.

## 4. Site Flet no ar (opcional)

Segundo serviço no Railway, mesmo repo:

- Start: `JDS_WEB=1 python garimpo_jds.py`
- Variável `JDS_API_URL` = URL do serviço da API
- Variável `JDS_WEB` = `1`

## 5. Para o robô comparar as 3 lojas de verdade (obrigatório no Railway)

Scraping no servidor é bloqueado. Cole as chaves em **Railway → Variables** (nunca no GitHub):

| Loja | Onde cadastrar | Variáveis |
|------|----------------|-----------|
| Amazon | [Associates](https://associados.amazon.com.br) → Product Advertising API | `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG=jdseconomiz0e-20` |
| Shopee | [Afiliados](https://affiliate.shopee.com.br) → Open API | `SHOPEE_APP_ID`, `SHOPEE_SECRET` |
| Mercado Livre | [developers.mercadolivre.com.br](https://developers.mercadolivre.com.br) | `MELI_ACCESS_TOKEN` |
| eBay EUA | [Partner Network](https://partnernetwork.ebay.com) | `EBAY_EPN_CAMPAIGN_ID=5339211741`, `EBAY_EPN_CUSTOM_ID=5339211530` |
| Google (SearchApi) | [searchapi.io](https://www.searchapi.io) | `SEARCHAPI_API_KEY` |
| Google (Serper, fallback) | [serper.dev](https://serper.dev) | `SERPER_API_KEY` |
| ZenRows (grátis) | [zenrows.com](https://www.zenrows.com) | `ZENROWS_API_KEY` |
| ScrapingAnt (grátis) | [scrapingant.com](https://scrapingant.com) | `SCRAPINGANT_API_KEY` |

No ar o motor pede o Google pela **SearchApi** (Shopping + Product Offers, no máximo 3 ofertas por busca). Sem `SEARCHAPI_API_KEY` cai no fallback **Serper**. A chave nunca vai para o app nem para o GitHub.

Variáveis opcionais no Railway: `SEARCHAPI_MAX_PRODUCT_OFFERS=3`, `SEARCHAPI_CACHE_TTL=900`, `SEARCHAPI_OFFERS_CACHE_TTL=900`.

Depois do deploy, `/health` mostra `searchapi` como `true` quando `SEARCHAPI_API_KEY` está no Railway.

## 6. Suíte de qualidade

A suíte automatizada verifica o matcher, regras de identidade, integridade de
oferta (título/preço/imagem/URL), URLs genéricas, API, autenticação e respostas
vazias.

```text
python -m pytest -q
```

Ou:

```text
python scripts/quality_check.py
```

### Teste real no Railway

Depois de publicar:

```text
JDS_API_URL=https://SEU-DOMINIO.up.railway.app python scripts/live_smoke.py
```

Se houver `JDS_API_TOKEN`, também defina a variável no terminal. O script não
mostra o token e não grava credenciais.

O smoke test real verifica as respostas de:

- controle ps5
- controle ps5 sony
- controle ps5 sony branco
- iphone 15 128gb
- samsung galaxy s24
- jbl tune 520bt
- ps5
- nintendo switch oled

Importante: o teste automatizado não declara que duas ofertas são o mesmo
produto só porque a API respondeu. A confirmação de identidade continua sendo
feita pelo matcher e pelas regras de segurança do projeto.
