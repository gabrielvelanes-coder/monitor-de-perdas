# Pendências e histórico — Monitor de Perdas

## RETOMAR DAQUI (fim da sessão 2026-09-25, continuação) — as 6 fontes migradas pro banco

Gabriel pediu pra terminar a migração de vez: "quero todas as
informações sendo buscadas no banco. não quero ficar mais enviando
planilha." + botão "Atualizar agora". **As 6 fontes que antes eram
arquivo manual agora vêm do banco do ERP**, cada uma com fallback
automático pro arquivo se o banco cair (nunca quebra o app):

| Fonte | Tabela(s) do ERP | Constante liga/desliga |
|---|---|---|
| Perdas | `baixaestoque`+`itembaixaestoque`+`motivo` | `USAR_BANCO_PERDAS` |
| Custo | `custoproduto` | `USAR_BANCO_CUSTO` |
| Itens a vencer | `itemprevencido` | `USAR_BANCO_AVENCER` |
| Cadastro (DADOS) | `curvaabcprodutounidadenegocio`+`suspendecompraprodutounidadenegocio`+`estoque`+cálculo | `USAR_BANCO_CADASTRO` |
| Catálogo | `classificacaoproduto`+`curvaabcproduto` | `USAR_BANCO_CATALOGO` |
| Faturamento | `itemvenda` agregado | `USAR_BANCO_FATURAMENTO` |

**Botão "Atualizar agora"** na sidebar (topo, sempre visível) — limpa o
cache dos 6 caches de banco e busca de novo na hora, sem esperar os 15
minutos do TTL (`st.cache_data(ttl=900)` em todos).

**Cadastro (DADOS) — a peça mais grande, decisões tomadas:**
- `curva_valor`/`curva_qtd` POR LOJA (`curvaabcprodutounidadenegocio`,
  diferente da curva GLOBAL usada no Catálogo) e `motivo_susp`
  (`suspendecompraprodutounidadenegocio` → `motivo`) são campo direto
  do ERP — sem suposição.
- `mvm` (média venda mensal), `pvm` (preço venda médio),
  `ult_venda_dias`, `ult_compra_dias` são **calculados** (não são campo
  direto): mvm/pvm sobre os últimos 90 dias de `itemvenda`;
  ult_venda_dias/ult_compra_dias são inequívocos (dias desde a
  última venda/compra em `itemvenda`/`historicocusto`, sem suposição
  nenhuma), só mvm/pvm têm uma escolha de janela (90 dias) que
  **ainda não foi confirmada com o Gabriel** se bate com o critério
  real da "Sugestão de Compra" do ERP — vale perguntar se ele notar
  giro/mvm estranho.
- **Não busca o catálogo inteiro x 23 lojas** — só as combinações
  (loja, produto) que Perdas + Itens a vencer já carregaram (achado:
  a busca sem filtro trazia MUITO mais linhas que os arquivos DADOS
  reais tinham, produto que a loja nunca teve nenhum sinal). `custo_medio`
  não vem mais do Cadastro (usar `load_custo_do_banco`, grão EAN, bem
  melhor cobertura).

**2 bugs reais achados e corrigidos no caminho (ambos confirmados com
dado real antes de fechar):**
1. **Código de loja sem zero à esquerda.** `str(int(loja))` dava "7" em
   vez de "07" (como `unidadenegocio.codigo` guarda) — o JOIN do
   Cadastro falhava silenciosamente pra TODA loja de 1 dígito (lojas
   2-9). Resultado: 3.165 de 8.106 pares pedidos sem NENHUM match,
   `sem_cadastro` inflado pra 37% (deveria ser bem menor). Corrigido
   com `.zfill(2)`; `sem_cadastro` caiu pra 4,2% depois do fix — número
   plausível.
2. **1 lote com quantidade absurda no próprio ERP.** LANCETA ACCU CHEK
   FASTCLIX, lote `WPK193A`, loja 11: `quantidadeinicial = 31.122.025`
   (o 2º maior saldo real de todo o banco é 119 — 260 mil vezes menor).
   O mesmo lote no arquivo manual antigo tinha saldo=1 numa loja
   diferente (9) — é erro de digitação recente na origem, não bug
   nosso. Sem filtro, esse 1 registro sozinho inflava "Estoque exposto"
   de ~R$300 mil pra **R$1,7 BILHÃO** (achado testando no navegador,
   não só por script). `LIMITE_SALDO_PLAUSIVEL = 100.000` novo em
   `core.py` (bem folgado, nunca excluiria um saldo real já visto) —
   blinda contra esse tipo de erro de digitação. **Vale o Gabriel
   corrigir esse lote direto no ERP quando puder** (não afeta mais a
   ferramenta, mas o dado errado continua lá na origem).

**1 bug menor corrigido no caminho:** `pvm` (usado no 2º nível do
resgate automático de custo) nunca chegava no cálculo quando
`custo_medio` faltava no cadastro — os 2 campos vinham do mesmo merge
condicional (`"custo_medio" in cad.columns`), então faltando um dos
dois o outro também sumia. Desacoplados em `enriquecer_a_vencer`.

**Validado com o pipeline inteiro, dado real, e confirmado ao vivo no
Chrome nas 3 telas (Painel, Anatomia, Itens a vencer) depois dos 2
fixes:**
- Painel: faturamento 9 meses R$77,4M (agora inclui setembro — antes
  ficava de fora por falta de `faturamento.csv`; e inclui a loja 12,
  que não entrava no arquivo antigo), perda R$494.554, taxa 0,64%.
- Anatomia: 9.005 linhas, medicamento 50% / não-medicamento 50%.
- Itens a vencer: **R$300.381 de estoque exposto** (bate com o
  histórico documentado, ~R$277-396 mil), 4.707 lotes, **0 EAN
  inválido** (era 8 no arquivo antigo — o banco usa
  `embalagem.codigobarras`, o EAN de verdade, sem a ambiguidade
  "Código/Etiqueta" que o relatório manual tinha), 0 custo zerado sem
  solução, 38 preços resgatados automaticamente.

**Pendências reais que ficam:**
- Confirmar com o Gabriel se a janela de 90 dias pra mvm/pvm faz
  sentido (ou se ele quer outro critério, tipo o mesmo do ERP).
- Sugerir ao Gabriel corrigir o lote WPK193A (LANCETA ACCU CHEK, loja
  11) no ERP — quantidade errada na origem.
- `sem_cadastro` em 4,2% (278 de 6.581 no escopo "vencido") — residual
  plausível (produto sem venda/curva no período de 365 dias
  considerado), não investigado item a item.
- Servidor rodando só local (`localhost:8501`) — perguntar se quer
  expor na rede (mesmo processo dos outros 3 projetos,
  `iniciar_para_rede.bat` + `ALLOWED_HOSTS`/`.gitignore` equivalente)
  se quiser acesso de outras pessoas.

## CONCLUÍDO NESTA SESSÃO (2026-09-25, 1ª parte) — Perdas direto do banco do ERP

Gabriel pediu pra trazer os dados do banco do ERP (mesmo banco Postgres já
usado no [[projeto-painel-ofertas]] e no [[projeto-cestas-vendas]] — ver
[[projeto-integracao-sql-server]]), começando só pela fonte **Perdas**
(as outras 4 — Itens a vencer, Custo, Faturamento, Catálogo — ficam pra
depois, decisão explícita dele).

**Tabelas achadas e validadas:** `baixaestoque` (1 por baixa: loja,
motivo, data) + `itembaixaestoque` (1 por produto dentro da baixa:
quantidade/valor) + `motivo` (descrição) — equivalente exato do
relatório "Análise de Baixa de Estoque" (.xls) que era exportado à mão.
Validado: 1 linha específica (loja 02, ABS LONGO MODERADO, set/26,
motivo PRODUTO VENCIDO) bate **exato** contra o .xls (2 itens,
R$13,92); soma jan-set/26 bate a **0,9%** (banco R$497.294 vs planilha
R$492.727 — diferença esperada, a planilha é um extrato estático de uma
data anterior, o banco é a foto atual). Filtro `status='F'` nas duas
tabelas é obrigatório (mesmo achado do painel-ofertas pra
`venda`/`itemvenda`: sem ele, baixa cancelada ou aberta entra na soma).
Também achei (não implementado ainda, registrado pra quando for a vez
das outras fontes): `itemprevencido` (lote/validade/quantidade —
bate exato com os campos que "Itens a vencer" já espera) e
`sugestaocompra` (provável correspondente da planilha "base suges" de
custo).

**Implementado (sem commit ainda no momento de escrever isto):**
- `erp_banco.py` (novo, raiz do projeto) — conexão somente leitura
  (mesmo padrão dos outros 2 projetos: `.env` fora do Git,
  `default_transaction_read_only=on`), `consultar_baixa_estoque(desde)`.
  Diferente dos outros 2 (Django), este projeto é Streamlit puro — lê o
  `.env` relativo ao próprio arquivo, sem `settings.BASE_DIR`.
- `core.load_perdas_do_banco(desde)` — mesma saída de `load_perdas`
  (loja, ano_mes, produto, motivo, motivo_cat, is_dep, itens,
  valor_unit, valor_total), só que a partir do banco. Reaproveita
  `classify_motivo` sem mudança — o vocabulário de motivo do banco já é
  o mesmo do .xls (mesma fonte).
- `app.py`: banco em 1º lugar (`USAR_BANCO_PERDAS = True`, constante no
  topo do arquivo — trocar pra `False` volta a usar só o arquivo),
  cai pro `.xls`/upload manual automaticamente se o banco falhar
  (rede, credencial) — nunca quebra o app por causa do banco. Upload
  manual continua tendo prioridade sobre os dois (ação explícita do
  usuário). Cache `st.cache_data(ttl=900)` — recarrega do banco a cada
  15 min, mesmo padrão de TTL já usado no resto do app. Caption "Fonte
  das perdas: Banco do ERP (ao vivo)" no topo do Painel, pra ficar claro
  de onde o dado está vindo.
