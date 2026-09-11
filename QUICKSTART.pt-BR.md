# Quickstart — instale e inspecione o bundle da fase 1

Esta página usa um wheel construído a partir do checkout. Ela não declara que existe um
pacote público do Omama. Comece com um worktree Git limpo, não-bare, que já tenha pelo menos
um commit. Nunca experimente no checkout-fonte do Omama; use primeiro um repositório descartável.

*[English version](QUICKSTART.md)*

## 1. Construa e instale o wheel local

Pré-requisitos: Git, `uv` e um Python 3.8+ (abaixo do Python 4) existente e escolhido pelo
usuário. Os placeholders de caminho abaixo são intencionais; troque-os pelos caminhos da sua máquina.

Os comandos abaixo ficam intencionalmente um por linha: as mesmas aspas funcionam em shell
POSIX e PowerShell, sem sintaxe de continuação de um shell usada no outro.

```text
cd "<CHECKOUT_FONTE_OMAMA>"
uv build --wheel --sdist --no-python-downloads --python "<CAMINHO_ABSOLUTO_DO_PYTHON_EXISTENTE>" --out-dir "dist"
uv tool install "dist/omama-0.1.0-py3-none-any.whl" --python "<CAMINHO_ABSOLUTO_DO_PYTHON_EXISTENTE>" --no-managed-python --no-python-downloads --no-config
```

Se o uv informar que seu diretório de executáveis não está no `PATH`, siga o comando
temporário de shell que ele imprime antes de continuar:

```text
omama --version
omama --help
```

Esses são comandos de artefato local, não `uvx` nem instalação a partir de um índice. Instalar
a CLI não inicializa o checkout-fonte e não autoriza publicação do pacote.

## 2. Inicialize um repositório

A rota padrão cria um runtime durável do gate de recibo dentro do alvo:

```text
omama init "<REPOSITORIO_ALVO>"
omama doctor "<REPOSITORIO_ALVO>"
```

O `init` padrão encontra de forma independente um Python-base suportado já instalado, cria
`<REPOSITORIO_ALVO>/.omama/runtime` e usa o `uv`, somente durante a instalação, para instalar
ali apenas `PyYAML>=6.0.2,<7`. Downloads de Python gerenciado e descoberta de configuração
global são desativados. O init nunca baixa Python, instala a CLI nesse runtime nem muda
configuração Python, Claude ou Git de usuário/global.

Se a equipe já possui um ambiente Python/PyYAML durável, selecione-o explicitamente:

```text
omama init "<REPOSITORIO_ALVO>" --python "<CAMINHO_ABSOLUTO_DO_PYTHON_QUALIFICADO>"
```

Esse interpretador precisa informar Python 3.8+ (abaixo do 4) e importar o PyYAML restrito.
O Omama o inspeciona com gravação de bytecode desativada e não instala nem modifica esse
ambiente. O interpretador registrado para recibos é separado do wrapper de privacidade, que
mantém a seleção upstream pelo PATH (`py -3`, depois `python3`, depois `python`). Doctor
qualifica ambos.

Um init bem-sucedido instala o payload completo de 15 arquivos e registra URL/revisão da
fonte, versão do pacote, licença, identidade do bundle e hashes por arquivo. Ele também:

- mescla um registro de Stop de sua propriedade no `.claude/settings.local.json` ignorado,
  com caminho absoluto do interpretador entre aspas, usando barras normais, e
  `"$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"`;
- instala gate de recibo, wiring checker, validator de work order, checker S3, scanner de
  privacidade, wrapper de privacidade inalterado e os dois chainers Git;
- inicializa política de deny editável pela equipe, tokens condicionais só com comentário,
  work-order e templates inertes de starter/PLAN/REVIEW, preservando conteúdo existente;
- acrescenta caminhos locais/de evidência ao `.gitignore` apenas quando o Git confirma que
  o ignore resultante é efetivo; e
- roda **primeiro, em privado**, todas as verificações de inventário do doctor que não
  dependem de ativação e a admissão obrigatória completa a partir dos bytes instalados;
  em seguida ativa `core.hooksPath=.githooks` local; e só então roda o doctor completo,
  ciente da ativação, antes de registrar o estado completo. Uma instalação que falha nunca
  deixa hooks ativos.

