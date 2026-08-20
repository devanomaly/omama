# Omama

[![verify](https://github.com/devanomaly/omama/actions/workflows/verify.yml/badge.svg)](https://github.com/devanomaly/omama/actions/workflows/verify.yml)

*Omama, na cosmologia Yanomami, é o demiurgo que deu forma e regra ao mundo — o nome certo para
um toolkit cujo trabalho é dar forma e regra ao comportamento de agentes.*

**Regra sem enforcement é desejo.**

Omama é um pequeno conjunto de guardrails deterministas para trabalhar com agentes de código:
hooks, validadores e scripts com exit code — não prosa de CLAUDE.md que um agente consegue
racionalizar sob pressão. Cada peça carrega uma fixture que prova que ela falha no vermelho antes
de passar no verde, e cada README documenta suas próprias lacunas conhecidas em vez de escondê-las.

**Nenhuma alegação de eficácia é feita aqui.** O que está provado é a mecânica (fixtures
red-green, um processo externo de revisão adversarial que convergiu sobre o que medir) e nada
além disso. Onde o README de uma peça cita um placar de votação (ex.: "4/5", "5/5"), essa é a
contagem de um painel de cinco membros convocado naquela revisão — o processo como um todo nem
sempre teve cinco membros, mas todo placar citado nos docs deste repositório vem de uma fase de
cinco membros dele. Um piloto interno é o próximo passo antes de qualquer alegação de "isso
funciona" — veja [Honestidade, por design](#honestidade-por-design) abaixo.

*Este repositório é um seed extraído de um histórico de trabalho privado; o registro de processo —
a revisão adversarial que matou a maior parte do que foi construído, e o porquê de cada corte —
vive lá, não aqui. O commit inicial é a extração, não o trabalho.*

*[Read in English](README.md)*

Esta página de entrada é mantida em PT-BR; os READMEs de cada peça individual estão em inglês.

## O seed loop (card → recibo → artefato estruturado)

Uma tarefa entra, roda e fecha assim:

1. **[work-order](work-order/README.md)** — a tarefa entra como **card slim**: goal, non-goals,
   tier ratificado pelo humano (S1|S2|S3), done-when observável, UM comando `verify` não-vacuoso,
   repro anexada se bugfix. Validador de schema fechado, preflight.
2. **[receipt-gate](receipt-gate/README.md)** — um Stop hook que, no close DECLARADO, re-roda o
   `verify` do card contra a árvore corrente, hasheia antes/depois e escreve o recibo — **só o
   gate emite o VERIFIED de conclusão de tarefa**. Fechar honestamente como FAILED/UNVERIFIED é
   sempre possível e sempre deixa recibo. Cards S3 exigem review-artefato aprovado antes do
   VERIFIED.
3. **[output-discipline](output-discipline/README.md)** — planos/reviews com estrutura
   obrigatória (verdict primeiro, tier, done-when/verify, non-findings) e **orçamentos de linha
   só advisory** — a estrutura é obrigatória; os orçamentos só sinalizam.

**Passivas de baixo atrito (habilitadas junto, fora da superfície medida por tarefa):**
[privacy-hook](privacy-hook/README.md) (pre-commit de segredos) e
[protect-tests](protect-tests/README.md) (PreToolUse contra apagar/desativar/skipar teste — a
única cobertura mecânica de enfraquecimento de teste até o receipt gate cobrir isso).

**Substrato e starter (ativos, não medidos):**
[validator](validator/README.md) — biblioteca, não peça de governança: o esqueleto de validador
tri-estado do qual output-discipline e o receipt gate herdam o contrato de exit.
[starter-claude-md](starter-claude-md/README.md) — starter de `CLAUDE.md` + checker de
coerência (regra sem tag, heading renomeado, bypass de vocabulário).

**On-demand ([skills/](skills/README.md), fora da superfície medida por tarefa):**
belief-check, triad-check e concurrency-map — invocáveis numa sessão neste repo via os
ponteiros de `.claude/skills/`.

### Numeração das peças (legenda [NN])

O starter template e seu checker ([starter-claude-md](starter-claude-md/README.md)) rastreiam
toda regra de volta a uma peça via tag `[NN]`. Eis o que cada número mapeia neste repo:

| NN | Peça |
|---|---|
| 01 | [privacy-hook](privacy-hook/README.md) |
| 02 | [work-order](work-order/README.md) |
| 03 | [validator](validator/README.md) |
| 04 | [protect-tests](protect-tests/README.md) |
| 05 | *avaliação de ferramenta de terceiro; cortada antes da adoção, não incluída* |
| 06 | *avaliação de ferramenta de terceiro; cortada antes da adoção, não incluída* |
| 07 | convenções de código, opcional — não incluída neste toolkit |
| 08 | [starter-claude-md](starter-claude-md/README.md) |
| 09 | [output-discipline](output-discipline/README.md) |

## Pré-requisitos

Python 3 no PATH — `python3` no macOS/Linux, `py -3` no Windows. Todos os comandos deste repo
estão escritos com `python3`; troque por `py -3` se estiver no Windows. O código em si independe
do launcher (invoca via `sys.executable`), mas é **desenvolvido e exercitado no dia a dia em
Windows** — POSIX é suportado por construção e coberto por CI, não por uso diário.

**work-order** e **receipt-gate** precisam de PyYAML (`pip install pyyaml`); **receipt-gate**
precisa de `git`; **protect-tests** precisa de Node.js. validator, starter-claude-md e
output-discipline rodam só com Python 3.

## Princípios (por que essas peças)

Regra sem enforcement é desejo — cada peça é um hook, um validador ou um script com exit code,
não prosa. Evidência antes de confiança — toda peça carrega fixture com vermelho plantado; a
prova de um guard é vê-lo falhar pelo motivo certo antes de vê-lo passar. Toda peça governa seu
próprio residual — cada README carrega "o que NÃO pega", com a rota nomeada que resolveria.

### Honestidade, por design

O gate trava a alegação, não a sessão. Estados honestos (WIP, FAILED) são exit 0 com rastro —
baratos. Uma alegação VERIFIED desonesta é cara — exige derrotar hash binding e tripwires, e as
rotas conhecidas de forja residual estão documentadas e fixadas em fixture, não escondidas.

## Como adotar

Cada peça é opt-in por repositório; nada aqui se instala sozinho. Adote o LOOP, não peças
avulsas: work-order na raiz do repo, o gate no `.claude/settings.json` DO repo (por-repo, nunca
global — self-test vermelho E verde obrigatório, ver
[receipt-gate/adapt/README.md](receipt-gate/adapt/README.md)), os templates de output-discipline
para plano/review. As passivas (privacy-hook, protect-tests) entram junto (pre-commit e
PreToolUse). **Código de terceiros:** protect-tests vendoriza um script MIT
(`vendor/PROVENANCE.md` tem o registro completo).

## Verificação e empacotamento

```
python3 verify_all.py        # toda fixture ativa (privacy-hook leva minutos — corpus git real)
python3 verify_all.py --fast # pula o corpus da privacy-hook (vira NOT-RUN; exit 2)
```

Tri-estado de ponta a ponta: `OK` / `FAILED` / `NOT-RUN` por entrada; exit 0 só quando tudo
rodou e passou.

## Licença

MIT (`LICENSE` na raiz — código e documentação). Exceção de proveniência:
`protect-tests/vendor/` mantém a licença upstream — ver [NOTICE.md](NOTICE.md).