- `.env`/`.env.exemplo` (`.env` fora do Git) — mesma senha do Painel de
  Ofertas/Cestas & Vendas/DBeaver. `requirements.txt`:
  `psycopg[binary]>=3.2`.

**Validado ao vivo (não só curl):** Painel mostra "Fonte das perdas:
Banco do ERP (ao vivo)", números reais (faturamento R$69,69M/8 meses,
perda R$458.237, taxa 0,66%), setembro corretamente sinalizado como
"sem faturamento" (mês ainda não fechou). Anatomia da perda também
funcionando com o dado do banco cruzado com o cadastro/catálogo
(medicamento 50% / não-medicamento 47% / sem classificação 3%,
9.005 linhas). `streamlit.testing` smoke test: 0 exceções.

**Pendência real, não resolvida ainda:** a diferença de 0,9% entre
banco e planilha não foi investigada a fundo (lojas 21/ESC não
explicam — testado, contribuem ~R$0 no período). Mais provável é só
defasagem temporal (planilha é uma foto de um momento anterior). Não
bloqueia o uso — só registrar caso o Gabriel pergunte por que os
números mudaram um pouco depois da troca de fonte.

**Custo também migrado no mesmo dia (25/09/26), mas de uma tabela
MELHOR do que a mapeada inicialmente.** Gabriel achou sozinho no banco
(explorando por fora) as tabelas `custoproduto` (custo ATUAL por
produto x loja, mantido pelo próprio ERP) e `historicocusto` (log de
eventos por trás dela, 1 por nota fiscal/recebimento) e perguntou se
não fazia mais sentido usar essas em vez da "base suges" (sugestão de
compra) que eu tinha mapeado. **Fazia — investiguei e troquei:**
- `custoproduto` nunca tem `custo`/`customedio` nulo ou ≤0 nas 706 mil
  linhas (vs. ~26% zerado/quase-zero no "Custo Médio" do DADOS/base
  suges). Cobertura por (produto, loja) não é 100% — quando a própria
  loja nunca comprou o item diretamente não tem linha lá (ausência, não
  zero) — mas testado contra os 28.450 itens de custo inválido de um
  arquivo DADOS real: **89,6% resolvido** só combinando `custoproduto`
  com o fallback que já existia (`calcular_fallback_custo`, maior custo
  do mesmo EAN em outra loja).
- `erp_banco.consultar_custo_produto()` + `core.load_custo_do_banco()`
  (mesma saída de `load_base_suges`: loja/ean/custo — substituto
  direto, sem precisar mudar `enriquecer_a_vencer`/
  `calcular_fallback_custo`). Prioriza `customedio` (ponderado, mais
  estável) sobre `custo` (última compra).
- `app.py`: `USAR_BANCO_CUSTO = True`, mesmo esquema de fallback
  automático pro arquivo "base suges" se o banco falhar. Caption da
  tela Itens a vencer mostra a fonte real (`CTX['fonte_custo']`).
- **Validado com o pipeline inteiro, dado real** (`load_itens_a_vencer`
  → `enriquecer_a_vencer` → `enriquecer_precos` →
  `calcular_fallback_custo` → `exportar_erp_precos`, os 4.761 itens do
  arquivo atual): custo inválido sem solução ficou em **2** (igual ao
  melhor resultado já alcançado, mas agora sem precisar do arquivo de
  88MB), só 8 de 4.761 sem custo médio, fallback resgatou 32. Não deu
  pra confirmar visualmente no navegador desta vez (extensão do Chrome
  desconectada na hora) — só validação direta do pipeline via script,
  pedir confirmação visual do Gabriel na próxima sessão.
- `historicocusto` não foi usado diretamente — é só o log por trás do
  `custoproduto`, que já é o resumo/atual que interessa aqui.

**Próximo passo, quando o Gabriel pedir:** repetir o mesmo processo pra
Itens a vencer (`itemprevencido`), Faturamento (reaproveitar
`consultar_venda_geral_mensal` já pronto no painel-ofertas) e Catálogo
(reaproveitar `CONSULTA_PRODUTOS` já pronto no cestas-vendas). Custo já
está feito (ver acima).

## CONCLUÍDO NESTA SESSÃO (fim da sessão 2026-09-17)

Tudo commitado (5 commits desde o README anterior, ainda não enviados ao
GitHub — `git push` pendente), working tree limpa. App sobe em
`localhost:8501`. Frentes reais resolvidas nesta sessão, todas em torno
de "Itens a vencer" → preço sugerido → arquivo de importação do ERP:

**1. Código inválido no arquivo de importação (`57bf0b5`).** O relatório
usa a coluna "Cod. Barras/Etiqueta", que mistura EAN de verdade com
código interno de etiqueta quando o lote não tem EAN cadastrado — o
arquivo gerado saía com código de etiqueta (ex. "38493") em vez de EAN,
e o ERP rejeitava o arquivo **inteiro** por causa de 1 linha ruim.
`_ean_valido()` novo (8+ dígitos) filtra esses casos antes de montar os
4 arquivos; UI avisa quantos itens ficaram de fora e por quê.

**2. Preço sugerido virou editável (`fd3567a`).** Coluna "Preço
sugerido" da tabela Itens virou `st.data_editor` — edição fica em
`session_state` por (EAN, faixa), sobrescreve o cálculo tanto na tela
quanto nos 4 arquivos baixados, com botão "Desfazer edições".

**3. Custo inválido (zerado/negativo/<1 centavo) excluído (`b73583f`)
+ resgate automático (`8f0b2da`).** `sugerir_preco()` passou a exigir
custo>0 E preço final ≥R$0,01 (ERP recusa preço abaixo disso). Pra não
simplesmente descartar o item, `calcular_fallback_custo()` tenta em 2
níveis: (1) maior custo válido do mesmo EAN em OUTRA loja, (2) Preço
Venda Médio (já no cadastro) com o mesmo fator de desconto, se não
houver custo válido em loja nenhuma. **Bug real corrigido no caminho:**
em `exportar_erp_precos`, os overrides (edição manual) eram aplicados
DEPOIS de descartar linha sem preço válido — um item que só existia
graças à edição manual ou ao resgate automático nunca recebia o preço
(a linha já tinha sumido antes de aplicar o override). Resultado real:
custo inválido sem solução caiu de 55 para 2 itens.

**4. Fonte de custo trocada (`bc80dce`).** Achado real: o campo "Custo
Médio" do DADOS fica zerado/quase-zero sem motivo em ~26% da base — mas
a coluna "Custo" de uma base NOVA (planilha "base suges", sugestão de
compra do ERP, ~353 mil linhas) é plausível nos mesmos casos onde
"Custo Médio" falha. `load_base_suges()` novo (cache parquet);
`enriquecer_a_vencer` passou a juntar por (loja, EAN) em vez de (loja,
produto), usando "Custo" da base nova como prioridade e caindo pro
Custo Médio do DADOS só quando faltar.

**5. Botão de limpar busca (`4bad6a5`).** "x" ao lado de "Buscar
(produto ou EAN)" em Itens a vencer, sem precisar apagar manualmente.

Sem nenhuma pendência de código aberta desta rodada — próxima frente é
faturamento de setembro (quando fechar) e, a partir de 25/09/26,
integração com o banco do ERP (ver seção abaixo).

## Infraestrutura — backup (16/09/26)

