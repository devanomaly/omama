# Superfície de empacotamento da CLI Omama

[English](README.md)

> Este arquivo é o par em português brasileiro de `cli/README.md`. As duas
> versões descrevem o mesmo comportamento; quando o código muda, as duas mudam
> juntas. Redigido para revisão humana — não é tradução automática.

O pacote expõe `omama init [CAMINHO] [--python CAMINHO_ABSOLUTO] [--no-git-config]`
e `omama doctor [CAMINHO] [--static-only]`, além de ajuda e versão. O instalador
resolve apenas worktrees Git não-bare, recusa roteamento Git herdado e destinos
inseguros antes da publicação, e oferece mecânica finita de lock, journal e
rollback condicional.

Um `init` normalmente ativado segue esta ordem: publica o payload; roda **em
privado** todas as verificações de inventário do doctor que não dependem de
ativação e a admissão completa, específica do adotante, a partir dos bytes
instalados; e só então define `core.hooksPath=.githooks` local e roda o doctor
completo, ciente da ativação. Ele retorna 0 apenas depois que essa verificação
final passa — ou seja, uma instalação que falha nunca deixa hooks ativos no
repositório enquanto o próprio estado dela ainda está incompleto. Caso
contrário, informa uma falha nomeada e faz rollback condicional, inclusive da
ativação.

Os códigos de saída são exatos: `0` significa que todas as verificações
selecionadas exigidas rodaram e passaram; `1` significa uma falha observada e
nomeada; `2` significa cobertura deliberadamente incompleta ou NOT-RUN. Nenhuma
linguagem de sucesso acompanha `1` ou `2`. A preparação deliberada com
`--no-git-config` continua sendo a rota distinta de incompleto/2 enquanto a
ativação ainda for necessária: ela publica a instalação preparada, imprime o
comando exato de ativação e não ativa nada.

## Bundle e identidade

As builds geram o payload empacotado a partir dos arquivos autoritativos do
repositório listados em `build_backend/inventory.py`. `omama_cli.bundle.load_bundle()`
lê somente recursos instalados do pacote e verifica cada SHA-256 registrado
antes de expor qualquer byte; um manifesto malformado produz um `BundleError`
nomeado, nunca um erro de acesso a chave. O manifesto distingue arquivos
imutáveis vendorizados, material editável de bootstrap, wiring gerado e estado
local posterior. `omama_cli.identity` fornece classificações conservadoras
somente de leitura e não realiza escritas do instalador.

## Publicação, lock e recuperação

A publicação usa **um** lock canônico do repositório, no diretório comum do Git,
compartilhado por todos os worktrees vinculados, sem roubo de lock obsoleto. Ela
registra cada before-image finita antes da primeira escrita, verifica cada
escrita durável relendo-a antes de registrá-la como aplicada, usa substituições
individuais no mesmo diretório e restaura condicionalmente apenas bytes ainda
escritos por aquela tentativa. Uma edição intercorrente é preservada e deixa um
journal `recovery-required` nomeado.

O `omama init` reconcilia sozinho uma instalação interrompida quando todas as
entradas do journal são inequívocas. Primeiro ele estabelece um único dono: um
lock cujo dono ainda possa estar em execução, ou cuja identidade não possa ser
estabelecida, nunca é tomado — só o PID não é identidade, porque PIDs são
reaproveitados, e só a idade também não é, porque uma instalação lenta não é uma
instalação morta. Depois classifica cada entrada, **inclusive as ainda marcadas
como `applied: false`**, comparando com os bytes em disco: `before` (não
aplicada), `after` (aplicada, mesmo que o journal ainda não tivesse registrado)
ou `neither`. Se qualquer entrada for `neither`, ele não altera absolutamente
nada, preserva o journal e todos os bytes, e para com `recovery-ambiguous`. Para
esse caso, siga o [procedimento manual de recovery](RECOVERY.pt-BR.md), que
prioriza preservação; nunca apague `.omama`, seu runtime, o lock ou o journal
indiscriminadamente.

O re-init recusa outro bundle registrado, repara material imutável ausente do
mesmo bundle e preserva arquivos editáveis de bootstrap já adotados (inclusive
quando foram deliberadamente apagados). Closes ativos, estado local rastreado,
drift de arquivos imutáveis ou gerados, caminhos somente leitura, escapes de
caminho e travessia de symlink/junction são falhas de preflight nomeadas. A
fronteira operacional continua sendo um alvo quiescente: um processo escritor
não cooperativo ainda pode vencer a corrida final entre verificação e
substituição, então isto não é uma garantia de atomicidade sobre todos os
arquivos nem um serviço genérico de transações.

## Contrato de runtime

Python 3.8+ é o contrato de runtime nas duas rotas. A rota gerenciada instala e
exige `PyYAML>=6.0.2,<7`; a rota somente leitura `--python` é qualificada pela
capacidade que o gate instalado realmente precisa, e não por esse piso de
versão. O backend usado apenas na build é restrito a `setuptools>=68,<76`.

