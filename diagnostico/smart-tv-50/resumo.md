# Diagnóstico: smart tv 50

Consulta real na branch `cursor/busca-segura-7dfb`, commit `4d58fd7`, sem cache.

A API respondeu HTTP 200 com **0 ofertas**. A SearchApi não estava vazia: achou anúncios e descartou todos antes de confirmar.

## Resultado

| Campo | Valor |
| --- | --- |
| Consulta | `smart tv 50` |
| HTTP da API | 200 |
| Total de ofertas | 0 |
| Status SearchApi | `SEARCHAPI_EMPTY` |
| Fallback Serper | sim |

## Funil da SearchApi

| Etapa | Quantidade |
| --- | --- |
| shopping_requests | 1 |
| shopping_results | 40 |
| candidates | 17 |
| candidatos com product_token | 17 |
| candidatos com product_id | 15 |
| po_fila_candidatos | 2 |
| product_offers_requests | 3 |
| offers_received | 9 |
| offers_rejected | 5 |
| apos_parser | 4 |
| apos_matcher | 1 |
| confirmer_entrada | 1 |
| offers_confirmed | 0 |
| product_page_skipped | 1 |

Orçamento: 4 de 5 chamadas. Sem timeout. `budget_atingido=false`.

Motivos registrados:

```text
loja_fora: 4
matcher_rejeitou: 1
html_vazio: 1
confirmer_rejeitou: 1
```

O Mercado Livre entra duas vezes no mesmo anúncio: `html_vazio` e `confirmer_rejeitou`.

## O que quebrou a consulta

1. A oferta Amazon `Smart TV 50" Roku Multi 4K Compatível com Alexa e Google Home - TL059M` (ASIN `B0DBM7323B`, R$ 2.299,90) passou em título e relevância, mas `_jds_anuncio_bate_consulta` devolveu falso.
2. A palavra **compatível** em "Compatível com Alexa e Google Home" era lida como anúncio genérico (`nao_original`). O descarte saiu como `matcher_rejeitou`.
3. Das 4 ofertas que passaram do parser, o matcher manteve 1: o anúncio do Mercado Livre `MLBU3365756008`.
4. A página desse anúncio veio sem HTML. O confirmer registrou `html_vazio` e devolveu `None`.
5. Sem oferta confirmada, o motor caiu no Serper. O Serper devolveu 40 cards e extraiu 0 (`apos_extrair=0`).

Por isso `smart tv 50` terminou vazio mesmo com 40 resultados de shopping e 9 ofertas recebidas.

## O que não explica o vazio

O agrupamento por loja em `_jds_confirmar_listings` não descarta os outros candidatos da mesma loja quando o primeiro falha. A loja some só se todos os anúncios dela falharem. Esse fluxo não é a causa deste caso.

KaBuM, Magalu e Gazin saíram como `loja_fora`. Isso é a allowlist (Amazon, Mercado Livre e Shopee), não o bug da TV.

## O que o teste trava agora

`tests/test_smart_tv_50_regressao.py` repete o caso:

- o título Amazon com "Compatível com Alexa e Google Home" tem que bater com `smart tv 50`;
- "Compatível com PS5" continua genérico;
- TV 32 polegadas não passa como 50;
- no pipeline, com o Mercado Livre sem HTML, a Amazon `B0DBM7323B` a R$ 2.299,90 tem que sair confirmada.

## O que a execução real não registrou

Não há payload bruto da SearchApi nem do Serper. Também não há motivo item a item para:

- os 23 cards de shopping que não viraram candidato;
- as 3 ofertas de Product Offers que não entraram na amostra;
- os 40 cards do Serper, todos descartados na extração sem motivo individual.