Repositório não tinha remoto (só commits locais) — criado
https://github.com/gabrielvelanes-coder/monitor-de-perdas e enviado todo
o histórico (`git push -u origin master`). Novo `backup_dados.py`
(`python backup_dados.py`, roda manual, sem Tarefa Agendada) copia
`DADOS*.xlsx`/`BASE CADASTRO*.xlsx`/`perdas*.xls`/`faturamento.csv`/
`itens a vencer.xlsx`/`regionais.csv` (nunca vão pro Git) pra
`OneDrive\Área de Trabalho\BACKUPS DB\PERDAS\<carimbo>\`, mantém as 5
rodadas mais recentes. Mesmo processo aplicado no projeto Monitor de
Preço de Mercado (`OneDrive\Área de Trabalho\MONITOR DE PRECOS\
monitor-precos`) no mesmo dia.

## CONCLUÍDO NESTA SESSÃO (fim da sessão 2026-09-14)

Tudo commitado, working tree limpa, app rodando em `localhost:8501` com o
código mais recente. Frentes em aberto pra continuar:

1. **Faturamento de setembro/2026** — só quando o mês fechar (ver
   [PENDENTE #1](#1-faturamento-de-setembro2026) mais abaixo). Não é bug:
   testado com uma loja específica sem filtro de mês, jan–ago aparecem
   normais, só set/26 cai no aviso "Meses sem faturamento informado" —
   esperado, faturamento.csv não tem setembro ainda.

**Preço sugerido do pré-vencido — IMPLEMENTADO (14/09/26).** Gabriel deu
o sinal verde depois do planejamento fechar (ver
[PLANEJAMENTO](#planejamento--regra-de-precificação-do-pré-vencido-2026-09-12)
logo abaixo pro histórico da decisão). `core.py` ganhou `faixa_preco`,
`sugerir_preco`, `enriquecer_precos`, `exportar_erp_precos`; tela **Itens
a vencer** ganhou seção "Preço sugerido — pré-vencido" com 4 botões de
download (`oferta_30dias.txt`/`60`/`90`/`120dias.txt`, layout
`A|EAN|||PREÇO`) + coluna "Preço sugerido" na tabela. Validado com dados
reais (4249 lotes, 188 CAMPANHA) e `streamlit.testing` (0 exceções).
Depois, mais 2 ajustes na mesma tela: **filtro "Faixa de preço"**
(30/60/90/120, multiselect ao lado de Urgência — diferente granularidade,
Urgência é 30/90/180/365 pra visão geral) pra ver só os itens de 1 faixa
específica; e **"Digitar faturamento" oculto** da sidebar (Gabriel
perguntou pra que servia — nunca era realmente usado, `faturamento.csv`
sempre tem prioridade quando existe; `MOSTRAR_DIGITAR_FATURAMENTO = False`
no topo do `app.py`, mesmo tratamento de "Fontes de dados"). Filtro de
faixa de preço **movido** (Gabriel não gostou dele junto de Regional/
Lojas/Urgência — mexia em cards/gráficos/downloads também) pra dentro do
container da tabela "Itens", filtrando só ela. Mais 2 ajustes na mesma
tabela: coluna **"Custo médio"** antes de "Preço sugerido" (pra conferir
o desconto aplicado) e busca **"Buscar (produto ou EAN)"**. Tabela
"Produtos" da **Anatomia** ganhou busca por nome também (só nome — a
base de perdas não tem EAN). Cabeçalho "Monitor de Perdas" movido pra
cima do menu de navegação, via `st.logo(assets/logo.svg)` — jeito
suportado pelo Streamlit de "furar a fila" do `st.navigation`, que
sempre reserva o topo da sidebar pro menu. Gráficos **"Curva de
quantidade"** e **"Tempo da última venda"** (Anatomia) ganharam o % de
cada barra sobre o total do próprio gráfico, junto do R$/unidades —
`_fmtcol_pct()` novo (não mexe em `_fmtcol`, usado em vários outros
gráficos do app). Tudo verificado ao vivo no Chrome, não só por teste
automatizado.

**Tabela "Produtos" (Anatomia) — 3 rodadas de interação, FECHADA
(14/09/26):** 1ª: clique-na-linha via `st.dataframe(on_select="rerun")`
— Gabriel testou, "não apareceu nada" (causa provável: clicou na linha/
texto, que só foca a célula, não no quadradinho de seleção — e o painel
ficava depois de "Baixar (CSV)", podia ter passado batido rolando).
2ª: trocado por `st.selectbox` (funcionou ao vivo, testei), mas Gabriel
não gostou do modelo, queria clique mesmo. 3ª (estado final, `c14895b`):
**volta ao clique-na-linha**, com caption explícito mandando clicar no
quadradinho e o painel movido pra logo depois da tabela — **Gabriel
confirmou que funciona** ("está funcionando"). Coluna "Status catálogo"
removida (ficou assim nas 3 rodadas). **Lição pro app:** `st.dataframe`
com seleção de linha funciona bem desde que (a) a instrução deixe claro
que é o quadradinho que seleciona, não a linha/célula, e (b) o resultado
apareça o mais perto possível da tabela, sem exigir rolar a tela.

**Regra de preço própria pra medicamento — implementada e REVERTIDA no
mesmo dia (14/09/26).** `sugerir_preco()` ganhou uma 3ª tabela de fator,
só pra categoria (nível 1) **medicamento** (PROPAGADO/GENÉRICOS/
SIMILARES, mesmo critério de `macro_categoria()`): 30d 0,90 / 60d 1,00 /
90d 1,05 / 120d 1,10 — validada com 1644 lotes reais, fatores batendo
100%. **Gabriel simulou os 4 arquivos e achou vários itens altos demais**
— a regra nova desconta MENOS que a padrão nas faixas de 30/60/90 dias
(só ficava mais barata que a padrão aos 120 dias). Pediu pra voltar à
regra padrão pra medicamento — revertido, `sugerir_preco()` tem só 2
casos de novo (CAMPANHA vs. padrão, medicamento sem tratamento
especial). Os números ficam comentados em `core.py` (não apagados) pra
retomar rápido se o Gabriel quiser tentar de novo com desconto maior.
**Lição:** simular antes de fechar uma regra de preço — o número "parece
razoável" na conversa pode não bater com o padrão anterior linha a
linha; comparar contra a regra vigente, não só contra a intuição.

Sem nenhuma outra pendência de código aberta.

---

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — tira "Sem regional" do filtro)

Gabriel notou que o filtro Regional oferecia uma 3ª opção **"Sem regional"**
(pegava a loja 12, que é DEP/depósito e não está no `regionais.csv`) e
apontou que esse balde não deveria existir — ou é Regional 1/2, ou nem
aparece. Corrigido: `_regional_local` só lista lojas que **estão** no mapa
(`if int(l) in reg_map`), nunca sintetiza "Sem regional" como opção;
`_filtra_regional` também não trata mais loja fora do mapa como uma
categoria — ela simplesmente nunca bate com nenhuma regional escolhida (ou
seja, filtrando por "Regional 1" ou "Regional 2" ela sempre fica de fora, e
sem filtro nenhum ela aparece normal, igual antes do filtro existir).
Verificado no app rodando: dropdown mostra só "Regional 1" / "Regional 2".

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — filtro por Regional)

Item 6 do pedido do Gabriel: filtro de **Regional** (2 supervisores, cada um
cuida de um grupo de lojas) nas telas, além do filtro de loja individual que
já existia. Ele mandou as duas listas (por print, em 3 rodadas até fechar —
as lojas 08/15/16 ficaram de fora dos 2 primeiros prints por corte de tela):

- **Regional 1** (11 lojas): 2, 3, 4, 10, 13, 14, 15, 17, 19, 20, 25
- **Regional 2** (11 lojas): 5, 6, 7, 8, 9, 11, 16, 18, 22, 23, 24

Bate certinho com as 22 lojas que a ferramenta já conhece (loja 12 do
relatório de perdas é DEP/depósito — fica como "Sem regional").

**Implementação:**
- `regionais.csv` (loja, regional) criado na pasta — **fora do git**
  (`.gitignore`), igual `faturamento.csv`: como a divisão é **rotativa**
  (supervisor pode trocar de grupo), o Gabriel edita esse arquivo direto
  quando mudar, sem precisar de código novo.
- `core.load_regionais(src) -> {loja: regional}` — novo, lê o CSV (aceita
  variação de nome de coluna: LOJA/UND/NEG, REGIONAL/SUPERVISOR).
- `app.py`: `build_context` auto-detecta `regionais.csv` (ou `*regional*.csv`)
  e expõe `CTX["loja_regional"]`. Dois helpers novos, no mesmo padrão de
  `_loja_local`/`_mes_local`: `_regional_local(df, key, container)` (mostra o
  multiselect "Regional (nesta tela)", some se só tiver 1 regional no
  recorte) e `_filtra_regional(df, regsel)` (aplica o filtro num dataframe
  com coluna `loja`).
- Ligado nas 3 telas visíveis: **Painel** (novo `c_reg`, aplicado em
  `perdas`/`fat`/`vc` antes do filtro de mês/loja), **Anatomia** (aplicado em
  `vc` e em `vfull`, o bloco "Todos os motivos no recorte") e **Itens a
  vencer** (aplicado em `enr`, junto com Lojas/Urgência).

Verificado no app rodando (Chrome): selecionar "Regional 1" no Painel muda
faturamento de R$ 69,7M → R$ 34,4M e o ranking de lojas cai de 22 pra
exatamente as 11 lojas certas. Mesmo comportamento na Anatomia e Itens a
vencer. `streamlit.testing` smoke test: 0 exceções.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — "Fontes de dados" oculto)

Gabriel perguntou se o expander **"Fontes de dados"** (uploaders manuais na
barra lateral) ainda tinha necessidade, já que o app auto-detecta os 5
arquivos pela pasta. Decisão: manter a funcionalidade (fallback útil pra
testar um relatório pontual sem mover pra pasta), mas **ocultar** da UI —
mesmo tratamento dado a Motivos/Evitável/Regras. `app.py`: nova constante
`MOSTRAR_FONTES_DADOS = False` no topo; o bloco dos 5 `st.file_uploader`
só roda se `True` (os `up_*` viram `None` quando oculto — o resto do código
já testava `is not None`, nada mais mudou). Reativa voltando a constante
pra `True`.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — limpeza do Painel)

Removido o expander **"Bater com o número da reunião"** do rodapé do
Painel — campo pra digitar um valor/% apresentado numa reunião e ver a
diferença contra o dado da ferramenta. Era uma muleta da fase inicial
(quando a taxa da ferramenta divergia do Power BI e precisava provar/
comparar número a número); hoje o "Bridge de escopo" já mostra os 3
recortes lado a lado, então virou redundante. A pedido do Gabriel.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — números em pt-BR em tabelas e gráficos)

Gabriel pediu pra revisar **todos** os números de venda/perda em tabelas e
gráficos e formatar em pt-BR (milhar com ponto, decimal com vírgula).
Achado: várias tabelas usavam `st.column_config.NumberColumn(format="R$
%.0f")` (Python `%`-format — sem separador de milhar nenhum, ex. "R$
388455") e quase todos os gráficos usavam `alt.Tooltip(..., format=",.0f")`
(d3-format americano — vírgula como milhar, ex. "388,455") tanto nas
tooltips quanto nos rótulos de valor em cima das barras (`mark_text`). O
texto do "Diagnóstico" no Painel também tinha `.2f` cru (`0.67%` em vez de
`0,67%`).

**Correção sistemática** (`app.py` + `core.py`):
- `PTNUM(v, d=0)` novo — formatador pt-BR genérico (milhar `.`, decimal
  `,`), usa `str.translate` pra trocar os separadores de uma vez só (evita
  o bug clássico de `.replace()` em cadeia embaralhar milhar com decimal).
- `_fmtcol(df, col, fmt)` novo — cria `<col>_fmt` (string já em pt-BR) num
  dataframe e devolve o nome da coluna, pra usar em `Tooltip`/`Text` do
  Altair como campo **Nominal** (`:N`) em vez de `Quantitative` com
  `format=`. O Vega-Lite não tem como trocar milhar/decimal por um format
  string (isso exigiria configurar um *locale* D3 no embed, que o
  `st.altair_chart` não expõe) — pré-formatar a string em Python e tratar
  como texto é o jeito confiável, já usado desde a sessão de 09-11 na
  tabela "Todos os motivos".
- Todas as tabelas (`NumberColumn` → coluna já formatada + `column_config`
  só com o rótulo) e todos os gráficos (tooltip + rótulo em cima da barra)
  do Painel, Anatomia, Itens a vencer e das telas ocultas (Motivos,
  Evitável, Regras) passaram por essa troca.
- `core.frase_diagnostico`: os `.2f` da taxa/meta agora trocam `.`→`,`.
- **Achado no caminho:** 2 gráficos tinham a *mesma* string de título no
  eixo (`title="R$"`) e na tooltip customizada — title duplicado colide na
  descrição de acessibilidade do Vega-Lite (não afeta o hover visual, mas
  por clareza os títulos da tooltip viraram "R$ perda"/"R$ no mês").

**Limitação conhecida, avisada ao Gabriel:** os **números dos eixos** dos
gráficos (as marcações de escala, tipo "20,000" no eixo X) continuam no
padrão americano — trocar isso exigiria configurar um *locale* D3 global no
Vega, que o `st.altair_chart` do Streamlit não expõe hoje. Só os valores
que aparecem em tabelas, tooltips (ao passar o mouse) e rótulos em cima das
barras foram corrigidos — que é o que normalmente se lê.

Verificado no app rodando (Chrome, via árvore de acessibilidade dos
gráficos): tooltips mostram "taxa %: 1,23", "perda: R$ 36.066", "R$ perda:
388.455", etc. — todos com separador pt-BR correto. `streamlit.testing`
smoke test: 0 exceções.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — bug de alinhamento na Anatomia)