O init imprime instruções para adotar o starter e o bloco por operador de output-discipline;
não cria `CLAUDE.md` nem grava esse bloco em configuração de usuário.

## 3. Ativação deliberada da configuração Git

Para preparar os arquivos sem alterar a configuração Git local:

```text
omama init "<REPOSITORIO_ALVO>" --no-git-config
```

Quando a ativação é necessária, esse resultado é intencionalmente incompleto (exit 2). O
Omama imprime um comando exato com esta forma:

```text
git -C "<REPOSITORIO_ALVO>" config --local core.hooksPath .githooks
```

Rode exatamente o comando impresso e repita o mesmo `omama init ... --no-git-config`.
Quando `.githooks` já for efetivo, a repetição faz a admissão completa e pode sair com 0.

Para um linked worktree cuja configuração compartilhada ainda não está correta, o init se
recusa a alterá-la. Primeiro rode a correção exata que ele imprime contra o **checkout principal**:

```text
git -C "<CHECKOUT_PRINCIPAL>" config --local core.hooksPath .githooks
omama init "<LINKED_WORKTREE>"
```

O Omama nunca habilita a extensão worktree-config do Git nem altera silenciosamente config
compartilhada. Se `git init --separate-git-dir` colocou a configuração de ativação deste worktree fora do
worktree, o init recusa antes da publicação; a fase 1 não ativa esse layout.
Se um hooksPath customizado estiver efetivo, ou existir qualquer hook ativo no
diretório que seria deslocado — mesmo apenas `pre-push` — o init recusa. Integre os hooks
manualmente; deslocamento do diretório inteiro não se torna seguro só porque os novos arquivos coexistem.

## 4. Leia corretamente os exits e as repetições

Ambos os comandos são tri-estado:

| Exit | `init` | `doctor` |
|---|---|---|
| 0 | Toda checagem dinâmica e admissão de hook obrigatória passou; estado completo. | Toda linha dinâmica obrigatória rodou e passou. |
| 1 | Violação nomeada, conflito, alvo inseguro, falha de runtime ou admissão obrigatória falhou/não pôde ser avaliada. Estado de rollback/recovery é explícito. | Ao menos uma violação nomeada; ela domina linhas incompletas. |
| 2 | Estado preparado deliberado ou outra capacidade obrigatória não foi avaliada; nunca sucesso. | Nenhuma violação conhecida, mas cobertura obrigatória incompleta, inclusive `--static-only`. |

Repetições do mesmo bundle reparam somente material imutável/gerado ausente que seja elegível.
Arquivos bootstrap editáveis pertencem à equipe depois de criados; edições e remoção deliberada
de templates inertes sobrevivem. Drift imutável, conflito na fiação gerada e outro bundle são
conflitos nomeados, não update implícito. Estado de card/close/recibo/índice, tokens, política
de deny, settings/hooks não relacionados e edições externas são protegidos.

As gravações usam um lock no alvo, journal finito das gravações próprias, substituição por
arquivo e rollback condicional. Se outro escritor muda um caminho depois que o Omama o gravou,
o Omama preserva a edição externa e deixa estado nomeado de recovery necessário, em vez de
restaurar bytes obsoletos. Isso é recovery limitado ao conjunto documentado de arquivos sob
um alvo quiescente, não atomicidade de todos os arquivos, roubo de lock antigo ou serviço geral
de transações.

Se o init deixar `recovery-required` ou informar `unfinished-install`, não apague
indiscriminadamente `.omama`, seu runtime, lock ou journal. Siga o
[procedimento finito de recovery manual](cli/RECOVERY.pt-BR.md), que prioriza a preservação,
retenha as before-images e edições externas e repita somente depois de contabilizar cada
entrada própria registrada.

## 5. O que doctor realmente verifica

O doctor padrão é somente leitura quanto a arquivos do alvo, família do card, índice e config,
mas executa apenas os artefatos instalados esperados depois de conferir sua identidade. Ele relata:

- estado da instalação, propriedade de lock/journal, manifesto/proveniência, skew de bundle/versão,
  hashes imutáveis/gerados e drift de material editável da equipe;
