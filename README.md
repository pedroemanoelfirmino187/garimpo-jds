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

## 2. API no Render (buscas no servidor)

1. Crie um repositório Git com esta pasta e envie ao GitHub.
2. No [Render](https://render.com): **New → Web Service** → conecte o repo.
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
5. Plano **Starter** (o gratuito dorme e a busca parece quebrada).
6. Teste no navegador: `https://SEU-SERVICO.onrender.com/health`  
   Busca: `https://SEU-SERVICO.onrender.com/garimpar?q=controle%20ps5`

## 3. App apontando para a API

No Render (Environment) ou no arquivo `.env` local:

```text
JDS_API_URL=https://SEU-SERVICO.onrender.com
```

Aí o Flet só pede o produto; o servidor garimpa.

## 4. Site Flet no ar (opcional)

Segundo Web Service no Render, mesmo repo:

- Start: `JDS_WEB=1 python garimpo_jds.py`
- Variável `JDS_API_URL` = URL do serviço da API
- Variável `JDS_WEB` = `1`

## 5. Para ficar estável 24h

Cadastre as APIs oficiais e cole as chaves no Render (nunca no código):

| Loja | Onde | Variáveis |
|------|------|-----------|
| Amazon | Associates + Product Advertising API | `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY` |
| Shopee | Affiliate | `SHOPEE_APP_ID`, `SHOPEE_SECRET` |
| Mercado Livre | developers.mercadolivre.com | já usa a search pública MLB |

Sem essas chaves o servidor ainda busca, mas Amazon/Shopee podem bloquear. Com as chaves, o próximo passo é ligar PA-API e Shopee Affiliate no motor.