Gabriel reparou que na "Anatomia da perda", bloco "Todos os motivos no
recorte", a ordem das barras do gráfico não batia com a ordem da tabela ao
lado (tabela: maior R$ primeiro; gráfico: alfabético). Causa: `y=alt.Y(...,
sort="-x")` em duas camadas (`ch_m` + `lbl_m`, barra e rótulo de valor)
construídas como dois `alt.Chart(gmot)` **independentes** — `sort="-x"` não
fica estável entre camadas independentes nesse caso (mesma classe de bug já
resolvida antes no gráfico "Por urgência" do Itens a vencer, ali com uma
lista explícita `core.ORDEM_URGENCIA`). Corrigido do mesmo jeito: `ordem_mot
= gmot["motivo_label"].tolist()` (já vem ordenado por valor) passado como
`sort=ordem_mot` nas duas camadas. Testado no browser: gráfico agora segue
a mesma ordem decrescente da tabela. Os outros 3 gráficos da Anatomia
(categoria/curva/tempo) não tinham esse bug — usam um `base` compartilhado
entre a camada de barra e a de rótulo, em vez de dois `Chart(...)`
separados.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — terminologia sem viés)

Gabriel notou que "Perda real" (no seletor "Escopo da perda") dá a entender
que os outros escopos não são reais — viés de linguagem, bem na contramão do
que a mudança do item 2 (perda = todos os motivos) queria resolver. Pediu
sugestão neutra.

Termos trocados em **todo o app** (não só o seletor do Painel — a Anatomia
tinha o mesmo seletor, e o gráfico "Top motivos" a mesma classificação):
- **"Perda real"** → **"Perda direta"** (vencido + danificado + furto +
  descontinuado + outros — sai do estoque sem nenhuma compensação).
- **"Outra perda real"** → **"Outra perda direta"** e **"Não é perda"** →
  **"Baixa comercial"** (`core.CLASSES_PERDA`/`_CLASSE_MOTIVO`, usados no
  gráfico "Top motivos" do Painel e na tela Motivos oculta) — descreve o que
  é (tem contrapartida comercial: marketing/reembolso/consumo/doação) em vez
  de negar que seja perda.
- `core.ESCOPOS["perda_real"]` e todo texto de ajuda/rótulo correspondente
  em `app.py` (Painel, Anatomia, Bridge de escopo) e no `README.md`
  atualizados junto. A chave interna `"perda_real"`/`IS_PERDA_REAL` no código
  não mudou (só o texto visível ao usuário).

Verificado no app rodando: seletor do Painel, Bridge de escopo, legenda "Top
motivos" e seletor "Motivos" da Anatomia todos mostram os termos novos.

## CONCLUÍDO NESTA SESSÃO (2026-09-12)

Lista de 5 pedidos do Gabriel, resolvidos um a um (a lista virou seção
"PENDENTE" abaixo pro que ainda falta — item 5).

**1. Itens a vencer — faixas de urgência viraram cumulativas.** `core.py`:
`_faixa_urgencia`/`ORDEM_URGENCIA` trocaram os baldes exclusivos antigos
(Até 30 / 31-60 / 61-90 / 91-180 / Mais de 180 dias) pelos novos, pedidos
pelo Gabriel: **Até 30 dias / Até 90 dias / Até 180 dias / Até 12 meses /
Mais de 12 meses** (+ Sem data). `app.py`: KPI "Vence em até 90 dias"
ajustado pra somar os baldes novos.

**2. Painel — perda passa a somar todos os motivos por padrão, com filtro.**
Gabriel formalizou o entendimento: **perda = toda baixa do sistema**,
independente do motivo (marketing, reembolso, consumo, doação também contam
— não só vencido/danificado/furto/descontinuado) — mas ele ainda precisa
enxergar os motivos individualmente pra achar gargalos (por isso a "Bridge
de escopo" e "Top motivos" continuam na tela). `ESCOPO_PADRAO` (`app.py`)
virou `"todos"` (era `"vencido"`). `tela_veredito` ganhou de volta um
seletor **"Escopo da perda"** (segmented control: Vencido / Perda real /
Todos os motivos, default Todos os motivos) — a taxa do topo, o gráfico de
evolução e o ranking de lojas recalculam com o escopo escolhido. Testado no
browser: Todos os motivos → 0,66% (R$ 463.227); Vencido → 0,53%
(R$ 368.815, bate com o número de antes da mudança).

**3. Removido o texto "A perda é aceitável? · escopo: ... · recorte
global: ... · fonte ..."** do topo do Painel (poluía ao lado do novo
seletor de escopo).

**4. Menu "Motivos" ocultado.** Gabriel pediu pra não mexer nele por
enquanto (a tela ainda existe no código, comentada em `st.navigation`,
igual Evitável/Regras). Menu agora tem só 3 itens: Painel · Anatomia da
perda · Itens a vencer. Docstring do topo do `app.py` atualizada.

**5. Anatomia — clicar numa 2ª barra do mesmo gráfico agora substitui a
1ª (em vez de somar).** Gabriel confirmou o cenário exato: dentro do MESMO
gráfico (ex. Categoria), clicar em GENÉRICOS depois PROPAGADO deixava os
dois somados na tabela — só resetava clicando "Limpar filtros". Causa:
`alt.selection_point(..., toggle="true")` nos 3 gráficos força todo clique
a ser aditivo (multi-seleção), mesmo sem Shift. Corrigido: `toggle="true"`
removido dos 3 (`sel_cat`/`sel_cv`/`sel_g`) — volta ao padrão do Vega-Lite
(clique normal **substitui** a seleção; Shift+clique estende pra
multi-seleção quem quiser). Efeito colateral aceito: clicar 2x na mesma
barra não "solta" mais sozinho — usa o botão "Limpar filtros dos gráficos"
pra isso (Gabriel topou essa troca). Testado no browser: clicar PROPAGADO →
tabela "Categoria: PROPAGADO"; clicar GENÉRICOS em seguida → tabela vira
"Categoria: GENÉRICOS" (não mais "PROPAGADO, GENÉRICOS").

## CONCLUÍDO NESTA SESSÃO (2026-09-11, continuação)

### Correção: "Itens a vencer" usava a coluna errada para o valor exposto
Gabriel explicou os 4 campos do relatório do ERP (que a tela tratava como se
`Estoque Atual` fosse o "estoque pré-vencido"):
- **Quantidade Inicial** (`qtd_inicial`) — quantidade lançada no lote pré-vencido.
- **Qtd. Movimentada** (`qtd_movimentada`) — quantidade já vendida *dentro* desse
  pré-vencido.
- **Saldo** (`saldo`) = Quantidade Inicial − Qtd. Movimentada — o que **ainda
  resta** daquele lote pré-vencido. **É isso que expõe risco de perda.**
- **Estoque Atual** (`estoque_atual`) — estoque **geral** da loja pro produto,
  **não** restrito a esse lote (pode incluir outros lotes normais, ou não
  refletir ainda a baixa do pré-vencido) — só referência.

O código usava `estoque_atual` (clipado ≥0) como base de `valor_exposto`. Nos
dados reais, `saldo` ≠ `estoque_atual` em **2.648 das 4.249 linhas (62%)** —
em alguns casos o estoque geral é maior (mistura outros lotes), em outros é
menor (a baixa do pré-vencido ainda não bateu no estoque geral). Corrigido:
`core.enriquecer_a_vencer` agora usa `saldo` (com fallback pra `estoque_atual`
só se o relatório não trouxer a coluna Saldo — com aviso na tela). `core.py`:
`_AVENCER_MAP` ganhou `qtd_inicial`/`qtd_movimentada`/`saldo`. `app.py`: tabela
da tela mostra **Saldo (pré-vencido)** e **Estoque atual (geral)** lado a lado;
caption do topo trocou "Estoque atual" por "Saldo do pré-vencido".