- ambos os arquivos de settings do projeto, o único comando Stop gerenciado elegível,
  registros desativados/async ou conflitantes, quoting certificado e overrides visíveis do
  ambiente de projeto/processo;
- interpretador/PyYAML do recibo, resposta do gate, probes válido/inválido do validator e
  probes válido/malformado do checker S3, inclusive `--budgets-advisory`;
- hooksPath efetivo, ambos os chainers, identidade/modo de execução do wrapper/scanner,
  configuração de privacidade, interpretador selecionado pelo wrapper e estado dos tokens; e
- diferenças de clone/worktree/relocação e runtime/settings locais ausentes.

Doctor não imprime valores de token. Um arquivo de tokens configurado e ausente é violação com
caminho e correção. Um arquivo configurado existente, vazio ou só com comentários, produz um
aviso não bloqueante por execução do scanner: a camada literal está inativa; preencha-a ou use
null explicitamente. `tokens_file: null` e chave omitida desativam deliberadamente a camada sem
esse aviso. Arquivo preenchido prova apenas que há literais, não que a lista da equipe é completa.

`omama doctor "<REPOSITORIO_ALVO>" --static-only` não executa interpretador, gate, validator,
checker, scanner nem wrapper instalados. Ainda confere caminhos, formas, bytes, settings e
estado, nomeia cada linha dinâmica pulada e normalmente retorna incompleto/2. Use-o quando
executar settings controlados pelo repositório for impróprio; não o chame de prova de saúde.

Doctor observa `settings.json` e `settings.local.json` do projeto e seu ambiente de processo.
Settings de usuário, política gerenciada e uma fonte separada via `claude --settings` não são
totalmente observáveis. Portanto, doctor dinâmico certifica o comando modelado, não o merge
exato de settings que uma sessão Claude real carregará.

## 6. Admissão obrigatória

Antes de o init informar sucesso, ele roda o doctor dinâmico completo sob o proprietário privado
da transação e testa os comandos instalados no alvo em repositórios Git sintéticos. Ele prova:

- S1 chega a `VERIFY-RED`/2 real e depois `VERIFIED`/0, consumindo o close e permitindo
  recomputar o vínculo de commit/diff;
- S3 chega ao checker instalado com review PASS presente sem Non-findings, bloqueia como
  `S3-REVIEW`/2 e então fecha um review válido; somente excesso de orçamento é advisory;
- ambos os pontos de entrada de privacidade bloqueiam literal sintético plantado e permitem
  commit/merge limpo;
- estados de tokens configurado-ausente, vazio/só comentários, preenchido, null e omitido
  mantêm comportamentos distintos;
- remover gate, validator, checker, scanner ou wrapper instalados no scratch falha pelo nome,
  mesmo havendo cópias saudáveis no pacote/fonte em outro lugar; e
- todos os arquivos efetivamente instalados são commitados juntos pelo wrapper entregue e
  pela política corrente. Instalação nova admite o payload completo de 15 arquivos em um commit.

Somente `CLAUDE_PROJECT_DIR` muda para esses worktrees scratch; não há overrides de dependência
`OMAMA_*` gerados nem fallback para a árvore-fonte. São usados payloads sintéticos, nunca os bytes
dos tokens do adotante.

## 7. Rode uma tarefa real e inspecione seu recibo

A admissão do init usou cards e literais sintéticos para provar os mecanismos instalados.
Ela não criou nem fechou sua primeira tarefa real. A partir da raiz do repositório inicializado:

1. Copie `work-order.template.yaml` para `CARD.yaml`. Em shell POSIX, use
   `cp "work-order.template.yaml" "CARD.yaml"`; no PowerShell, use
   `Copy-Item -LiteralPath "work-order.template.yaml" -Destination "CARD.yaml"`.
2. Preencha goal, non-goals, done-when, tipo da tarefa e um `verify` real, relevante e
   não-vácuo. O agente pode propor o tier, mas um humano o ratifica e é responsável por
   confirmar `verify`; em bugfix, o humano também fornece ou confirma `repro`. Não invente
   comando ou reprodução só para preencher o schema.