O runtime de recibo padrão é `.omama/runtime`, criado a partir de um Python de
sistema existente e sondado de forma independente. A descoberta e o
provisionamento com `uv` no momento da instalação desabilitam explicitamente
downloads de Python gerenciado e descoberta de config/projeto, apontam para o
interpretador selecionado, usam modo de cópia e mantêm cache e temporários sob
`.omama/cache`. Todo controle `UV_*` e `PIP_*` herdado, e todo controle inseguro
de Python, é removido do ambiente em que o uv roda, de modo que quem chama não
consiga acrescentar distribuições não aprovadas nem redirecionar a seleção de
Python. `--no-seed` **não** é creditado como enforcement: ele é inerte nas
versões de uv exercitadas. Quem carrega a garantia é o ambiente higienizado, e
quem a prova é o inventário pós-provisionamento: o runtime próprio precisa
conter a distribuição PyYAML selecionada e nada além dela. A CLI Omama é
rejeitada dentro do runtime de recibo. As linhas `error:` acionáveis do uv são
preservadas nos diagnósticos, em vez de qualquer linha que por acaso tenha sido
impressa por último.

Um runtime gerenciado próprio **ausente** é reprovisionado, de modo que o
remédio do doctor ("rode init de novo neste clone/worktree") realmente funciona.
Um runtime gerenciado presente mas não pertencente ao omama, ou cujo marcador de
posse divergiu, é nomeado e recusado, sem ser apagado nem sobrescrito. A base
efetiva, o interpretador, a versão do Python, a versão do PyYAML resolvida e o
caminho de onde a dependência foi de fato importada ficam registrados no estado
local.

`--python CAMINHO_ABSOLUTO` é uma rota separada e somente leitura. Exige Python
>=3.8,<4 e um PyYAML que realmente satisfaça o gate instalado — qualificado
executando o ciclo `safe_load`/`safe_dump` do qual o gate depende e registrando
qual arquivo de módulo foi importado — em vez do piso universal `>=6.0.2,<7`,
que nunca foi justificado para essa rota. Dependência ausente ou incapaz falha
fechado. A sondagem usa `-B`/`PYTHONDONTWRITEBYTECODE`, roda a partir de um
diretório de trabalho neutro com apenas a entrada insegura do diretório atual
removida do caminho de busca, e nunca chama uv contra o ambiente fornecido. O
HOME real e a seleção de user-site desse interpretador são deliberadamente
preservados: reescrevê-los qualificaria uma dependência diferente daquela que o
gate vai importar. Um `--python` vazio é um valor inválido nomeado, não um
desvio silencioso para a rota gerenciada.

O isolamento de Git é limitado a subprocessos Git e a repositórios de rascunho
pertencentes à fixture, via opções `git -c` por comando. Ele não reescreve HOME
para execução de Python, gate, validador ou checker, e não enfraquece a recusa
de roteamento Git herdado — inclusive a do próprio gate instalado.

## Admissão, doctor e verificação

A fixture de artefatos construídos instala a CLI empacotada em um ambiente de
ferramenta pertencente ao teste, fora do checkout de entrega. Ela admite `init` e
`doctor` públicos reais a partir desses recursos instalados, retém os logs
completos dos filhos e trata um pré-requisito ausente como NOT-RUN, nunca como
sucesso. Um skip obrigatório em unittest é falha da fixture.

O comando completo é `python verify_all.py` sem `--fast`, executado com o
interpretador que o operador escolher; ele usa esse mesmo interpretador para as
fixtures filhas. A incapacidade específica de plataforma é reportada como
NOT-RUN e reprova o job; nunca é substituída por uma alegação estática de
portabilidade.

`--static-only` não executa nenhum interpretador, gate, validador, checker,
scanner ou wrapper instalado. Mantém inspeção de existência, hash e
configuração, nomeia cada linha dinâmica pulada e retorna incompleto/2, a menos
que uma violação conhecida faça o 1 dominar. Cobertura estática nunca se
apresenta como aprovação dinâmica completa.

## Distribuição e proveniência

A entrega piloto da fase 1 é **somente wheel**. O backend de build produz uma
wheel instalável e recusa construir uma distribuição de fonte; nenhuma
equivalência wheel↔sdist é alegada, e se um release público exigirá uma
distribuição de fonte é uma decisão separada e posterior.

A proveniência de build nomeia esta árvore de fontes ou não nomeia nada: uma
revisão só é registrada quando o topo do Git é a raiz de fontes do Omama. Assim,
uma cópia que apenas esteja dentro de um repositório não relacionado reporta a
revisão como indisponível e não limpa, em vez de tomar emprestado o commit
daquele repositório. A geração do payload primeiro descarta a staging obsoleta
do setuptools deste próprio projeto, e builds sobrepostas de um mesmo checkout
são serializadas por um lock de build, de modo que cada uma produza o mesmo
inventário e a mesma identidade de payload.
