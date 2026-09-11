# Recovery manual de um init incompleto

[English](RECOVERY.md)

## 0. O `omama init` reconcilia sozinho o estado inequívoco

Antes de planejar qualquer coisa, o `omama init` reconcilia automaticamente uma
instalação interrompida quando — e somente quando — todas as entradas do
journal forem inequívocas.

Primeiro ele exige que **nenhum lock esteja presente**. O lock canônico do
repositório fica no diretório comum do Git
(`<git-common-dir>/omama-install.lock`) e é compartilhado por todos os
worktrees vinculados do mesmo repositório. Um lock que já existe **nunca** é
tomado automaticamente — qualquer que seja seu schema, seu dono registrado ou
quão antigo ele pareça. Se o processo que o criou ainda está em execução não é
algo que esta instalação consiga estabelecer com segurança: só o PID não é
identidade, porque PIDs são reaproveitados, e só a idade também não é, porque
uma instalação lenta não é uma instalação morta.

Portanto a instalação não decide isso. **Você** decide, em um único passo,
idêntico em todas as plataformas:

1. Confirme que nenhum processo `omama` está em execução para este repositório.
2. Renomeie o lock, preservando-o como evidência:

   ```text
   mv <git-common-dir>/omama-install.lock <git-common-dir>/omama-install.lock.stale-<timestamp UTC>
   ```

3. Rode `omama init` de novo.

O `omama init` e a reconciliação automática descrita abaixo recusam enquanto
houver qualquer lock presente, e ambos imprimem exatamente esse remédio com o
caminho concreto preenchido. Um lock escrito por uma versão anterior
(`schema: 1`, registrando apenas um PID) recebe o mesmo tratamento, assim como
um lock sem journal ao lado — nesse caso não há nada a reconciliar, e a
renomeação é tudo o que é necessário.

Em seguida ele classifica cada entrada do journal, **inclusive as que ainda
estão marcadas como `applied: false`**, comparando com os bytes efetivamente
presentes em disco:

- **before** — a before-image registrada. A operação não chegou a ter efeito.
- **after** — a after-image registrada. A operação teve efeito, mesmo que o
  journal ainda não tivesse registrado isso. Esta é a verdadeira janela de
  interrupção pós-substituição: a substituição pode se tornar durável antes da
  atualização do journal, de modo que uma reexecução baseada apenas em
  `applied` pularia silenciosamente um arquivo já publicado.
- **neither** — possivelmente uma edição externa feita depois da falha.

A classificação termina para todas as entradas antes de qualquer alteração. Se
alguma entrada for **neither**, o init não altera absolutamente nada, preserva
o journal e todos os bytes, e para com `recovery-ambiguous`, nomeando os
caminhos e seus hashes registrados. Uma entrada ambígua nunca custa a
evidência mantida pelas entradas inequívocas.

**O que a reconciliação faz — e o que ela não faz.** O caminho automático
reverte as entradas classificadas como **after** para suas before-images
registradas. Ele **não** conclui a instalação interrompida. O repositório volta
ao estado anterior à instalação, e a execução de init que fez a recuperação
instala tudo desde o começo; as linhas `RECOVERED:` dizem isso. O journal
reconciliado também não é descartado — ele é renomeado para
`.omama/install-journal.json.reconciled-<owner>` e mantido como registro do que
foi classificado, no mesmo padrão que este procedimento manual exige de você.

Use o procedimento manual abaixo somente quando o init parar com
`recovery-ambiguous`, parar com `recovery-owner-uncertain`, ou informar
`unfinished-install` ou `recovery-required` indicando
`.omama/install-journal.json`. Esta é uma reconciliação finita dos caminhos
registrados nesse journal, não uma permissão para apagar indiscriminadamente
`.omama`, seu runtime, o lock ou o journal.

## 1. Estabeleça quiescência e retenha as evidências

Interrompa novas operações de `omama init`, Git e Claude neste worktree **e em
todos os worktrees vinculados do mesmo repositório**, pois eles compartilham um
único lock canônico. Confirme que o processo de init que informou a falha
terminou. Se algum lock ainda existir — o canônico
`<git-common-dir>/omama-install.lock` ou o legado `.omama/install.lock` — não o
remova nem o roube: identifique o `owner`/`pid` registrado, confirme se
exatamente esse processo ainda está em execução e pare para pedir ajuda ao
mantenedor se a propriedade for incerta.

