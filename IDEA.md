# IDEA.md — TrigoBom Fiscal

## O problema

A gestão das notas fiscais emitidas pela Trigo Bom para o município, das ordens de compra recebidas e do saldo das licitações hoje é manual e fragmentada: as notas e ordens de compra chegam em PDF sem consolidação, não há visão rápida de quanto entrou e saiu por órgão, as ordens de compra não têm os itens organizados nem acompanhamento estruturado de prazos de entrega, o status de pagamento das NFs é controlado "de cabeça" ou em anotações dispersas, e o saldo de cada licitação (itens e valores ainda disponíveis) não tem nenhum controle estruturado.

O **TrigoBom Fiscal** resolve isso com um sistema que lê arquivos em PDF (NFs, ordens de compra e relações de itens de licitação), extrai as informações relevantes e oferece quatro telas principais: um dashboard de entradas e saídas a partir das NFs emitidas para o município, uma lista to-do/agenda de ordens de compra com os itens extraídos e as entregas pendentes, um painel de controle manual de NFs pagas vs. não pagas, e um controle de saldo de licitação por item.

## Objetivos principais

1. **Leitura e manipulação de arquivos/pastas**: o sistema deve conseguir ler pastas do usuário, identificar e abrir arquivos em PDF (NFs, ordens de compra, relações de itens de licitação), e gravar/atualizar arquivos (dados extraídos, status, organização) sem corromper os originais.
2. **Dashboard de entradas e saídas**: ler as NFs emitidas para o município e consolidar visualmente o que entrou e o que saiu (valores, datas), segmentado pelo **órgão** ao qual a nota se refere — Administração, Saúde, Educação ou Assistência Social. O órgão é escolhido pelo usuário no momento do upload da nota.
3. **Lista to-do / agenda de ordens de compra**: ler as ordens de compra, extrair os **itens e valores linha a linha** (não só os dados gerais da OC) e organizar em formato de lista de tarefas, com as datas de entrega agendadas, para acompanhar o que está pendente e o que já foi entregue. O sistema deve permitir **exportar essa lista de itens das ordens de compra para planilha**.
4. **Controle manual de pagamento de NFs**: organizar as NFs em "pagas" e "não pagas", com marcação feita manualmente pelo usuário (o sistema não concilia pagamentos automaticamente).
5. **Controle de saldo de licitação** (tela própria, independente das demais): o sistema recebe, em PDF, a relação de itens de uma licitação com seus valores. O usuário registra manualmente, ao longo do tempo, quais itens foram saindo (consumidos/entregues) e o valor correspondente. O sistema mantém o histórico dessas saídas e calcula o **saldo restante por item** (quantidade/valor disponível). Este controle é independente do controle de NFs — não há baixa automática entre os dois.

## Para quem

Empresas que prestam serviço/fornecem para o município e precisam organizar a emissão de notas fiscais por órgão, o acompanhamento de ordens de compra recebidas e o saldo das licitações que venceram, sem depender de um ERP completo. Especificamente:

- Quem hoje guarda NFs, ordens de compra e documentos de licitação em PDF e quer um painel que leia esses arquivos automaticamente.
- Quem precisa segmentar a visão financeira por órgão público (Administração, Saúde, Educação, Assistência Social).
- Quem precisa acompanhar prazos de entrega de ordens de compra como uma agenda/to-do, com os itens de cada OC organizados e exportáveis em planilha.
- Quem quer marcar manualmente o que já foi pago, sem integração bancária.
- Quem venceu uma licitação e precisa controlar, item a item, quanto do valor contratado ainda resta disponível.

## Anti-escopo (o que o projeto não deve fazer, por ora)

- Não faz conciliação bancária ou integração automática com banco/Open Finance — o status de pagamento é manual.
- Não substitui um ERP ou sistema contábil completo (sem emissão de NF, sem apuração de impostos).
- Não faz reconhecimento de pagamento automático a partir de extratos.
- Não vincula automaticamente NFs ao saldo de licitação — são dois controles separados, alimentados de forma independente pelo usuário.

## Decisões confirmadas com o usuário

- **Formato dos arquivos de entrada**: NFs, ordens de compra e relação de itens de licitação chegam todos em **PDF**.
- **Extração de dados**: **automática** — o sistema lê o conteúdo do PDF e extrai valores, datas, órgão/fornecedor e itens, sem digitação manual (exceto marcação de pago/não pago e registro de saídas da licitação, que são manuais por decisão de produto).
- **Exportação**: apenas a lista de itens das **ordens de compra** tem exportação em planilha, por ora. As demais telas (NFs por órgão, saldo de licitação) não têm exportação prevista neste momento.
- **Saldo de licitação**: controle por **item** (quantidade/valor restante por item), não apenas um total agregado — sujeito a validação com testes reais de uso.
- **Plataforma**: **app desktop local**, lendo e gravando diretamente nas pastas do computador do usuário.
- **Volume**: baixo (até ~30 NFs/ordens de compra por mês) — não há necessidade de otimizar para alto volume ou processamento em lote pesado.