**Efeito real medido:** total de estoque exposto caiu de **R$ 396.050**
(errado, base `estoque_atual`) para **R$ 277.439** (correto, base `saldo`) —
o número antigo superestimava o risco ao contar estoque de outros lotes como
se fosse tudo pré-vencido. Por urgência (novo): ≤30d R$ 57.671 · 31-60d
R$ 81.662 · 61-90d R$ 63.760 · 91-180d R$ 56.681 · >180d R$ 17.666.

## CONCLUÍDO NESTA SESSÃO (2026-09-11)

Lista de mudanças pedida pelo Gabriel, feita em lote (commit `22414b1` + o
commit do "Itens a vencer" logo abaixo).

**Simplificação geral.** Barra lateral perdeu as seções "Filtros" (Lojas/
Período globais) e "Parâmetros" (Escopo/Meta/DEP) — viraram constantes fixas
no topo do `app.py` (`ESCOPO_PADRAO = "vencido"`, `META_PADRAO = 0.004`,
`incluir_dep = False`). Cada tela mantém seu filtro local de loja/mês
(`_loja_local`/`_mes_local`), só o filtro *global* saiu. `st.navigation` perdeu
"Evitável x estrutural" e "Regras e simulação" do menu (funções continuam no
arquivo, comentadas na lista — reativa descomentando 2 linhas).

**Anatomia da perda — 3 simplificações:**
- Removido o filtro **"Status no catálogo"** (Ativos/Inativos/Fora do
  catálogo) que ficava no topo — junto com o aviso de "quanto foi escondido".
- Removido o seletor **Curva de valor / Curva de quantidade** — agora só
  existe curva de quantidade (era o que o Gabriel queria acompanhar). Gráfico
  "Curva" (que mostrava A…I) virou **2 barras**: `_grupo_giro()` classifica
  A–H = "Com giro", I = "Sem giro" (+ "Sem cadastro"). Coluna "Curva valor"
  saiu da tabela de produtos.
- Gráfico "Quanto tempo parado quando venceu" → renomeado **"Tempo da última
  venda"**; `_grupo_tempo()` simplifica os 7 baldes antigos (`core.FAIXAS_GIRO`)
  em 3: **Até 90 dias / Até 180 dias / Acima de 180 dias** (+ "Sem cadastro").
  A interatividade clique-no-gráfico-filtra-tabela (já existia pros 3 gráficos)
  foi migrada pros novos campos (`giro_grupo`, `tempo_grupo`).

**Tabela "Todos os motivos no recorte":** coluna **"No escopo"** removida (o
gráfico ao lado ainda colore por dentro/fora do escopo, só a coluna da tabela
saiu). Números formatados em pt-BR de verdade (`BRLc()`/`NUM()` novos no
`app.py` — milhar com ponto, decimal com vírgula) em vez do `NumberColumn`
padrão do Streamlit (que não tem separador de milhar).

**Textos removidos** entre gráficos/tabelas na Anatomia (o "clique numa barra
pra filtrar", o "ignora o filtro de escopo/status", o "as lojas são número...",
o "uma linha por produto e motivo...") — quando a informação valia a pena,
virou `help=` (tooltip) de um metric em vez de texto solto na tela.

**Bug corrigido:** "Gap vs meta" mostrava `+0,13 p,p,` (a troca de separador
`.`→`,` também comia a abreviação "p.p."). Agora troca só o número.

### Itens a vencer — nova tela, com dado real
O Gabriel mandou `itens a vencer out26.xlsx` (relatório do ERP: estoque atual
com lote e validade, por loja — 4.249 linhas, 23 lojas, `Status` sempre
"Ativo", `Dias até vencimento` de 20 a 1538). Copiado pra
`PERDAS\itens a vencer.xlsx` (fora do git, como os outros dados).

`core.py`: `load_itens_a_vencer(source)` (mapa de colunas `_AVENCER_MAP`, só
`Status = Ativo`) + `enriquecer_a_vencer(av, cad)` (merge por loja+produto só
pra trazer `custo_medio`; `valor_exposto = estoque_atual.clip(0) × custo_medio`;
`macro` via `macro_categoria(classif)` reaproveitado; `urgencia` em 5 faixas —
`ORDEM_URGENCIA` = Até 30 / 31-60 / 61-90 / 91-180 / Mais de 180 dias / Sem
data). `app.py`: `_a_vencer` cache + auto-detect (`itens*a*vencer*.xls*`) +
uploader; `tela_itens_a_vencer()` substituiu o placeholder — KPIs (valor
exposto total, ≤30d, ≤90d, unidades), gráfico por urgência, gráfico por loja,
tabela (produto/lote/estoque/dias/validade/curva/categoria) + CSV.

Números (23 lojas, cadastro casou 98,3%): **R$ 396.050 de estoque exposto**,
R$ 83.985 vence em ≤30 dias, R$ 284.477 em ≤90 dias. Medicamento R$ 195.243 /
não-medicamento R$ 200.806 (bem mais equilibrado que o vencido histórico —
faz sentido, isso é o mix de estoque, não o mix do que já foi perdido). Loja
com mais valor exposto: **13** (diferente do ranking histórico de vencido,
onde 20 lidera) — vale olhar se é fruto de uma compra/transferência recente
que ainda dá tempo de agir.

## PLANEJAMENTO — regra de precificação do pré-vencido (2026-09-12, implementada 2026-09-14)

> Fica como registro histórico da decisão — já **implementado**
> (`core.faixa_preco`/`sugerir_preco`/`enriquecer_precos`/
> `exportar_erp_precos`, tela Itens a vencer), ver "RETOMAR DAQUI" no
> topo do arquivo pro estado atual.

Gabriel quis evoluir a tela **Itens a vencer**: já que o saldo pré-vencido de
cada loja está mapeado (`custo_medio` já vem no `enriquecer_a_vencer`), a
ideia é a ferramenta já **sugerir o preço com desconto** por item, em vez de
só mostrar o valor exposto.

**Regra de desconto (definida pelo Gabriel, por dias até vencer —
corrigida em 14/09/26, valores de 60 e 120 dias mudaram):**

| Até (dias) | Preço sugerido |
|---|---|
| 30 | custo × 0,75 (25% abaixo do custo) |
| 60 | custo × 0,85 (15% abaixo do custo) — era 0,95/5% antes, corrigido |
| 90 | custo × 1,00 (preço de custo) |
| 120 | custo × 1,15 (15% de markup) — era 1,10/10% antes, corrigido |
| acima de 120 | sem caderno — preço normal da loja (confirmado 14/09/26) |

Quanto mais perto de vencer, mais agressivo o desconto (inclusive abaixo do
custo nas 2 primeiras faixas) — prioriza girar o estoque a deixar vencer
(perda de 100% do custo).

**(14/09/26) Exceção — categoria CAMPANHA tem regra própria (markup, não
desconto):** Gabriel: "mesma formação de preço para todas as categorias.
com exceção para CAMPANHA." Isso também **fecha a dúvida do medicamento**
— não tem tratamento especial, é preço padrão igual às outras categorias
(só CAMPANHA foge da regra). **Atualização (14/09/26, mais tarde): não
vale mais** —
Gabriel pediu uma 3ª regra só pra medicamento, ver "RETOMAR DAQUI" no
topo do arquivo. Fica como registro histórico da decisão original.

| Até (dias) | Preço sugerido (CAMPANHA) |
|---|---|
| 30 | custo × 1,30 (30% de markup) |
| 60 | custo × 1,40 (40% de markup) |
| 90 | custo × 1,50 (50% de markup) |
| 120 | custo × 1,60 (60% de markup) |

Ao contrário da regra padrão, em CAMPANHA o markup **sobe** conforme
aproxima do vencimento — inverso da lógica de "girar antes de vencer";
provavelmente é subsidiado por outra fonte de receita (verba de
campanha/marketing do fabricante) e não é objetivo do painel questionar
a lógica de negócio, só implementar certo.

**"CAMPANHA" já existe nos dados reais e o código já tem como
identificar** — é categoria de nível 1 na coluna `classif` do relatório
de itens a vencer (`ARVORE NOVA > CAMPANHA > <subcategoria>`, ex.
"NEUROLÓGICO", "ENERGIA E FORÇA"). Testado no arquivo atual: 188 lotes
com essa classificação. `core._arvore_niveis(classif)` já extrai o nível
1 (`n1`) removendo o prefixo "ARVORE NOVA" — é só comparar
`n1 == "CAMPANHA"` pra decidir qual tabela de preço usar, mesma função
que `macro_categoria()` já usa pra medicamento/não-medicamento.

**(14/09/26) São 4 cadernos = 4 arquivos, 1 por faixa de dias — não 1
arquivo único pra rede toda como se pensava antes.** Gabriel: "temos que
ter 4 cadernos de oferta. os preços dos 30 dias, outro para 60, outro para
90 e outro para 120." Cada caderno é um arquivo separado, com os itens que
têm lote pré-vencido naquela faixa e o preço daquela faixa.

**Isso resolveu sozinho 2 dúvidas que estavam em aberto:**
- **Desempate por EAN com múltiplos lotes** — não existe mais o problema.
  Gabriel: "não tem problema ter itens iguais nos cadernos, porque o preço
  só sai na loja quando é colocado o lote e fica amarrado os dias de
  vencimento. o sistema faz a conta em cima de dias a vencer." Ou seja: se
  o mesmo EAN tem lote na faixa 30 e outro na faixa 60, ele **entra nos 2
  arquivos**, cada um com o preço da sua faixa — o ERP escolhe o preço
  certo pelo lote real selecionado na venda, não pelo arquivo. Não preciso
  mais escolher "o lote mais urgente" nem inventar critério de desempate.