Antes de alterar o alvo, copie estes itens para um diretório protegido de
evidências fora do repositório e registre os hashes SHA-256 dos originais e das
cópias:

- `.omama/install-journal.json`, byte por byte;
- cada caminho atual indicado por `operations`, `owned_trees` e
  `config_operations` no journal, inclusive caminhos alterados externamente;
- o índice e a configuração Git, além de todos os arquivos presentes
  `CARD.yaml`, `CARD.close`, `CARD.review.md` e recibos.

Não adicione nem faça commit do diretório de evidências. Mantenha a cópia do
journal depois que o repositório estiver saudável; ela contém before-images e
dados de propriedade necessários para explicar a tentativa que falhou.

## 2. Inspecione o journal real e os hashes atuais

O journal aceito tem `schema: 1`, `owner` não vazio, um status registrado na
fronteira que a tentativa alcançou (`planned`, `publishing`, `published`,
`runtime-reserved`, `runtime-published`, `activation-planned`, `activated`,
`writing-state`, `state-written` ou `recovery-required`) e três listas finitas:
`operations`, `owned_trees` e `config_operations`. Um status diferente de
`recovery-required` significa que a tentativa morreu antes de conseguir
registrar a própria falha; trate cada entrada pelos bytes, não pela flag
`applied`. Pare e peça ajuda ao mantenedor se o schema for diferente, um
caminho listado estiver fora do worktree, o dono do lock não for resolvido ou
uma entrada tiver formato desconhecido. Em particular, nunca siga
o caminho de configuração Git externo de um journal antigo: o init atual
recusa esse layout não suportado antes da publicação.

Para cada operação de arquivo aplicada, primeiro compare tipo/hash/tamanho/modo
atuais com o snapshot `before` registrado e depois compare seu SHA-256 com o
`after_sha256`; retenha `before.kind`, `before.sha256`,
`before.mode` e `before.bytes_b64`. Para cada operação de configuração, faça a
mesma comparação no caminho exato registrado. Para cada árvore própria,
confirme que os caminhos exatos `relative` e `staging_relative` ficam dentro do
worktree, que o dono e o marcador coincidem e que o digest completo da árvore
coincide com `tree_sha256`. O campo `error` indica entradas que o rollback já
considerou divergentes; verifique-as em vez de supor que a lista está completa.

Esta inspeção imprime somente hashes e nomes de caminho; não imprima conteúdo
de before-images nem tokens nos logs:

```python
# Salve fora do repositório como inspect_omama_recovery.py e execute:
# "<PYTHON_CONFIAVEL>" -B inspect_omama_recovery.py "<REPOSITORIO_ALVO>"
import hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
journal_path = root / ".omama" / "install-journal.json"
raw = journal_path.read_bytes()
doc = json.loads(raw.decode("utf-8"))
if doc.get("schema") != 1 or doc.get("status") != "recovery-required" or not doc.get("owner"):
    raise SystemExit("PARE: schema/status/owner de journal não suportado")

def contained(path):
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit("PARE: caminho fora do worktree: " + str(resolved))
    return resolved

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

print("journal_sha256", hashlib.sha256(raw).hexdigest())
print("owner", doc["owner"], "error", doc.get("error"))
for record in doc.get("operations", []):
    path = contained(root / record["relative"])
    print("file", record["relative"], "applied", bool(record.get("applied")),
          "current", file_hash(path), "installer_after", record.get("after_sha256"),
          "before_kind", record.get("before", {}).get("kind"),
          "before_sha256", record.get("before", {}).get("sha256"))
for record in doc.get("owned_trees", []):
    contained(root / record["relative"])
    contained(root / record["staging_relative"])
    print("tree", record["relative"], "staging", record["staging_relative"],
          "owner", record.get("owner"), "published", bool(record.get("published")),
          "marker_sha256", record.get("marker_sha256"),
          "tree_sha256", record.get("tree_sha256"))
for record in doc.get("config_operations", []):
    path = contained(Path(record["path"]))
    print("config", path, "applied", bool(record.get("applied")),
          "current", file_hash(path), "installer_after", record.get("after_sha256"),
          "before_kind", record.get("before", {}).get("kind"),
          "before_sha256", record.get("before", {}).get("sha256"))
```

