# Omama

[![verify](https://github.com/devanomaly/omama/actions/workflows/verify.yml/badge.svg)](https://github.com/devanomaly/omama/actions/workflows/verify.yml)

*Omama, na cosmologia Yanomami, é o demiurgo que deu forma e regra ao mundo — o nome certo para
um toolkit cujo trabalho é dar forma e regra ao comportamento de agentes.*

**Caminho mais rápido: [QUICKSTART.pt-BR.md](QUICKSTART.pt-BR.md)** — construa e
instale o wheel local, inicialize um repositório sintético ou adotante, inspecione-o com
doctor e então despache.

**Regra sem enforcement é desejo.**

Omama é um pequeno conjunto de guardrails deterministas para trabalhar com agentes de código:
hooks, validadores e scripts com exit code — não prosa de CLAUDE.md que um agente consegue
racionalizar sob pressão. Cada peça carrega uma fixture que prova que ela falha no vermelho antes
de passar no verde, e cada README documenta suas próprias lacunas conhecidas em vez de escondê-las.

**O menor harness suficiente.** A aposta do Omama é que o melhor harness é o menor que ainda
segura: o caminho comum por task é um card slim (uma dúzia de linhas de YAML), UM comando
`verify` e um recibo escrito no fechamento — nada além. Rigor é comprado por tier, não pago por
default: só cards S3 exigem artefato de revisão antes do VERIFIED. A verificação é a prova
suficiente mais barata para aquele risco, nunca um ritual fixo. Essa forma é subtrativa por
construção — uma revisão adversarial matou a maior parte do que foi originalmente construído, e
as peças cortadas ([05, 06, 07](#numeração-das-peças-legenda-nn)) estão nomeadas, não
escondidas. Se uma peça daqui custar mais atenção do que a falha que ela previne, isso é um bug
do Omama — abra uma issue.

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
   possível e deixa recibo após as checagens de roteamento e identidade do repositório. Cards S3 exigem review-artefato aprovado antes do
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
belief-check, triad-check e concurrency-map. Os arquivos canônicos ficam em `skills/`; este repo
não os conecta às suas próprias sessões (`.claude/` não é versionado aqui, exceto `settings.json`).

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
| 10 | [receipt-gate](receipt-gate/README.md) |

## Pré-requisitos

A CLI suporta Python 3.8 ou mais recente (abaixo do Python 4) e requer Git. Construa/instale
a partir deste checkout com `uv`; este documento não declara um pacote público disponível.
O `init` padrão também precisa do `uv` durante a instalação e de um Python-base existente,
descoberto de forma independente. Downloads de Python gerenciado são desativados: o comando
não baixa Python, não altera uma instalação Python de usuário/global e não grava configuração
Claude ou Git de usuário/global.

O `init` padrão cria `.omama/runtime` no alvo e instala ali apenas o PyYAML restrito.
`--python <CAMINHO_ABSOLUTO>` qualifica, em vez disso, um ambiente Python/PyYAML existente
somente para leitura. O hook de privacidade tem contrato separado: seu wrapper inalterado
seleciona `py -3`, `python3` e depois `python` pelo PATH. O interpretador do recibo não
configura nem substitui esse interpretador de privacidade.

As peças avulsas mantêm seus pré-requisitos documentados. Em particular, **work-order** e
**receipt-gate** precisam de PyYAML, e **protect-tests** precisa de Node.js.

## Princípios (por que essas peças)

Regra sem enforcement é desejo — cada peça é um hook, um validador ou um script com exit code,
não prosa. Evidência antes de confiança — toda peça carrega fixture com vermelho plantado; a
prova de um guard é vê-lo falhar pelo motivo certo antes de vê-lo passar. Toda peça governa seu
próprio residual — cada README carrega "o que NÃO pega", com a rota nomeada que resolveria.

### Honestidade, por design

O gate trava a alegação, não a sessão. Após as checagens de roteamento e identidade do
repositório, estados honestos (WIP, FAILED) são exit 0 com rastro —
baratos. Uma alegação VERIFIED desonesta é cara — exige derrotar hash binding e tripwires, e as
rotas conhecidas de forja residual estão documentadas e fixadas em fixture, não escondidas.

A barreira de roteamento herdado inclui `GIT_CONFIG_GLOBAL` e
`GIT_CONFIG_SYSTEM`; a checagem de wiring identifica a recusa como falha do
ambiente, sem dizer que o gate está ausente. Diretórios sem Git montados dentro
de um checkout mantêm NO-CARD, WIP e closes honestos nesse limite de filesystem.

## Como adotar

Use o fluxo de wheel local no [Quickstart](QUICKSTART.pt-BR.md) para o bundle da fase 1:
gate de recibo, validator, checker S3, scanner de privacidade e os dois pontos de entrada Git,
templates, política de exemplo, runtime/fiação local, proveniência e estado. A inicialização é
por repositório. Ela mescla sua entrada de Stop no `.claude/settings.local.json` ignorado,
preserva settings não relacionados e nunca cria `CLAUDE.md` nem muda configuração de usuário/global.

A adoção manual peça a peça continua disponível. Siga o `ADOPTION.md` de cada peça e o
[guia de vendoring](VENDORING.md): copie bytes sem alterações, registre fonte/SHA/arquivos
upstream e exclua manualmente as cópias dos formatters e linters. A CLI deliberadamente não
reescreve configuração de formatter. **Código de terceiros:** protect-tests inclui um script
MIT (`vendor/PROVENANCE.md` tem o registro completo); o próprio protect-tests fica fora do
bundle da CLI de fase 1.

Reexecutar o mesmo bundle repara arquivos imutáveis ausentes que sejam elegíveis e preserva
material editável adotado, inclusive a remoção deliberada de templates inertes. Ele recusa
drift imutável e outro bundle; não é um comando implícito de update. Política de deny da equipe,
tokens, estado de card/recibo/índice, settings não relacionados e hooks customizados não são
sobrescritos. Se ativar `.githooks` deslocaria qualquer hook ativo do diretório efetivo,
inclusive um `pre-push` solitário, o init recusa e pede integração manual.

## Verificação e empacotamento

```
python3 verify_all.py # Windows: py -3 verify_all.py
```

O comando de verificação da entrega é o runner completo, sem `--fast`. Tri-estado ponta a ponta:
`OK` / `FAILED` / `NOT-RUN` por entrada; exit 0 somente quando toda fixture obrigatória,
inclusive a integração contada da CLI a partir do artefato construído, rodou e passou. A matriz
medida de plataforma/build e os limites restantes estão resumidos no Quickstart; admissão
sintética pelo shell não prova que um host Claude real carregou os settings do projeto.

Na revisão congelada da fonte da CLI `efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, esse
runner informou `9 ok, 0 failed, 0 not-run` em Ubuntu/Python 3.8, Ubuntu/Python 3.11,
macOS/Python 3.11 e Windows/Python 3.11. Sua entrada contada da CLI contém seis suites e
74 testes nessa revisão, inclusive nove testes de runtime; a CI expõe o resumo pai de nove
entradas, não um hash de artefato ou log distinto para cada suite filha.

## Licença

MIT (`LICENSE` na raiz — código e documentação). Exceção de proveniência:
`protect-tests/vendor/` mantém a licença upstream — ver [NOTICE.md](NOTICE.md).
