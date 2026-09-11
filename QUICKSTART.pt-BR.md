# Quickstart — instale o Omama e feche sua primeira tarefa

*[English version](QUICKSTART.md)*

Esta página tem duas partes. A **Parte 1** é o caminho normal: construir a CLI a partir deste
checkout, inicializar um repositório descartável e fechar uma tarefa real pelo gate de
recibo — inclusive vendo-o recusar um close vermelho. A **Parte 2** é a referência de tudo o
que o caminho normal contorna: ativação deliberada, linked worktrees, conflitos com hooks
existentes, exit codes, o que o `doctor` prova, a admissão do próprio instalador e o limite
da cobertura.

Ela usa um wheel construído a partir do checkout. Não declara que existe um pacote público
do Omama. Nunca experimente no checkout-fonte do Omama; use primeiro o repositório
descartável abaixo.

Dois shells são usados. Os blocos de **shell POSIX** rodam em Linux, macOS e no Git Bash do
Windows (o Git Bash vem com o Git for Windows e é o shell que o próprio Claude Code usa para
hooks no Windows). Os blocos de **PowerShell** aparecem onde a grafia difere. Um passo —
rodar o gate à mão — é só para shell POSIX; o motivo está dito lá.

> **Em que esta página foi testada.** Todos os comandos da Parte 1 foram executados, na ordem
> mostrada, em Windows 11 com Git 2.41, uv 0.9.10, Claude Code 2.1.269 e Python 3.8, 3.10 e
> 3.12 instalados; os blocos POSIX rodaram no Git Bash, os de PowerShell no PowerShell 5.1.
> O despacho do passo 6 foi uma sessão real e autenticada do Claude Code em modo print nessa
> máquina. `init`, `doctor` e o gate também são exercitados em Linux e macOS pela CI do
> repositório, mas os blocos POSIX desta página não foram re-executados separadamente lá.
> Os trechos de saída são reais; campos específicos da máquina foram trocados por
> placeholders `<...>`.

---

## Parte 1 — o caminho normal

### 0. O que você precisa

| Necessidade | Por quê | Como conferir |
|---|---|---|
| Git 2.x, com identidade de commit | Todo passo é um repositório Git; o gate hasheia árvores; o passo a passo faz commits | `git --version`, `git config user.email` imprime algo |
| Um Python 3.8 ou mais recente, abaixo do 4, já instalado | A CLI roda nele; o `init` também encontra sozinho um Python-base instalado | `python3 --version` (POSIX) / `py -0p` (Windows) lista ao menos um |
| `uv` | Constrói e instala o wheel; o `init` o usa uma vez para criar o runtime de recibo por repositório | `uv --version` |
| Acesso ao índice, ou cache do `uv` aquecido | Instalar a CLI e provisionar o runtime resolvem PyYAML | — |
| Claude Code | O passo 6 despacha uma sessão real; todos os outros passos funcionam sem ele | `claude --version` |
| Só Windows: Git for Windows | Fornece o Git Bash, o shell dos hooks; sem ele o Claude Code cai para PowerShell, que a checagem de wiring do gate não certifica | "Git Bash" aparece no menu Iniciar depois de instalar o Git for Windows |

Nada abaixo baixa um Python, edita configuração Python, Claude ou Git de usuário/global, nem
escreve fora do repositório-alvo e do diretório de ferramentas do próprio `uv`.

### 1. Construa e instale a CLI (uma vez por máquina)

`<CHECKOUT_FONTE_OMAMA>` é um clone deste repositório
(`git clone https://github.com/devanomaly/omama.git`). O outro placeholder é intencional;
troque-o por um caminho da sua máquina. Um comando por linha: as mesmas aspas funcionam em
shell POSIX e em PowerShell.

```text
cd "<CHECKOUT_FONTE_OMAMA>"
uv build --wheel --no-python-downloads --python "<CAMINHO_ABSOLUTO_DO_PYTHON_EXISTENTE>" --out-dir "dist"
uv tool install "dist/omama-0.1.0-py3-none-any.whl" --python "<CAMINHO_ABSOLUTO_DO_PYTHON_EXISTENTE>" --no-managed-python --no-python-downloads --no-config
```