A linha de árvore mostra o digest registrado de propósito: recalcule o digest
completo de caminho relativo, tipo, modo e conteúdo com a implementação da
mesma versão instalada ou peça ajuda ao mantenedor antes de remover uma árvore;
só o marcador não basta.

## 3. Reconcilie somente o estado próprio registrado

Trabalhe entrada por entrada no journal retido, na ordem inversa de publicação,
e atualize suas notas de evidência após cada decisão:

1. Se uma entrada aplicada já coincidir com todo o snapshot `before` registrado
   (inclusive before ausente e estado atual ausente), o rollback já a restaurou.
   Registre o resultado e não faça alteração.
2. Se o hash atual de arquivo/configuração aplicada for igual a
   `after_sha256`, ele ainda é exatamente a saída da tentativa que falhou.
   Restaure somente essa entrada para sua before-image: remova só esse caminho
   quando `before.kind` for `missing`, ou decodifique `before.bytes_b64`,
   substitua atomicamente só esse arquivo e restaure `before.mode` quando
   `before.kind` for `file`.
3. Se o estado atual não coincidir nem com todo o snapshot `before` nem com
   `after_sha256`, trate-o
   como edição externa. Não o sobrescreva nem apague. Preserve os bytes em
   separado e decida explicitamente se são material compatível pertencente ao
   time (por exemplo, um `privacy-deny.json` editado intencionalmente) ou se
   devem ser integrados/restaurados manualmente antes que o init possa aceitá-los.
   Um conflito imutável ou gerado não pode ser reclassificado como editável.
4. Uma árvore própria/de staging registrada que estiver ausente já foi removida.
   Remova uma que ainda exista somente quando o caminho
   contido, o dono registrado, o marcador de propriedade e todo o
   `tree_sha256` coincidirem. Se algo divergir, preserve a árvore inteira e
   reconcilie seu conteúdo externo; nunca use `rm -rf .omama`,
   `Remove-Item .omama -Recurse` ou remoção incondicional do runtime.
5. Restaure a before-image de configuração registrada somente quando seu
   caminho estiver dentro do worktree e o arquivo atual ainda coincidir com
   `after_sha256`. Se divergir, preserve-o e reconcilie `core.hooksPath`
   manualmente. Nunca escreva em um banco Git externo por este procedimento.

Não remova o journal ativo enquanto cada entrada aplicada não estiver
restaurada à sua before-image ou deliberadamente mantida como estado
compatível de propriedade da equipe, cada entrada de árvore/config não estiver
contabilizada e os hashes protegidos de CARD/índice/evidência ainda
coincidirem.

Um lock retido não é um beco sem saída, e resolvê-lo é decisão sua, não do
instalador. Quando o acima valer:

- Se algum processo `omama` ainda estiver em execução para este repositório,
  **pare**. Nada aqui é seguro enquanto um instalador vivo for dono do
  repositório.
- Caso contrário, renomeie o lock em vez de apagá-lo, e registre o hash dele
  junto com as demais evidências:

  ```text
  mv <git-common-dir>/omama-install.lock <git-common-dir>/omama-install.lock.stale-<timestamp UTC>
  ```

  Este é o mesmo passo único descrito na seção 0, e vale igualmente para um
  lock legado `schema: 1` que registra apenas um PID. Renomeá-lo é um ato
  humano deliberado que diz "eu verifiquei"; o instalador nunca infere isso a
  partir de um PID, de um hostname ou de um timestamp.

Depois remova somente `.omama/install-journal.json`; mantenha a cópia
protegida. Não remova outro estado de `.omama` como atalho.

## 4. Repita a admissão uma vez

Repita a mesma rota de init suportada e a seleção de bundle usadas originalmente:

```text
omama init "<REPOSITORIO_ALVO>" [--python "<MESMO_PYTHON_QUALIFICADO>"]
omama doctor "<REPOSITORIO_ALVO>"
```

O sucesso exige o doctor dinâmico completo e a admissão instalada de
S1/S3/privacidade do init, seguidos por `DOCTOR-OK` independente. Verifique de
novo os hashes salvos de CARD, índice, configuração, edição externa e
evidências. Se a repetição informar conflito ou criar outro journal
`recovery-required`, pare; preserve as duas gerações de evidência e use a
violação nomeada para reconciliação assistida pelo mantenedor.