- **Faixa 121–150 dias** — não existe. Só os 4 cadernos (30/60/90/120)
  existem; confirmado que acima de 120 dias não entra em nenhum arquivo,
  fica no preço normal da loja.

**Layout — CONFIRMADO (14/09/26): `A|EAN|||PREÇO`.** O print de 2 pipes
(`A|4005900664006|29.2500`) era só compressão visual do print — Gabriel
confirmou por escrito: "A|EAN|||PREÇO ESSE É O CORRETO". Uma linha por
item, campos separados por `|`, sem cabeçalho, 4 pipes (2 campos vazios
no meio):

```
A|<EAN>|||<PREÇO>
```

Exemplo real (sessão anterior):
```
A|7894913003073|||38.9700
A|7894913003066|||38.9700
A|7896023707100|||89.9500
```

- Campo 1: `A` = **"Preço"** (tipo de registro — confirmado pelo Gabriel).
- Campo 2: **EAN** (código de barras) — já temos essa coluna no relatório
  de itens a vencer (`cod_barras` em `core._AVENCER_MAP`).
- Campos 3 e 4: sempre vazios — só reproduzir a estrutura `|||`.
- Campo 5 (**preço**): ponto como decimal, sempre **4 casas** (`38.9700`,
  não `38.97`), sem separador de milhar.
- Os **4 arquivos usam o mesmo layout de linha** — só muda o conjunto de
  itens (os que têm lote na faixa daquele caderno) e o preço (a fórmula
  da faixa).

**Nomes dos 4 arquivos — confirmado (14/09/26):**

| Faixa | Arquivo |
|---|---|
| 30 dias | `oferta_30dias.txt` |
| 60 dias | `oferta_60dias.txt` |
| 90 dias | `oferta_90dias.txt` |
| 120 dias | `oferta_120dias.txt` |

Nenhuma pergunta em aberto pra este planejamento — só falta o Gabriel dar
o sinal verde pra implementar. (As faixas de dias 30/60/90/120 continuam
diferentes das faixas de urgência já usadas na tela — 30/90/180/365 —,
propósitos diferentes, uma pra agrupar/visualizar e outra pra precificar,
só registrando que não são a mesma coisa.)

Quando vier o sinal verde: `core.py` ganha `sugerir_preco(dias_venc,
custo_medio, classif) -> preco_sugerido` (regra padrão + exceção
CAMPANHA via `n1 = _arvore_niveis(classif)[0]`) + `exportar_erp_precos(df)
-> dict[str, str]` — 1 texto por faixa, chaveado pelo nome do arquivo da
tabela acima, cada um filtrando os itens daquela faixa e reaproveitando o
mesmo formato de linha (`A|EAN|||PREÇO`, 4 casas decimais) pras 4.

## PENDENTE

### 1. Faturamento de setembro/2026
`faturamento.csv` vai até **2026-08**. Setembro ainda não fechou (dado de perda
também é parcial). Quando fechar: pegar no Power BI *Visão geral - mês*, mês = set,
a coluna **Receita** por **Und. ID** (22 lojas: 2–11, 13–20, 22–25; não há 12 nem 21),
e acrescentar as linhas `loja,2026-09,valor` no `faturamento.csv`.
Conferir sempre: soma das 22 lojas = Total exibido no rodapé do relatório.
Agora dá para puxar isso pela extensão do Chrome (ver item 2).

---

## CONCLUÍDO NESTA SESSÃO (2026-09-10)

### 0. Reestruturação combinada com o Gabriel — ✅ CONCLUÍDA (a–d)
O Gabriel pediu para documentar e continuar depois. Sequência acordada (proposta
minha, ele topou a direção geral; encadear na ordem, commit a cada etapa).
Todos os quatro itens feitos nesta sessão + rodada de ajustes de filtro/tela.

**a) Filtros globais na barra lateral.** ✅ FEITO — commit `57f2dec`. Loja +
Período viraram dois multiselect no `build_context` (vazio = tudo), aplicados em
`perdas`/`fat` antes dos derivados e no resultado do cache `_vclass`. `CTX` expõe
`lojas_sel` / `meses_sel` / `perdas_full`. `tela_motivos` e `tela_anatomia`
perderam os multiselect locais; todas as telas mostram "Recorte (filtro global)".

**b) Veredito → "Painel".** ✅ FEITO — commit `55eb5d6`. `st.Page` renomeado.
Topo com 4 KPIs (faturamento no período · perda no escopo · taxa ponderada · gap
vs meta em p.p.). Diagnóstico (semáforo + frase) mantido. Evolução mensal ao lado
de ranking de lojas por taxa (barras no semáforo + régua da meta). Bridge de
escopo + top motivos reaproveitados da tela Motivos. "Bater com o número da
reunião" foi para um expander. Helpers novos: `CLASSE_COR`, `_cor_taxa`.

**c) Anatomia com seletor de motivo.** ✅ FEITO — commit `3c38334`. `_vclass`
recebe `cats` e cacheia por conjunto de motivos; `build_context` passa
`("vencido",)` p/ o `CTX["vclass"]` e expõe `psig`/`csig`. Helper
`_vclass_recorte(cats)` roda o cache com outro conjunto e reaplica o recorte
global. `tela_anatomia` tem selectbox "Motivo da baixa" (Vencido / Danificado /
Furto / Descontinuado / Perda real / Todos os motivos).

**d) Integrar o catálogo (BASE CADASTRO COM GRUPOS).** ✅ FEITO — commit `9268722`.
`core.load_catalogo` (nível produto, chave = Descrição normalizada);
`enriquecer_vencidos(catalogo=)` coalesce `classif` / `curva_valor` / `curva_qtd`
após o merge do DADOS (DADOS tem prioridade; `sem_cadastro` fixado antes).
`_vclass` recebe `cat_sig` + `_cat_df`. Anatomia ganhou radio "Status no
catálogo" (Todos / Ativos / Inativos / Fora do catálogo) e coluna "Status
catálogo". A `BASE CADASTRO COM EAN.xlsx` **não** entrou (perda não tem EAN).
Os 2 xlsx saíram do versionamento (`.gitignore`, dados sensíveis).

Efeito real medido (vencido jan–set): "sem classificação" R$ 22.039 → **R$ 4.174**
(residual "fora do catálogo"); os R$ 17.865 / 299 SKUs classificados foram para
medicamento (219.827 → **231.003**) e não-medicamento (146.589 → **153.278**).
Vencido de itens `Status = Inativo`: ~R$ 2,8 mil. Isso **fecha** a dúvida antiga
"os R$ 22 mil sem classificação" (commit `46d77bf`).

### Ajustes de leitura da Anatomia (feedback do Gabriel, commit `c5ecc70`)
Cartão **"Total — <motivo>"** na linha de KPIs. Gráfico "Tem curva?" → **"Curva"**,
estratificado por letra **A…I**. **Rótulo de valor em cada barra** dos 3 gráficos.
Coluna "R$" da tabela → "Total perda (R$)".

### Filtro clique-nos-gráficos da Anatomia — ✅ verificado no browser
Era a dúvida "não está voltando". `selection_point(toggle="true")` (re-clique na
mesma barra solta) + botão "Limpar filtros dos gráficos" (reset via nonce nas
`key` dos charts). Testado no Chrome: OK.

### 2. Extensão Claude no Chrome — ✅ CONECTOU (2026-09-10, mais tarde)
Voltou a conectar ("Browser 1", Windows local). Verificado no app rodando:
Painel, Motivos e Anatomia renderizam certo (cartão Total R$ 388.455, gráfico
"Curva" A–I, rótulos nas barras, tabela "Total perda (R$)"). Observação: o
`Page.captureScreenshot` dá timeout às vezes — o renderizador do Streamlit é
pesado (dataframes grandes + Altair em camadas); espera + repete resolve.
Agora dá para puxar dados do Power BI pela extensão em vez de print manual.

---

## FEITO NESTA SESSÃO (2026-09-10)

### Commit `85fd382` — Títulos = menu; Anatomia sempre com todos os motivos
- **Títulos:** `st.title()` de cada tela passa a ser igual ao rótulo do menu
  (Painel / Motivos / Anatomia da perda / Evitável x estrutural / Regras e
  simulação). A "pergunta" antiga virou início da legenda.
- **Anatomia:** escopo "Motivos" abre em **Todos** (era Vencido). Bloco fixo
  **"Todos os motivos no recorte"** (não é mais expander) — tabela + barra do
  conjunto completo de motivos da loja/mês, **ignorando** o filtro de
  escopo/status. Coluna/cor "No escopo" marca o que entra na análise abaixo.
  Uma linha grande (ex. marketing R$ 10,5 mil) nunca some, mesmo analisando só
  vencido. `vfull = _vclass_recorte(_cats_do_escopo("todos"))`.

### Commit `f30429b` — Anatomia: motivo flexível + "ver tudo" (feedback do Gabriel)
Gabriel comparou o relatório do sistema (loja 16, ago, AÇÃO DE MARKETING → item
LANCETA ACCU CHECK R$ 10.029,36) e não achou o item na Anatomia. Causa: o filtro
**"Status no catálogo = Ativos"** escondia silenciosamente a linha — o produto
`LANCETA ACCU CHECK SAFE-T-PRO UNO CX C/ 200` **não casa** com o catálogo (que
tem `... UNO`, sem o `CX C/ 200`), então caiu em "fora do catálogo".
- Seletor de motivo: segmented **Vencido / Perda real / Todos** + multiselect
  **"…ou motivos específicos"** que sobrepõe. (`_cats_do_escopo`; `MOTIVO_OPCOES`
  saiu.)
- Novo expander **"Motivos no recorte"** — tabela R$/unid/linhas/produtos/% +
  barra por motivo.