`<CAMINHO_ABSOLUTO_DO_PYTHON_EXISTENTE>` é qualquer interpretador Python 3.8+ instalado, por
exemplo o caminho que `py -0p` imprime no Windows ou que `command -v python3` imprime em
POSIX. As flags `--no-managed-python` / `--no-python-downloads` impedem o `uv` de baixar um
Python próprio; `--no-config` faz com que ele ignore qualquer arquivo de configuração do
`uv` na máquina. Se o `uv` informar que seu diretório de executáveis não está no `PATH`,
acrescente esse diretório antes de continuar — no Git Bash, escreva-o como caminho POSIX
(`/c/Users/<voce>/.local/bin`, não a forma `C:/...` que o `uv` imprime, que o Git Bash não
honra) — e então:

```text
omama --version
omama --help
```

Esperado: `omama 0.1.0`, e um texto de ajuda listando exatamente dois comandos, `init` e
`doctor`. Esses são comandos de artefato local, não `uvx` nem instalação a partir de um
índice. Instalar a CLI não inicializa o checkout-fonte e não autoriza publicação do pacote.
A ferramenta é por máquina; cada repositório é inicializado separadamente no passo 3.

### 2. Crie um repositório descartável com uma tarefa real, que falha

A tarefa: `greet("World")` devolve `Hello World`; o teste espera `Hello, World!`. O teste
já existe e já falha, então o comando de prova do card tem em que falhar antes da correção e
em que passar depois dela.

Shell POSIX:

```sh
mkdir omama-first && cd omama-first
git init -q -b main
cat > greet.py <<'EOF'
def greet(name):
    return "Hello " + name
EOF
cat > test_greet.py <<'EOF'
import unittest

from greet import greet


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self):
        self.assertEqual(greet("World"), "Hello, World!")


if __name__ == "__main__":
    unittest.main()
EOF
git add . && git commit -qm "greeter: initial code and its test"
python3 -B -m unittest -q test_greet
```

PowerShell:

```powershell
New-Item -ItemType Directory omama-first | Out-Null; Set-Location omama-first
git init -q -b main
Set-Content -LiteralPath greet.py -Encoding ascii -Value @"
def greet(name):
    return "Hello " + name
"@
Set-Content -LiteralPath test_greet.py -Encoding ascii -Value @"
import unittest

from greet import greet


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self):
        self.assertEqual(greet("World"), "Hello, World!")


if __name__ == "__main__":
    unittest.main()
"@
git add .; git commit -qm "greeter: initial code and its test"
py -3 -B -m unittest -q test_greet
```

A última linha precisa falhar — essa falha é a reprodução que o card anexa no passo 4. (No
Git Bash do Windows, `python3` costuma ser o stub da Microsoft Store, não um Python; rode
essa linha lá como `py -3 -B -m unittest -q test_greet`, como faz o bloco de PowerShell.)

```text
AssertionError: 'Hello World' != 'Hello, World!'
...
FAILED (failures=1)
```

O `init` exige um worktree Git não-bare com pelo menos um commit, o que este agora é.

### 3. Inicialize o repositório e leia o `doctor`

`<REPO>` é o caminho absoluto do diretório que você acabou de criar (`pwd` / `Get-Location`).

```text
omama init "<REPO>"
omama doctor "<REPO>"
```

