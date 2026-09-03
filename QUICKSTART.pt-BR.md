# Quickstart — o loop mínimo, do clone ao primeiro recibo

Todo comando abaixo foi executado num repositório de teste antes deste
documento ser commitado (em Windows, com as substituições de interpretador
anotadas inline); o caminho mecânico — sem contar leitura — levou pouco mais
de 6 minutos na máquina do autor. Os comandos estão escritos com `python3` —
no Windows troque por `py -3` (ver [Pré-requisitos](README.pt-BR.md#pré-requisitos)).

*[English version](QUICKSTART.md)*

## 1. Veja-o se recusar a exagerar (2 comandos, sem compromisso)

Instale as dependências PRIMEIRO — sem PyYAML as fixtures reportam `FAILED`,
que se lê como "repo quebrado" quando significa "dependência faltando" (as
linhas de detalhe até dizem `pyyaml not installed`, mas só se você ler além
do sumário):

```
pip install pyyaml
python3 verify_all.py --fast
echo $?
```

Esperado: `7 ok, 0 failed, 1 not-run` — e **exit code 2, não 0**. Sete passes
mais um check pulado não é um pass; um verificador que reporta sucesso sobre
cobertura que pulou está mentindo. Esse exit code é a postura inteira deste
toolkit num único bit observável. (`python3 verify_all.py` sem `--fast` roda
também o corpus pulado — leva minutos — e sai com 0.)

## 2. O loop mínimo são três peças

- **[work-order](work-order/README.md)** — a tarefa entra como card: goal,
  non-goals, tier ratificado por humano, done-when observável, UM comando
  `verify` que pode falhar. Sem ele o gate não tem a que te prender.
- **[receipt-gate](receipt-gate/README.md)** — um Stop hook que re-roda o
  `verify` do próprio card antes de um close poder alegar VERIFIED, e escreve
  um recibo em qualquer caso. Sem ele o card é prosa.
- **[output-discipline](output-discipline/README.md)** — estrutura para
  planos/reviews (verdict primeiro, non-findings explícitos). Necessária desde
  o dia um apenas para cards S3; adote os templates quando chegar lá.

Todo o resto do repo é opcional e separável — ver
[Como adotar](README.pt-BR.md#como-adotar).

## 3. Instale no seu repositório

Da raiz do seu repo (`<OMAMA>` = seu clone deste repo):

```
mkdir -p .claude/hooks tools
cp <OMAMA>/receipt-gate/receipt_gate.py   .claude/hooks/
cp <OMAMA>/work-order/validate_work_order.py  tools/
cp <OMAMA>/work-order/work-order.template.yaml .
```

Registre o hook: copie o bloco `hooks` de
[receipt-gate/adapt/settings.example.json](receipt-gate/adapt/settings.example.json)
para o `.claude/settings.json` **do seu repositório**. Três regras, cada uma
prevenindo um gate que *parece* instalado enquanto está silenciosamente
ausente ou bloqueando para sempre:

- **Por-repo, NUNCA `~/.claude/settings.json`** — um gate global quebrado
  bloqueia todos os seus repos; um por-repo quebrado bloqueia só o repo que
  optou por ele.
- **Caminho absoluto do interpretador no comando, não `python3`** — se o
  launcher não existe no host, o shell sai com 127/9009, o que NÃO bloqueia:
  o gate fica silenciosamente ausente para sempre.
- **Exporte as env vars ANTES do self-test** — `OMAMA_CARD` (caminho do card
  ativo) e `OMAMA_VALIDATOR` (caminho do seu `validate_work_order.py`
  copiado). Sem elas todo close bloqueia com `SCHEMA: validator unrunnable`.
  `OMAMA_CHECK_ARTIFACT` só é exigida quando você usar cards S3. Tabela
  completa: [receipt-gate/adapt/README.md](receipt-gate/adapt/README.md).

O gate precisa de um repo git com pelo menos um commit (HEAD não-nascido
falha-fechado, por design).

## 4. Prove o gate: wiring check, depois vermelho, depois verde (obrigatório — não pule)

Uma instalação que você não viu bloquear não está instalada. Esta seção é o
self-test que o [adapt/README.md](receipt-gate/adapt/README.md) torna
obrigatório — primeiro o wiring check (a verificação mecânica da fiação),
depois rode o gate pela string de comando EXATA registrada no seu
`settings.json`, copiada e colada, não redigitada.

**Passo 1 — wiring check.** Da raiz do seu repo:

```
python3 <OMAMA>/receipt-gate/adapt/check_wiring.py    # Windows: py -3 ...
```

**Esperado: `WIRING-OK ...` e exit 0.** Ele resolve o comando de Stop hook
registrado e faz uma execução de teste (dry run) com stdin vazio —
interpretador ausente, só o nome do launcher em vez do caminho absoluto,
argumento `receipt_gate.py` errado ou ausente, um `CLAUDE_PROJECT_DIR` que
o shell do hook deixaria literal (grafia `%VAR%`, aspas simples), um hook
numa forma que o check não certifica (`async`, `args` em forma exec,
`shell: powershell`), qualquer outra expansão `$` no comando, ou
`disableAllHooks` num arquivo de settings vira uma `VIOLATION` nomeada
(exit 1) em vez da ausência silenciosa 127/9009; no Windows sem Git Bash a
resposta é NOT-RUN (exit 2), porque o hook rodaria pelo PowerShell. (Ele
EXECUTA o comando registrado — esse é o ponto; detalhes, a forma
certificada, uso em CI e `--static-only` no
[adapt/README.md](receipt-gate/adapt/README.md).)

**Passos 2–3 — vermelho, depois verde.** Adicione o snippet do gitignore primeiro — um card é por tarefa e por
máquina, não algo para versionar (veja
[work-order/ADOPTION.md](work-order/ADOPTION.md#the-card-and-its-receipt-stay-local)
para o porquê):

```
cat >> .gitignore <<'EOF'
CARD.yaml
CARD.close
CARD.receipt.json
*.receipt.json
EOF
git add .gitignore
git commit -m "gitignore: card e receipt ficam locais"
```

Escreva um primeiro card, `CARD.yaml`, cujo `verify` **ainda** não passa —
p.ex. para um repo onde `app.js` ainda diz `hi`:

```yaml
goal: app.js greets with "hello" instead of "hi"
non_goals:
  - any file other than app.js
tier: S1
task_type: implementation
done_when:
  - app.js source contains the string hello
verify: python3 -c "exit(0 if 'hello' in open('app.js').read() else 1)"
```

(Escreva o `verify` no que roda na SUA máquina — no Windows, `python`.)

```
python3 tools/validate_work_order.py CARD.yaml   # esperado: OK ... valid card
echo "CLOSE" > CARD.close
echo '{}' | <string de comando exata do seu settings.json>
```

Nada para commitar ainda — `CARD.yaml` e `CARD.close` estão no gitignore, e
`app.js` ainda não mudou.

**Esperado: `RECEIPT-GATE BLOCK[VERIFY-RED]` e exit 2.** Esse block é o
produto funcionando. (O `{}` no stdin faz as vezes do payload de Stop-hook
que o Claude Code envia; stdin vazio é ele próprio um block nomeado, por
design.)

Agora faça o trabalho e feche de novo:

```
# ...faça app.js imprimir hello...
git add -A && git commit -m "greet with hello"
echo "CLOSE" > CARD.close
echo '{}' | <string de comando exata do seu settings.json>
```

**Esperado: exit 0, `VERIFIED ... receipt written`, e `CARD.receipt.json` em
disco** com comando de verify, exit code e hashes da árvore amarrados juntos.
`CARD.close` sumiu — o gate o consome em todo close permitido; o recibo é o
registro durável. Closes honestos (`FAILED: <razão>`, `UNVERIFIED: <razão>`)
sempre passam e sempre deixam recibo também.

Se você viu o WIRING-OK, o BLOCK vermelho **e** o VERIFIED verde, o loop
está instalado. Um resultado vermelho/verde sem o outro significa fiação
quebrada — ver a seção de self-test do
[adapt/README.md](receipt-gate/adapt/README.md) para o que cada resultado
parcial significa.

## 5. Despacho

O loop está instalado. Despachar uma tarefa por ele é uma linha — o card já
está em disco (`CARD.yaml`, validado, `tier` ratificado), o branch já está
cortado, e o prompt não diz nada que o card e o `CLAUDE.md` do repo já não
digam:

```
Implement the CARD.yaml at this repo root. It is the contract: if it is wrong or incomplete, stop and report it defective — do not redefine it.
```

Essa linha basta **porque as peças carregam o resto**. Toda vez que um
despacho aqui precisou de uma linha extra, a linha extra acabou nomeando
algo que uma peça já governa:

| Linha extra que o despacho precisou | Quem já governa isso | Peça |
|---|---|---|
| "não toque em nada fora deste diretório" | o `non_goals` do card — a lista congelada do que o diff não pode conter | 02 |
| "escreva `CLOSE` em `CARD.close` quando terminar, e pare" | a regra do Stop hook no arquivo starter, em "Hooks installed in this repo" | 08 |
| "corte o branch da ponta do branch padrão e abra um PR contra ele" | a regra de branch no arquivo starter, em "Bugfix requires a work order" | 08 |

**Um prompt de despacho que precisa de uma segunda linha está nomeando uma
peça ausente ou não adotada.** Leia a linha extra como achado, não como
prosa a manter: ou o `non_goals` do card está frouxo demais, ou o
`CLAUDE.md` deste repo está sem a regra (ver
[starter-claude-md](starter-claude-md/README.md), cujo checker rejeita
regra que não rastreia para peça nenhuma). Conserte o artefato, não o
prompt.

**O fechamento, do lado do agente.** Quando o trabalho do card termina, o
agente escreve `CLOSE` em `CARD.close` e para — esse é todo o protocolo que
lhe cabe. O gate faz o resto: re-roda o `verify` do próprio card contra a
árvore atual, escreve `CARD.receipt.json`, e bloqueia um close vermelho
(exit 2, nomeado) em vez de deixá-lo alegar VERIFIED. Parar sem `CARD.close`
é um turno WIP e é permitido. Todo valor que `CARD.close` pode carregar —
inclusive os closes honestos `FAILED:`/`UNVERIFIED:` — está na tabela em
[receipt-gate/README.md](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session);
não é repetido aqui, para haver uma cópia só a manter verdadeira.

## 6. Você agora tem

- Cards que congelam goal/non-goals/verify antes do dispatch, validados por
  `tools/validate_work_order.py`.
- Um gate que re-roda a prova do próprio card antes de qualquer close poder
  alegar VERIFIED, e escreve recibo para todo close, falhas honestas
  incluídas.
- Um recibo de self-test vermelho provando que o gate realmente bloqueia na
  sua máquina.

Próximos passos: semântica de tiers e o que só um humano decide —
[work-order/ADOPTION.md](work-order/ADOPTION.md); review-artefatos S3 —
[output-discipline/ADOPTION.md](output-discipline/ADOPTION.md); o que o gate
NÃO pega — a seção de residuais do
[receipt-gate/README.md](receipt-gate/README.md). Nenhuma alegação de
eficácia é feita para nada disto; ver o [README](README.pt-BR.md).