- Tabela de produtos agrupa por **(produto, motivo)**, ganha coluna **Motivo**;
  head 300→500; CSV baixa tudo.
- **Avisos de linha escondida:** warning quando "Status no catálogo" ≠ Todos
  esconde R$; caption do R$ fora do filtro dos gráficos.
- **Fragilidade conhecida:** o join catálogo↔perda é por descrição exata
  normalizada; variações de embalagem no nome ("... UNO" vs "... UNO CX C/ 200")
  não casam → item vira "fora do catálogo". Cobertura ~99 %, mas linhas grandes
  podem cair fora. Se virar problema, casar por `Código` em vez de descrição.

### Commit `c5ecc70` — Anatomia: ajustes de leitura (feedback do Gabriel)
Cartão **"Total — <motivo>"** na linha de KPIs (R$ + unidades + linhas). Gráfico
"Tem curva?" → **"Curva"**, estratificado por letra **A…I** (+ "Sem cadastro")
em vez dos baldes A–D/E–G/H–I (`_cletra`/`ORD_LETRA` no lugar de `_cg`/`ORD_CURVA`;
filtro da tabela usa `cletra`). **Rótulo de valor em cada barra** dos 3 gráficos
(categoria, curva, tempo parado) via camada `mark_text`. Coluna "R$" da tabela →
"Total perda (R$)".

### Commit `9268722` — Catálogo BASE CADASTRO COM GRUPOS na Anatomia (item 0d)
`core.load_catalogo(sources)` lê a BASE CADASTRO COM GRUPOS (nível produto, sem
loja), chave = `Descrição` normalizada (`_norm_produto` = `_ascii`), dedup por
produto (Ativo vence Inativo), cache parquet próprio (`_cache_path(..., "catalogo")`).
`enriquecer_vencidos(..., catalogo=None)`: após o merge `(loja, produto)` com o
DADOS, merge extra por descrição normalizada + `_coalesce` de `classif` /
`curva_valor` / `curva_qtd` (DADOS tem prioridade). `sem_cadastro` continua sinal
do DADOS (fixado antes do coalesce). Novo `status_cadastro`. `_vclass` recebe
`cat_sig` + `_cat_df`; `CTX` expõe `catalogo`/`catsig`. `_catalogo` cache +
auto-find `*GRUPOS*.xlsx` + uploader. Anatomia: radio "Status no catálogo" +
coluna "Status catálogo". `BASE CADASTRO COM EAN.xlsx` não usado. Os 2 xlsx
saíram do versionamento (`.gitignore`).

### Commit `3c38334` — Anatomia com seletor de motivo (item 0c)
`_vclass(perdas_sig, cad_sig, cats, _perdas, _cad)` — `cats` entra na chave do
cache. `build_context` chama com `("vencido",)` p/ o `CTX["vclass"]` (Painel /
Evitável / Regras seguem só-vencido) e devolve `psig`/`csig`. Módulo:
`MOTIVO_OPCOES` (6 opções) + `_vclass_recorte(cats)` que roda o cache e reaplica
loja/mês do filtro global. `tela_anatomia`: selectbox "Motivo da baixa" ao lado
de mês/loja; Vencido reusa o CTX, os demais recalculam. Números: Vencido
219.827 / 146.589 / 22.039 · Perda real 224.232 / 162.558 / 23.367 · Todos
235.839 / 219.156 / 34.616 (medicamento / não-medic. / sem classificação).

### Commit `da48837` — Filtro de mês na tela em todas as telas
Helper `_mes_local(df, key, container=)` espelhando `_loja_local` (some quando o
recorte já tem ≤ 1 mês). **Evitável x estrutural** e **Regras e simulação**
ganham mês + loja na tela (antes: só loja / nada); `n_meses` recalculado do
recorte local. **Motivos** ganha "Meses (nesta tela)". **Painel** e **Anatomia**
passam a usar o helper. Agora todas as 5 telas têm mês + loja na própria tela,
além do filtro global da barra lateral.

### Commit `7fb754d` — Painel com filtro de mês/loja na tela
Feedback do Gabriel: o Painel também precisa de filtro e informações no recorte.
- Multiselect **"Meses (nesta tela)"** e **"Lojas (nesta tela)"** no topo do
  Painel (dentro do recorte global). `taxa_lm` / `mensal` / `cobertura` / `vclass`
  passam a ser recalculados a partir do recorte da tela — os 4 KPIs, o ranking de
  lojas, o bridge de escopo e o bloco "meses sem faturamento" respondem aos
  filtros. Conferido: mês = 2026-08 → fat 8.637.085 · perda 52.576 · taxa 0,61 % ·
  bridge 52.576 / 56.588 / 83.265 (bate com a decomposição de agosto abaixo).

### Commits `82fb613` + `e770596` — Seletores por tela + revisão da Anatomia
Feedback do Gabriel: além do filtro global, quer seletor de loja/mês nas telas.
- `82fb613`: helper `_loja_local(df, key)` — multiselect "Lojas (nesta tela)" em
  Motivos, Anatomia e Evitável x estrutural, restringe dentro do recorte global;
  some quando o recorte já tem ≤ 1 loja.
- `e770596` (Anatomia): filtro de **Meses (nesta tela)** ao lado do de Lojas
  (`_loja_local` aceita `container=`). Radios **Medida** (R$/Unidades) e **Curva**
  (Valor/Qtd) movidos para dentro dos containers dos gráficos. Cliques nos
  gráficos com `selection_point(toggle="true")` (re-clique solta) + botão
  **"Limpar filtros dos gráficos"** que reseta via nonce nas `key` dos charts.
  "Sem classificação" com rótulo próprio + aviso + opção "Só sem classificação"
  no seletor *Ver*. Tabela: coluna `lojas` (nunique) virou **Nº lojas** +
  **Lojas (ID)** (lista dos números); `itens` → "Unidades vencidas". Não há nome
  de loja no relatório de perdas, só número (2–25).
- (O clique-para-filtrar da Anatomia foi ajustado depois com `toggle="true"` +
  botão de limpar, e verificado no browser — ver seção CONCLUÍDO acima.)

### Commit `55eb5d6` — Veredito vira "Painel" (item 0b)
- `st.Page` renomeado Veredito → **Painel**. Topo com 4 KPIs: Faturamento no
  período · Perda no período (escopo) · Taxa ponderada (perda ÷ fat) · Gap vs
  meta em p.p. Diagnóstico (semáforo + frase) mantido; cai para
  `_cor_taxa(taxa_ponderada)` quando falta cadastro.
- Evolução mensal (taxa × meta) ao lado de **ranking de lojas por taxa** (barras
  no semáforo + régua da meta, vindo de `CTX["taxa_lm"]`).
- **Bridge de escopo** (vencido / perda real / todos — R$/mês + % fat) e **top
  motivos** (barra colorida por classe) reaproveitados da tela Motivos.
- "Meses sem faturamento" mantido; "Bater com o número da reunião" foi p/ um
  expander no rodapé. Helpers novos no topo: `CLASSE_COR`, `_cor_taxa(taxa, meta)`
  (mesma régua de `core.frase_diagnostico`); `CLASSE_COR` duplicado saiu de Motivos.
- Conferência sem filtro: fat R$ 69,69 M · taxa 0,53 % · bridge 0,55 / 0,58 /
  0,69 % — bate com a tabela do faturamento mensal.

### Commit `57f2dec` — Filtros globais de Loja e Período (item 0a)
- `build_context`: bloco "### Filtros" na sidebar com dois multiselect —
  **Lojas** e **Período (meses)**, vazio = tudo (`key="g_lojas"` / `"g_meses"`).
- O recorte é aplicado em `perdas`/`fat` **antes** dos derivados (`taxa_lm`,
  `mensal`, `cob`, `n_meses`) e no **resultado** do cache `_vclass` — o cross
  vencido×cadastro continua sendo calculado na base cheia (cache estável) e só
  depois filtrado por loja/mês.
- `CTX` agora expõe: `perdas` (já filtrado), `perdas_full` (base cheia, usada só
  pelo editor de faturamento), `fat` (filtrado), `lojas_sel`, `meses_sel`.
- `tela_motivos` e `tela_anatomia`: removidos os multiselect locais de Loja/Mês.
  `tela_motivos` ganhou guard para recorte sem lançamentos; `tela_baldes` e
  `tela_regras`, guard para `vclass` vazio.
- Helper `_recorte_txt()` + legenda "Recorte (filtro global): …" no topo das 5
  telas. Smoke test (`streamlit.testing`) nas 5 telas, com e sem filtro: 0 exc.

### Commit `45afa58` — Motivos c/ filtro de loja; Anatomia R$/unidades; meta 0,40%
- `tela_motivos`: multiselect de **Lojas** (vazio = todas), ao lado de Meses;
  filtra `perdas` e `fat` juntos p/ o % não distorcer.
- `tela_anatomia`: novo radio **"Medida dos gráficos"** (R$ vencido / Unidades)
  que rege o eixo x dos 3 gráficos; tooltip de todos passa a mostrar R$ **e**
  unidades sempre. Groupby dos 3 agora agrega `valor_total` **e** `itens`.
- **Meta de perdas: default do slider 0,50% → 0,40%** (definição do Gabriel,
  `app.py` `build_context`). É a meta oficial agora.

### Commit `46d77bf` — Anatomia: loja, curva e gráficos clicáveis
- `core.macro_categoria()` simplificada pela regra do Gabriel: no nível 1 da
  árvore, só GENÉRICO / SIMILAR / PROPAGADO é `medicamento`; qualquer outra
  categoria é `nao-medicamento`; sem categoria é `sem classificacao`. Sumiu o
  balde `indefinido` (CAMPANHA, HIGIENE PESSOAL/BUCAL, MUNDO HOMEM, PRIMEIROS
  SOCORROS caíram em não-medicamento). Efeito no vencido jan–set: medicamento
  R$ 219.827 · não-medicamento R$ 146.589 · sem classificação R$ 22.039.
  **A confirmar com o Gabriel:** os R$ 22 mil "sem classificação" são itens com
  `classif` em branco no cadastro — mantidos num balde à parte (não viraram
  não-medicamento). Se ele quiser, é 1 linha juntar.