O `init` levou cerca de trinta segundos na máquina testada, a maior parte na admissão
descrita em [R4](#r4-admissão-obrigatória): antes de informar sucesso ele prova, em cópias
privadas de rascunho, que o gate que acabou de instalar bloqueia um close vermelho e verifica
um verde. A saída termina com:

```text
ADMISSION-OK: every mandatory installed command was evaluated and passed
ACTIVATED: repository-local core.hooksPath=.githooks was set after private admission passed
... (o relatório do doctor ciente da ativação)
DOCTOR-OK: all required dynamic checks evaluated and passed
INSTALLED: doctor and every mandatory installed-command admission check passed
ADOPT STARTER: copy docs/templates/omama/CLAUDE.starter.md to CLAUDE.md, ...
PER-OPERATOR OUTPUT-DISCIPLINE BLOCK (copy deliberately to your global CLAUDE.md; omama did not write global configuration):
> **Output form.** ...
```

Exit 0 é o único sucesso; 1 é falha nomeada com rollback; 2 é deliberadamente incompleto
([R2](#r2-leia-corretamente-os-exits-e-as-repetições)). Duas linhas `WARNING` são normais num
repositório novo: `environment-boundary` (o doctor não enxerga settings de usuário ou
gerenciados do Claude) e `token-state` (o arquivo de tokens literais existe e está vazio —
preencha-o ou desative-o depois, veja [R3](#r3-o-que-doctor-realmente-verifica)).

**O que o `init` escreveu, e onde cada coisa mora:**

| Por repositório — ainda não rastreado, feito para ser commitado e compartilhado | Por máquina — ignorado, recriado pelo `init` em cada clone ou worktree |
|---|---|
| `tools/omama/` — gate de recibo, checker de wiring, validador de card, checker de artefato S3, scanner de privacidade, licença, proveniência, manifesto | `.omama/runtime/` — um venv contendo só PyYAML, criado a partir de um Python-base instalado que o `init` encontrou sozinho (qual: o campo `base_interpreter` de `.omama/state.json`; a linha `interpreter` do doctor informa a versão de Python do runtime) |
| `.githooks/pre-commit`, `.githooks/pre-merge-commit` (chainers), `.githooks/privacy-pre-commit` (o wrapper de privacidade inalterado) | `.omama/state.json` — o que foi instalado, hashes, o interpretador registrado |
| `privacy-deny.json` — política de segredos editável pela equipe | `.claude/settings.local.json` — o registro do Stop hook: o caminho absoluto do interpretador do runtime mais `"$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"` |
| `work-order.template.yaml`, `docs/templates/omama/{CLAUDE.starter,PLAN,REVIEW}.md` — templates inertes | config Git local do repositório `core.hooksPath=.githooks` |
| `.gitignore` — acrescido de um bloco `# Omama local state and evidence` nomeando cada caminho da coluna da direita mais `CARD.yaml`, `CARD.close`, `CARD.review.md`, `CARD.receipt.json`, `*.receipt.json` | `privacy-tokens.txt` — bootstrap só com comentário para a camada de tokens literais |

O `init` imprimiu instruções para adotar `CLAUDE.starter.md`; ele não criou `CLAUDE.md` e
nunca escreve configuração de usuário ou global. Essa adoção é o primeiro item do passo 8.

`omama doctor` relê tudo isso (poucos segundos) e termina com `DOCTOR-OK`. O
doctor dinâmico executa o gate, o validador e o checker instalados com entradas sintéticas
pelo comando registrado exato, então sua linha `settings-execution` certifica que a string de
comando registrada responde como o gate. Ele **não** prova que uma sessão do Claude Code
carrega esse arquivo de settings — o passo 6 é onde isso é exercitado de verdade.

### 4. Escreva o card, depois decida

Copie o template e preencha. POSIX: `cp work-order.template.yaml CARD.yaml`; PowerShell:
`Copy-Item -LiteralPath work-order.template.yaml -Destination CARD.yaml`. Os comentários do
template explicam cada campo; o card preenchido para esta tarefa é:

```yaml
goal: greet("World") returns "Hello, World!" (comma and exclamation mark), as test_greet.py already expects.
non_goals:
  - editing test_greet.py
  - adding any other file or function
tier: S1
task_type: bugfix
done_when:
  - test_greet.py passes
verify: python3 -B -m unittest -q test_greet
repro:
  - "python3 -B -m unittest -q test_greet fails with AssertionError: 'Hello World' != 'Hello, World!'"
```

**No Windows o gate roda o `verify` pelo `cmd.exe`**, não pelo seu shell — escreva o launcher
do jeito que o `cmd.exe` o encontra, normalmente `py -3 -B -m unittest -q test_greet`, tanto
em `verify` quanto em `repro` (foi essa a grafia usada na execução testada). Em qualquer
plataforma, rode você mesmo a linha do `verify` nesse shell antes: ela precisa falhar agora,
pelo motivo que `repro` registra.

**Por que este `verify` e não outro.** É o único comando cujo exit status *é* o done-when:
falha na árvore atual exatamente pelo motivo do goal e só consegue passar quando o goal for
atingido — ou quando o teste for alterado, o que `non_goals` proíbe e nada mecânico impede.
Compare com `verify: echo done` — o validador o rejeita pelo nome, porque um
comando que não consegue falhar não prova nada. Compare também com
`verify: python3 -c "pass"`: o validador o *aceita* (é um comando real), e o gate o fecharia
`VERIFIED`, porque re-rodar um comando que sempre sai com 0 produz um verde genuíno. Nada
mecânico distingue uma prova irrelevante de uma relevante; essa é a leitura humana abaixo, e
é o motivo de o recibo ser evidência sobre o comando, não sobre o goal.

**Valide a forma.** O validador precisa de PyYAML, que o `init` instalou só no runtime de
recibo, então chame esse interpretador — o mesmo caminho absoluto registrado em
`.claude/settings.local.json`, que é `.omama/runtime/bin/python` em POSIX e
`.omama/runtime/Scripts/python.exe` no Windows:

```sh
.omama/runtime/bin/python -B tools/omama/work-order/validate_work_order.py CARD.yaml
```

```powershell
& ".omama/runtime/Scripts/python.exe" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
```

Esperado: `OK: CARD.yaml is a valid card`, exit 0. Para ver a deny-list em ação, troque
`verify` por `echo done` e rode de novo:

```text
VIOLATION: verify='echo done' is vacuous (deny-list: true, :, echo ...): segment 'echo done' begins with 'echo' -- a command that cannot fail proves nothing
```

Remova o bloco `repro` em vez disso e o validador recusa o bugfix sem reprodução. Restaure o
card antes de continuar.

**As decisões humanas, antes do despacho — nada abaixo é conferível por script:**

1. **Ratificar o `tier`.** `S1` aqui: uma linha, um teste, sem artefato de revisão exigido.
   `S3` exigiria também um `CARD.review.md` aprovado antes do `VERIFIED`.
2. **Ratificar o `verify`.** O exit status dele prova o `goal`? Aqui sim, por construção.
3. **Ratificar o `repro`.** É algo que você observou? Você o rodou no passo 2.
4. **Ler os `non_goals`.** O diff é revisável contra essa lista? Aqui o diff pode tocar uma
   função em um arquivo.

Se você não consegue responder sim ao item 2, o `task_type` certo é `ask-first`, não um
comando inventado.

### 5. Veja o gate dizer não (um ensaio, à mão)

Antes de gastar uma sessão de agente, veja como é um close vermelho. Declare o close agora,
com o bug ainda no lugar, e rode o gate instalado exatamente como um evento Stop chegaria a
ele — um objeto JSON no stdin, a partir da raiz do repositório:

```sh
printf 'CLOSE\n' > CARD.close
echo '{}' | .omama/runtime/bin/python tools/omama/receipt-gate/receipt_gate.py
```

No Windows, rode este bloco no **Git Bash** com `.omama/runtime/Scripts/python.exe` como
interpretador. Ele deliberadamente não é dado para PowerShell: na máquina testada o
PowerShell 5.1 prefixou um byte-order mark ao texto do pipe e o gate respondeu
`BLOCK[BAD-INPUT]`, que é o gate recusando entrada que não consegue parsear, não um problema
de wiring.

O gate re-roda o `verify`, o vê falhar e bloqueia (exit 2):

```text
RECEIPT-GATE BLOCK[VERIFY-RED]: verify exited 1 on the current tree.
--- verify output tail ---
======================================================================
FAIL: test_greets_by_name (test_greet.GreetTest.test_greets_by_name)
...
AssertionError: 'Hello World' != 'Hello, World!'
...
FAILED (failures=1)
fix and re-close, or declare an honest FAILED in CARD.close ("FAILED: <reason>")
```

Olhe o diretório: `CARD.close` continua lá e **nenhum** `CARD.receipt.json` foi escrito. Um
close bloqueado não deixa nada que se confunda com evidência. Numa sessão real, esse texto é
o que o Claude Code devolve ao agente, cujas duas opções honestas são as que a última linha
nomeia.

Isso roda o script do gate diretamente, o que basta para ver a resposta dele; não exercita a
fiação do Stop em si (a linha `settings-execution` do doctor fez isso, e o passo 6 faz pelo
host). Agora desfaça o close declarado para que o despacho parta de um estado limpo:
`rm CARD.close` (PowerShell: `Remove-Item CARD.close`).

### 6. Despache o Claude Code

A partir da raiz do repositório, ou abra uma sessão interativa com `claude` e cole esta
instrução, ou rode-a de forma não interativa como o passo a passo testado fez:

```text
claude -p "Implement CARD.yaml at the repository root. When its ratified work is complete, write CLOSE to CARD.close and stop." --allowedTools "Read,Edit,Write,Bash" --max-turns 12
```

`--allowedTools` pré-aprova essas ferramentas para a sessão em modo print — aceitável num
repositório descartável, decisão sua em outro lugar. A instrução carrega a regra de close
explicitamente porque este repositório ainda não tem `CLAUDE.md`; o passo 8 a torna
permanente.

O que acontece, em ordem: o agente lê o card, edita `greet.py`, roda o teste, escreve `CLOSE`
em `CARD.close` e para. O Claude Code dispara o Stop hook de `.claude/settings.local.json`; o
gate encontra o card no diretório de trabalho da sessão, re-roda o `verify`, hasheia a árvore
antes e depois, escreve o recibo e consome `CARD.close`. A sessão testada terminou em menos de
um minuto e imprimiu seu próprio resumo terminando em *CARD.close now contains CLOSE* — **essa
frase é a alegação do agente, não a evidência**. A evidência está em disco:

```text
ls CARD.*            # PowerShell: Get-ChildItem CARD.*
CARD.receipt.json
CARD.yaml
```

`CARD.close` sumiu e existe um recibo. Duas coisas a saber sobre o host:

- O Claude Code mostra a saída do Stop hook na transcrição **só quando o hook bloqueia**. Uma
  liberação não imprime nada; o `CARD.close` consumido e o recibo escrito são o registro
  visível.
- Se o agente fechar vermelho, ele vê o texto de bloqueio do passo 5 e pode corrigir e
  fechar de novo, ou fechar honestamente. O Claude Code limita bloqueios consecutivos do Stop
  hook e então encerra o turno; observado num host real como nove, acompanhado na
  [issue #50](https://github.com/devanomaly/omama/issues/50). O resultado é conservador —
  sem recibo, alegação não verificada — mas o bloqueio é limitado pelo host, não ilimitado.

Sem Claude Code à mão? Corrija você mesmo a linha em `greet.py`, declare `CLOSE` de novo e
rode outra vez o comando do passo 5: ele responde `VERIFIED: verify green and fresh on <rev>
-- receipt written, CARD.close consumed.` e escreve o mesmo recibo. Isso prova o gate, não a
fiação do host.

### 7. Leia o recibo

```text
cat CARD.receipt.json    # PowerShell: Get-Content -LiteralPath CARD.receipt.json
```

A execução testada produziu (hashes abreviados):

```json
{
 "command": "py -3 -B -m unittest -q test_greet",
 "exit": 0,
 "verdict": "VERIFIED",
 "rev": "7e1a581c8a059dec3b4529cdd9fb841bef08b035",
 "patch_id": "7f50aeb4…",
 "diff_sha": "f104accf…",
 "diff_hash": "f6d0de5e…",
 "timestamp": "2026-09-11T23:39:10.745772+00:00"
}
```

| Campo | Significado | Como conferir |
|---|---|---|
| `command`, `exit` | O `verify` do card como estava no close, e o exit status que o gate observou | Rode você mesmo; um recibo `VERIFIED` sempre tem `exit: 0` |
| `verdict` | `VERIFIED` só a partir de uma re-execução verde; `FAILED` / `UNVERIFIED` a partir de um close honesto (aí `reason` está presente) | — |
| `rev` | `HEAD` quando a prova rodou | `git rev-parse HEAD` — igual aqui, porque o agente não commitou |
| `patch_id` | `git patch-id --stable` do diff não commitado contra `HEAD` no close; `empty-diff` numa árvore limpa | `git diff HEAD \| git patch-id --stable` enquanto o diff não mudar |
| `diff_sha` | SHA-256 dos bytes do `git diff HEAD` fixado | Recomputável neste checkout enquanto a árvore existir |
| `diff_hash` | SHA-256 de todo o material hasheado depois do `verify` — diff, nomes não rastreados, reflog, stash, flags do índice, a família do card | O gate o recomputa no próximo close; divergência entre antes e depois é `UNEXPECTED-CHANGE` |
| `timestamp` | UTC | — |

Um recibo `VERIFIED` sempre carrega `rev`, `patch_id` e `diff_sha` não nulos; um com hash nulo
é forjado na cara. Nunca crie nem edite o recibo você mesmo; o gate apaga o recibo que
encontra no início de toda tentativa de close.

Commite a correção agora (`git add greet.py && git commit -m "greet: add comma and
exclamation mark"`) — seu primeiro commit pelo hook de privacidade instalado, que imprime um
`notice` sobre o arquivo de tokens vazio e deixa passar um commit limpo. Depois rode de novo
o comando do passo 5 sem `CARD.close` presente: o gate responde uma linha WIP que termina em
`receipt: VERIFIED @ 7e1a581c… …, tree has moved since`. O recibo continua nomeando a árvore
que ele verificou; a árvore agora é outra. É o vínculo fazendo seu trabalho.

Um close honesto é uma linha: `FAILED: <motivo>` ou `UNVERIFIED: <motivo>` em `CARD.close`.
O gate ainda re-roda o `verify`, registra o exit, escreve um recibo com esse veredito e o
motivo, consome o token e sai com 0 — um rastro, nunca um `VERIFIED`.

**O que este recibo prova:** no commit `7e1a581…` com aquele diff aplicado, o comando
ratificado saiu com 0, naquele momento, sem forja pelo caminho do close. **O que ele não
prova:** que o comando era a prova certa (você ratificou isso no passo 4), que o diff é bom no
resto (leia-o), ou que o teste não poderia ter sido enfraquecido antes (`non_goals` diz para
não fazer isso; o guard opcional [protect-tests](protect-tests/README.md) vigia isso; o recibo
não). A lista de residuais do gate está em
[receipt-gate/README.md](receipt-gate/README.md#what-it-does-not-catch-honest-named-boundaries).

### 8. O que fazer em seguida

1. **Torne a regra de close permanente.** Copie `docs/templates/omama/CLAUDE.starter.md` para
   `CLAUDE.md`, remova o comentário de cabeçalho, resolva cada `<ADJUST: ...>` (remova os hooks
   que este repositório não instalou — protect-tests não está no bundle) e confira a cópia
   com `starter-claude-md/check_starter.py` a partir do checkout do Omama — o checker não faz
   parte do payload instalado. Detalhes: [adoção do starter](starter-claude-md/ADOPTION.md).
   Depois disso, um despacho não precisa mais da instrução explícita de close.
2. **Inicialize um repositório real do mesmo jeito.** O `init` recusa deslocar hooks já
   ativos e nunca reescreve config compartilhada de worktree;
   [R1](#r1-ativação-deliberada-da-configuração-git-worktrees-e-hooks-existentes) cobre esses
   casos e o `--no-git-config`. Depois edite `privacy-deny.json` e preencha ou desative
   `privacy-tokens.txt`.
3. **Cada clone e cada linked worktree roda `omama init` para si.** O runtime, a fiação do
   Stop e o `core.hooksPath` são por máquina e não viajam com um clone; o `doctor` nomeia o
   que falta.
4. **Leve a evidência para a revisão.** Cole `command`, `exit` e `rev` no corpo do PR. O
   arquivo de recibo fica local por política
   ([por quê](work-order/ADOPTION.md#the-card-and-its-receipt-stay-local)).
5. **Leia o que você está e não está recebendo.** O README de cada peça termina com "What it
   does NOT catch"; [R5](#r5-cobertura-e-o-que-não-pega) abaixo é o limite do próprio
   instalador.

---

## Parte 2 — referência

### R1. Ativação deliberada da configuração Git, worktrees e hooks existentes

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

Se a equipe já possui um ambiente Python/PyYAML durável, selecione-o em vez do runtime
gerenciado:

```text
omama init "<REPOSITORIO_ALVO>" --python "<CAMINHO_ABSOLUTO_DO_PYTHON_QUALIFICADO>"
```

Esse interpretador precisa informar Python 3.8+ (abaixo do 4) e importar o PyYAML restrito.
O Omama o inspeciona com gravação de bytecode desativada e não instala nem modifica esse
ambiente. O interpretador registrado para recibos é separado do wrapper de privacidade, que
mantém a seleção upstream pelo PATH (`py -3`, depois `python3`, depois `python`). Doctor
qualifica ambos.

Na rota padrão, o `init` encontra de forma independente um Python-base suportado já
instalado, cria `<REPOSITORIO_ALVO>/.omama/runtime` e usa o `uv`, somente durante a
instalação, para instalar ali apenas `PyYAML>=6.0.2,<7`. Downloads de Python gerenciado e
descoberta de configuração global são desativados. O init nunca baixa Python, instala a CLI
nesse runtime nem muda configuração Python, Claude ou Git de usuário/global.

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

### R2. Leia corretamente os exits e as repetições

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

### R3. O que doctor realmente verifica

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

### R4. Admissão obrigatória

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

A admissão do init usou cards e literais sintéticos para provar os mecanismos instalados.
Ela não criou nem fechou sua primeira tarefa real; a Parte 1 faz isso. Veja
[adoção do work-order](work-order/ADOPTION.md) para a ratificação humana e
[o modelo de close do receipt](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session)
para todos os valores de close e a semântica do recibo.

### R5. Cobertura e o que não pega

A checagem de entrega do repositório é o comando completo, sem `--fast`:

```sh
python3 verify_all.py # Windows: py -3 verify_all.py
```

Exit 0 exige que toda fixture contada — inclusive integração da CLI com wheel construído — rode
e passe. As fixtures avulsas de validator, recibo, privacidade e artefato precedem esta CLI; sua
cobertura isolada não prova que a integração install/init/doctor passou.

*Registro histórico, não contagem atual:* para a fonte congelada da CLI em
`efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, o runner completo passou nas quatro pernas da
matriz: Ubuntu/Python 3.8, Ubuntu/Python 3.11, macOS/Python 3.11 e Windows/Python 3.11, cada
uma com nove entradas de topo e `9 ok, 0 failed, 0 not-run`. A entrada contada da CLI
continha seis suites e 74 testes nessa revisão (inclusive nove testes de runtime); o resumo
pai da CI informa a entrada, não um log ou hash separado para cada suite filha.

| Alegação | Limite da evidência |
|---|---|
| Identidade de bundle/build e admissão S1/S3/privacidade instalada | Medida em artefatos locais construídos, dentro de repositórios descartáveis. |
| Matriz suportada de plataforma e Python | O runner completo da revisão exata passou em Ubuntu 3.8/3.11, macOS 3.11 e Windows 3.11; isso não amplia o suporte além dos jobs nomeados. |
| Carregamento de settings pelo Claude | Admissão determinista pelo shell não prova que um host Claude real carregou os settings do projeto. É exigida sessão separada no host; o passo 6 da Parte 1 é uma dessas sessões, no Windows. |
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