3. Um humano roda o validator antes do despacho, usando o interpretador absoluto de recibo
   exato que o init gravou primeiro em `.claude/settings.local.json`.

   Shell POSIX:

   ```sh
   "<PYTHON_ABSOLUTO_DE_RECIBO_DOS_SETTINGS_LOCAL>" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
   ```

   PowerShell (onde um executável entre aspas precisa do operador de chamada):

   ```powershell
   & "<PYTHON_ABSOLUTO_DE_RECIBO_DOS_SETTINGS_LOCAL>" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
   ```

   Despache somente depois de ele informar `OK`.
4. Adote no `CLAUDE.md` do repositório a regra de close de
   `docs/templates/omama/CLAUDE.starter.md`, seguindo a
   [adoção do starter](starter-claude-md/ADOPTION.md), ou carregue a regra explicitamente
   neste despacho:

   ```text
   Implemente o CARD.yaml da raiz do repositório. Quando o trabalho ratificado terminar, escreva CLOSE em CARD.close e pare.
   ```

O Stop hook trata a ausência de `CARD.close` como WIP. Num close deliberado ele reexecuta a
prova do próprio card; um close vermelho é bloqueado e precisa ser corrigido antes de outro
close deliberado. Depois de um close permitido, confirme que `CARD.close` foi consumido e
inspecione `CARD.receipt.json` (`cat "CARD.receipt.json"` em shell POSIX ou
`Get-Content -LiteralPath "CARD.receipt.json"` no PowerShell). Não crie nem edite o recibo
manualmente. Veja [adoção do work-order](work-order/ADOPTION.md) para a ratificação humana e
[o modelo de close do receipt](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session)
para todos os valores de close e a semântica do recibo.

## 8. Cobertura e o que não pega

A checagem de entrega do repositório é o comando completo, sem `--fast`:

```sh
python3 verify_all.py # Windows: py -3 verify_all.py
```

Exit 0 exige que toda fixture contada — inclusive integração da CLI com wheel construído — rode
e passe. As fixtures avulsas de validator, recibo, privacidade e artefato precedem esta CLI; sua
cobertura isolada não prova que a integração install/init/doctor passou.

Para a fonte congelada da CLI em `efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, o runner
completo passou nas quatro pernas da matriz: Ubuntu/Python 3.8, Ubuntu/Python 3.11,
macOS/Python 3.11 e Windows/Python 3.11, cada uma com nove entradas de topo e
`9 ok, 0 failed, 0 not-run`. A entrada contada da CLI contém seis suites e 74 testes nessa
revisão (inclusive nove testes de runtime); o resumo pai da CI informa a entrada, não um
log ou hash separado para cada suite filha.

| Alegação | Limite da evidência |
|---|---|
| Identidade de bundle/build e admissão S1/S3/privacidade instalada | Medida em artefatos locais construídos, dentro de repositórios descartáveis. |
| Matriz suportada de plataforma e Python | O runner completo da revisão exata passou em Ubuntu 3.8/3.11, macOS 3.11 e Windows 3.11; isso não amplia o suporte além dos jobs nomeados. |
| Carregamento de settings pelo Claude | Admissão determinista pelo shell não prova que um host Claude real carregou os settings do projeto. É exigida sessão separada no host. |
| Segurança de crash/concorrência | Rollback condicional finito não é atomicidade do repo inteiro/de todos os arquivos; escritores hostis e queda de energia ficam fora da promessa. |
| Eficácia de detecção | Nenhuma alegação de eficácia ou redução antes da evidência do piloto. |

Remover ou mover o Python-base selecionado, o repositório ou `.omama/runtime` pode quebrar a
execução futura do recibo; doctor detecta essas falhas de ciclo de vida, mas não torna o
interpretador permanente. Config Git local e estado de máquina ignorado não acompanham um clone.
O hook de privacidade também mantém os bypasses documentados (`--no-verify`, cherry-pick/am/rebase,
histórico e segredos genéricos de alta entropia); veja [privacy-hook/README.md](privacy-hook/README.md).

Para instalação manual, proveniência e exclusões de formatter/linter, use
[VENDORING.md](VENDORING.md) e o `ADOPTION.md` de cada peça. Configuração de formatter nunca é
reescrita automaticamente.