- `tela_anatomia`: multiselect de **Lojas** (vazio = todas) ao lado de Meses;
  seletor de curva virou `st.radio` com `key` (o `segmented_control` não
  alternava) e agora rege o gráfico "Tem curva?"; os 3 gráficos (categoria /
  curva / tempo parado) viraram clicáveis via `alt.selection_point` +
  `st.altair_chart(on_select="rerun")` — clicar numa barra filtra a tabela de
  Produtos no rodapé, com título e legenda dizendo de qual gráfico e qual valor
  veio. Tabela ganhou coluna "Tempo parado" e download CSV.

### Commit `a787f5f` — tela "Motivos" (de-para de escopo)
Entregue conforme a spec que estava aqui. `core.py`: `classe_motivo(motivo_cat)`
+ `CLASSES_PERDA` (3 baldes: `Vencido` / `Outra perda real` / `Não é perda`,
coerente com `IS_PERDA_REAL` — só destaca o vencido). `app.py`: `tela_motivos()`,
2ª tela do `st.navigation` (ícone `category`).

- Filtro de meses (multiselect), default = meses com faturamento.
- 3 cartões de bridge de escopo (reusa `core.in_escopo`): Somente vencidos /
  Perda real / Todos os motivos — cada um com R$/mês + % do faturamento.
- Tabela por motivo: Motivo | Classe | R$ no período | R$/mês | % do faturamento
  | % do lançado | Linhas, ordenada por valor.
- Barra por motivo colorida pela classe + barra mensal empilhada por classe.
- % do faturamento usa só os meses da seleção que têm faturamento; meses sem
  faturamento entram no R$/mês e aparecem num aviso (`:material/info:`).
- Cálculo inline no `app.py` (não usa `core.perda_por_motivo`, que não entrega
  corte por mês nem % do faturamento).

Conferência jan–ago/2026 (todas as lojas, sem DEP): somente vencidos 0,55% ·
perda real 0,58% · todos os motivos 0,69% do faturamento acumulado. Para
reproduzir o 0,96% do BI de agosto, filtrar só `2026-08` no multiselect.

### Commit `5b681c3` — correções da revisão do app
- **`frase_diagnostico` (core.py):** agora usa a **meta do slider** para o semáforo
  (ok / atenção / crítico). Antes o parâmetro `meta` era ignorado e o nível vinha
  de uma faixa fixa 0,3–0,8%. Regra nova: `≤ meta+5%` → ok; `≤ meta+30%` → atenção;
  acima → crítico. A frase cita a meta **e** a faixa de mercado. Removido o
  parâmetro `escopo`, que não era usado.
- **Tela Veredito (app.py):** bloco novo "Meses sem faturamento informado" —
  gráfico de perda em R$ dos meses que têm baixa mas ainda não têm faturamento
  (jul+ sumiam sem aviso claro).
- **`load_perdas` (core.py):** cria `valor_unit` quando a coluna falta
  (evita `KeyError` em relatório sem coluna de valor unitário).
- **Editor de faturamento na sidebar:** `st.rerun()` ao salvar + aviso de que
  `faturamento.csv` na pasta **tem prioridade** sobre o valor digitado
  (era pegadinha: com o CSV presente, digitar/salvar não tinha efeito).
- **"Bater com o número da reunião":** protegida divisão por zero.
- **Limpeza:** removidos `BRLk` e a coluna `evitavel_pdv` (mortos).
- **`requirements.txt`:** `streamlit>=1.49` (era `>=1.40`; o app usa
  `container(horizontal=)`, `width="stretch"`, `metric(chart_data=)`).
- **`.gitignore`:** `_run.log`.

### `faturamento.csv` — reconstruído com valores MENSAIS reais (NÃO versionado)
Antes: jan–jun estavam **chapados pela média do trimestre** (T1/T2 do Power BI
"Visão geral - trimestre"). Agora: valor real de cada mês, **jan a ago/2026**,
fonte Power BI *Visão geral - mês* → Receita por Und. ID. Cada mês foi conferido
somando as 22 lojas contra o Total do relatório (maio fecha com 2 centavos de
diferença — arredondamento de leitura de print, irrelevante).

Taxa de perdas por mês (escopo "somente vencidos"), com o dado mensal real:

| Mês | Perda (vencidos) | Faturamento | Taxa |
|---|---:|---:|---:|
| 2026-01 | R$ 43.434 | R$ 8.830.034 | 0,49% |
| 2026-02 | R$ 43.533 | R$ 7.906.261 | 0,55% |
| 2026-03 | R$ 47.073 | R$ 8.903.328 | 0,53% |
| 2026-04 | R$ 45.320 | R$ 8.672.600 | 0,52% |
| 2026-05 | R$ 42.173 | R$ 8.890.939 | 0,47% |
| 2026-06 | R$ 44.716 | R$ 8.714.910 | 0,51% |
| 2026-07 | R$ 49.990 | R$ 9.139.575 | 0,55% |
| 2026-08 | R$ 52.576 | R$ 8.637.085 | 0,61% |

Média jan–ago: **0,53%**. Tendência de alta jun→jul→ago (0,51 → 0,55 → 0,61%).
Agosto é o pior mês da série.

### Por que a ferramenta mostra 0,61% e o Power BI mostra 0,96% (agosto)
Mesmo relatório, filtros diferentes. Decomposição de agosto (sem depósito):

| Motivo | Valor | % do fat | É perda? |
|---|---:|---:|:--:|
| Produto vencido | R$ 52.576 | 0,61% | sim |
| Ação de marketing | R$ 15.089 | 0,17% | não (troca/brinde) |
| Reembolso pelo fornecedor | R$ 6.529 | 0,08% | não (fornecedor paga de volta) |
| Doação / brinde | R$ 2.530 | 0,03% | não |
| Consumo da loja | R$ 1.945 | 0,02% | não |
| Danificado | R$ 1.755 | 0,02% | sim |
| Furto | R$ 1.653 | 0,02% | sim |
| Descontinuado | R$ 604 | 0,01% | sim |
| Devolução ao fornecedor | R$ 583 | 0,01% | não |
| **Todos os motivos** | **R$ 83.265** | **0,964% ≈ 0,96%** | |

- Somente vencidos: R$ 52.576 → **0,61%**
- Perda real (venc + danif + furto + descont): R$ 56.588 → 0,66%
- Todos os motivos: R$ 83.265 → **0,96%** (bate com o `%perda/fat` do Power BI)

O 0,96% do BI está inflado ~0,28 p.p. por marketing + reembolso + doação (~R$ 24 mil),
que não são perda. É essa separação que a tela "Motivos" (pendência 1) vai deixar
explícita. Hoje já dá para ver na barra lateral: **Parâmetros → Escopo →
"Todos os motivos"** faz a taxa de agosto virar 0,96%.

---

## Estado do app (fim da sessão 2026-09-12)
- **3 telas visíveis** via `st.navigation`: Painel · Anatomia da perda ·
  Itens a vencer. Ocultas (código intacto, comentado): Motivos, Evitável x
  estrutural, Regras e simulação.
- **Escopo de perda = "Todos os motivos" por padrão** (perda = toda baixa do
  sistema); Painel e Anatomia têm seletor próprio (Vencido / Perda direta /
  Todos os motivos) — nomes revisados pra não sugerir que um escopo é "mais
  real" que outro.
- **Filtros por tela:** `Meses`/`Lojas (nesta tela)` em todas; `Regional
  (nesta tela)` no Painel/Anatomia/Itens a vencer (2 supervisores, de
  `regionais.csv`); Escopo no Painel/Anatomia. Sem filtro global na sidebar
  (removido em 09-11) — só `Digitar faturamento` e (oculto) `Fontes de
  dados`.
- **Números em pt-BR** em todas as tabelas/tooltips/rótulos de gráfico
  (milhar `.`, decimal `,`) — só os eixos dos gráficos continuam no padrão
  americano (limitação do Vega-Lite/Streamlit).
- **Anatomia:** abre em "Todos os motivos"; bloco fixo "Todos os motivos no
  recorte" mostra a foto completa da loja/mês sempre; tabela é 1 linha por
  produto × motivo; clique num gráfico substitui a seleção anterior (não
  soma mais). Join catálogo por descrição exata — item com nome de
  embalagem diferente cai em "fora do catálogo".
- **Itens a vencer:** valor exposto usa **Saldo** do pré-vencido (não
  Estoque Atual, que é geral); urgência em 4 faixas cumulativas (Até
  30/90/180 dias / 12 meses).
- **Entradas** (todas auto-detectadas na pasta, uploader manual oculto):
  `perdas*.xls` (obrigatório) · `DADOS*.xlsx` (cadastro por loja) ·
  `BASE CADASTRO COM GRUPOS.xlsx` (catálogo) · `faturamento.csv` (jan–ago/2026)
  · `itens a vencer.xlsx` · `regionais.csv` (loja→regional). Todos exceto o
  catálogo e o código ficam fora do git (`.gitignore`) — dados sensíveis ou
  rotativos.
- Roda em `http://localhost:8501` (headless, `--server.fileWatcherType none` →
  mudança de código só entra com restart do servidor).
- Comando: `streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none`
- Python: `C:\Users\E.C Velanes\AppData\Local\Programs\Python\Python314\python.exe`
- Doc de uso e visão geral: `README.md`.
