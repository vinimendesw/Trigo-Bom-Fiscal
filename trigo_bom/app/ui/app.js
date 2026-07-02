'use strict';

// ─── Estado global ────────────────────────────────────────────────────────────
const estado = {
  viewAtual:      'dashboard',
  mesAtual:       new Date(),
  nfs:            [],           // todas as NFs (cache)
  ocs:            [],           // OCs com itens aninhados (legado)
  listas:         [],           // listas de compra com OCs e itens agregados
  ocsSemLista:    [],           // OCs sem lista_id
  listaAtualId:   null,         // lista em que OCs estão sendo adicionadas
  listasAbertas:  new Set(),    // ids de listas com card expandido (preserva entre renders)
  ocsAbertas:     new Set(),    // ids de listas com a sub-lista de OCs expandida
  config:         {},
  // Detalhe NF
  nfAtual:        null,
  viewAnteriorNF: 'pagamentos',
  // Filtros NF
  filtros:        { orgao_id: '', status: '', mes: '' },
  // Marcação em massa
  selecionadas:   new Set(),
  // Formulário NF
  nfFormModo:     'pdf',
  nfFormCaminho:  null,
  nfFormItens:    [],
  nfFilaLote:     [],           // fila para lote PDF/XML
  nfFilaIdx:      0,
  // Formulário OC lote
  ocFilaLote:     [],
  ocFilaIdx:      0,
  // Exclusão de OC
  selecionadasOC: new Set(),
  ocExcluindoId:  null,
  // Exclusão de NF
  nfExcluindoId:  null,
  nfExcluindoIds: [],
  // Exclusão de lista
  listaExcluindoId: null,
  // Extração assíncrona (correlação request_id → callback)
  pendentesExtracao: {},
  reqSeq:          0,
  // Fila de revisão: PDFs detectados na pasta de entrada aguardando confirmação
  filaRevisao:     [],
  nfRevisaoCaminho: null,       // caminho do PDF sendo revisado (fluxo da fila)
};

const ORGAOS = { 1: 'Administração', 2: 'Saúde', 3: 'Educação', 4: 'Assistência Social' };
const CORES_ORGAO = { 1: '#c90914', 2: '#f2972c', 3: '#1a1a1a', 4: '#2e7d32' };
const MESES  = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                 'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

// ─── FAB contextual (Incluir NF / Incluir OC) ─────────────────────────────────
const ICONE_FAB_NF = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="12" x2="12" y2="18"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>';
const ICONE_FAB_OC = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1"></circle><circle cx="18" cy="20" r="1"></circle><path d="M3 4h2l2.4 12.4a2 2 0 0 0 2 1.6h7.2a2 2 0 0 0 2-1.6L21 8H6"></path><line x1="17" y1="2" x2="17" y2="6"></line><line x1="15" y1="4" x2="19" y2="4"></line></svg>';
const FAB_CONFIG = {
  pagamentos: { label: 'Incluir NF',  icone: ICONE_FAB_NF, acao: () => document.getElementById('btn-incluir-nf').click() },
  agenda:     { label: 'Nova lista',  icone: ICONE_FAB_OC, acao: () => document.getElementById('btn-nova-lista').click() },
};
function atualizarFab(view) {
  const fab = document.getElementById('fab-incluir');
  const cfg = FAB_CONFIG[view];
  if (cfg) {
    document.getElementById('fab-icon').innerHTML = cfg.icone;
    document.getElementById('fab-label').textContent = cfg.label;
    fab.style.display = 'flex';
  } else {
    fab.style.display = 'none';
  }
}

// ─── Utilitários ──────────────────────────────────────────────────────────────
// Escapa texto vindo de extração de PDF/XML ou do banco antes de interpolá-lo em
// template strings que viram innerHTML. Sem isso, uma descrição de item ou nome
// de fornecedor contendo <, > , & ou aspas quebra a renderização (ou injeta
// marcação). Não usar em valores numéricos já formatados por fmtBRL.
function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function fmtBRL(v) {
  if (v == null || isNaN(v)) return '—';
  return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function parseBRL(s) {
  if (!s) return null;
  s = String(s).replace(/[^\d,\.]/g, '');
  if (/\d\.\d{3},\d/.test(s)) s = s.replace(/\./g, '').replace(',', '.');
  else s = s.replace(',', '.');
  const v = parseFloat(s);
  return isNaN(v) ? null : v;
}
// Máscara de moeda "dígitos como centavos": cada dígito digitado empurra os
// anteriores, formatando com separador de milhar "." e decimal ",".
// Ex.: digitar "125000" resulta em "1.250,00". Formata o próprio campo no evento
// `input`; o valor final salvo continua saindo por parseBRL() (float), então a
// máscara é apenas de apresentação e compatível com o fluxo existente.
function mascararMoeda(el) {
  const digitos = el.value.replace(/\D/g, '');
  if (!digitos) { el.value = ''; return; }
  const centavos = parseInt(digitos, 10);
  el.value = (centavos / 100).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}
// Formata um float já existente (edição/pré-preenchimento) no mesmo padrão da
// máscara, para o campo exibir o valor já formatado ao ser carregado.
function moedaParaMascara(v) {
  if (v == null || isNaN(v)) return '';
  return Number(v).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}
function fmtData(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}
function isoHoje() { return new Date().toISOString().split('T')[0]; }
function diasAte(iso) {
  if (!iso) return null;
  return Math.round((new Date(iso + 'T00:00:00') - new Date(isoHoje() + 'T00:00:00')) / 86400000);
}
function mostrarToast(msg, erro = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (erro ? ' erro' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = 'toast'; }, 3000);
}

// Estado "lendo" durante a extração assíncrona (a janela não congela mais, então
// é preciso sinalizar visualmente que há trabalho em andamento).
function _desabilitar(ids, desabilitar) {
  ids.forEach(id => { const b = document.getElementById(id); if (b) b.disabled = desabilitar; });
}
function mostrarLendoOC(lendo) {
  document.getElementById('oc-lendo').style.display = lendo ? 'flex' : 'none';
  const card = document.getElementById('oc-confirmacao-card');
  if (card) card.style.display = lendo ? 'none' : '';
  _desabilitar(['btn-salvar-oc', 'btn-pular-oc'], lendo);
}
function mostrarLendoNF(lendo) {
  document.getElementById('nf-lendo').style.display = lendo ? 'flex' : 'none';
  if (lendo) {
    // Esconde upload, formulário e abas de modo enquanto a leitura roda; o
    // formulário reaparece quando o resultado da extração chega.
    document.getElementById('nf-sec-arquivo').style.display = 'none';
    document.getElementById('nf-form-dados').style.display  = 'none';
    document.getElementById('nf-modo-wrap').style.display   = 'none';
  }
  _desabilitar(['btn-salvar-nf', 'btn-pular-nf', 'btn-cancelar-nf2'], lendo);
}

// ─── Navegação ────────────────────────────────────────────────────────────────
function navegarPara(view, navKey) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + view).classList.add('active');
  if (navKey) {
    document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));
    const link = document.querySelector(`.nav-link[data-view="${navKey}"]`);
    if (link) link.classList.add('active');
  }
  document.querySelector('.shell').scrollTop = 0;
  estado.viewAtual = view;
  atualizarFab(view);
}

// ─── Inicialização ────────────────────────────────────────────────────────────
new QWebChannel(qt.webChannelTransport, channel => {
  window.backend = channel.objects.backend;
  iniciar();
});

function iniciar() {
  atualizarHora();
  setInterval(atualizarHora, 60000);
  // Resultado da extração assíncrona volta por sinal Qt, correlacionado por id.
  backend.extracaoConcluida.connect((requestId, json) => {
    const cb = estado.pendentesExtracao[requestId];
    if (cb) { delete estado.pendentesExtracao[requestId]; cb(json); }
  });
  // Fila de revisão (pasta de entrada) mudou no backend → recarrega e re-renderiza.
  backend.filaRevisaoAtualizada.connect(() => carregarFilaRevisao());
  // Checagem/instalação de atualização (disparada pelo main.py ao abrir, ou
  // pelo botão manual em Configurações) — status chega por este sinal.
  backend.atualizacaoStatus.connect(tratarStatusAtualizacao);
  vincularEventos();
  carregarTudo();
}

// Dispara a extração (PDF/XML) fora da thread da GUI; `callback(jsonString)` é
// chamado quando o backend devolve o resultado pelo sinal extracaoConcluida.
function extrairAsync(metodo, caminho, callback) {
  const reqId = 'req-' + (++estado.reqSeq);
  estado.pendentesExtracao[reqId] = callback;
  backend[metodo](reqId, caminho);
}
function atualizarHora() {
  const ag = new Date();
  document.getElementById('sidebar-hora').textContent =
    'Atualizado ' + ag.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function carregarTudo() {
  backend.listar_nfs(raw => { estado.nfs = JSON.parse(raw); renderDashboard(); renderNFs(); });
  backend.listar_listas_com_ocs(raw => {
    estado.listas = JSON.parse(raw);
    backend.listar_ocs_sem_lista(raw2 => {
      estado.ocsSemLista = JSON.parse(raw2);
      renderListaCompras();
    });
  });
  backend.carregar_config(raw => { estado.config = JSON.parse(raw); renderConfiguracoes(); });
  carregarFilaRevisao();
}

// ─── Fila de revisão (pasta de entrada monitorada) ─────────────────────────────
function carregarFilaRevisao() {
  backend.listar_fila_revisao(raw => {
    estado.filaRevisao = JSON.parse(raw);
    renderFilaRevisao();
  });
}

function renderFilaRevisao() {
  const bar   = document.getElementById('revisao-bar');
  const lista = document.getElementById('revisao-lista');
  const cont  = document.getElementById('revisao-contagem');
  const itens = estado.filaRevisao || [];
  if (!itens.length) { bar.style.display = 'none'; lista.innerHTML = ''; return; }
  bar.style.display = '';
  cont.textContent = itens.length;
  lista.innerHTML = itens.map(item => {
    const d = item.dados || {};
    const preview = d._erro
      ? `<div class="preview erro">Falha na leitura: ${escapeHtml(d._erro)}</div>`
      : `<div class="preview">NF ${escapeHtml(d.numero) || '—'} · ${d.valor != null ? fmtBRL(d.valor) : 'valor —'} · ${d.data_emissao ? fmtData(d.data_emissao) : 'data —'}</div>`;
    const cam = escapeHtml(item.caminho);
    return `<div class="revisao-item">
      <div class="info">
        <div class="nome">${escapeHtml(item.nome)}</div>
        ${preview}
      </div>
      <div class="acoes">
        <button class="btn-acao btn-revisar" data-caminho="${cam}">Revisar</button>
        <button class="btn-acao btn-descartar" data-caminho="${cam}">Descartar</button>
      </div>
    </div>`;
  }).join('');

  lista.querySelectorAll('.btn-revisar[data-caminho]').forEach(btn =>
    btn.addEventListener('click', () => revisarNFDetectada(btn.dataset.caminho)));
  lista.querySelectorAll('.btn-descartar[data-caminho]').forEach(btn =>
    btn.addEventListener('click', () => descartarNFDetectada(btn.dataset.caminho)));
}

// Abre o formulário de inclusão de NF pré-preenchido com os dados extraídos do
// PDF detectado, para conferência/correção antes de confirmar. O PDF já está
// dentro da pasta_nfs; salvar reaproveita salvar_nf (origem 'pdf' → _copiar_pdf
// não regrava porque dest == src, evitando novo evento no watcher).
function revisarNFDetectada(caminho) {
  const item = (estado.filaRevisao || []).find(i => i.caminho === caminho);
  if (!item) return;
  const d = item.dados || {};

  estado.viewAnteriorNF   = 'pagamentos';
  resetarFormNF();
  estado.nfFormModo       = 'pdf';
  estado.nfFormCaminho    = caminho;
  estado.nfRevisaoCaminho = caminho;
  estado.nfFilaLote       = [];
  estado.nfFilaIdx        = 0;

  // Preenche os campos com o que foi extraído.
  document.getElementById('nf-numero').value       = d.numero || '';
  document.getElementById('nf-data-emissao').value = d.data_emissao || '';
  document.getElementById('nf-valor').value        = d.valor != null ? moedaParaMascara(d.valor) : '';
  document.querySelectorAll('#nf-orgao-tags .tag').forEach(t => t.classList.remove('selected'));
  if (d.orgao_id) {
    const tag = document.querySelector(`#nf-orgao-tags .tag[data-val="${d.orgao_id}"]`);
    if (tag) tag.classList.add('selected');
  }

  // Verificação de duplicidade por número (2.6): alerta, não bloqueia.
  // Consulta o banco diretamente (não depende da lista em memória estado.nfs),
  // então o aviso é atualizado de forma assíncrona quando a resposta chega.
  const aviso = document.getElementById('nf-dup-aviso');
  aviso.style.display = 'none';
  if (d.numero) {
    backend.numero_nf_existe(String(d.numero), raw => {
      aviso.style.display = JSON.parse(raw).existe ? '' : 'none';
    });
  }

  // Mostra o formulário de confirmação como no fluxo de extração de PDF.
  document.getElementById('nf-conf-titulo').textContent  = 'Revisar nota detectada';
  document.getElementById('nf-sec-arquivo').style.display = 'none';
  document.getElementById('nf-form-dados').style.display  = '';
  document.getElementById('nf-modo-wrap').style.display   = 'none';
  document.getElementById('nf-lote-progress').style.display = 'none';
  document.getElementById('btn-pular-nf').style.display   = 'none';
  navegarPara('incluir-nf', 'pagamentos');
}

function descartarNFDetectada(caminho) {
  backend.descartar_revisao(caminho, () => {
    mostrarToast('Nota dispensada da revisão.');
    // A fila é recarregada pelo sinal filaRevisaoAtualizada emitido no backend.
  });
}

function recarregarListas(cb) {
  backend.listar_listas_com_ocs(raw => {
    estado.listas = JSON.parse(raw);
    backend.listar_ocs_sem_lista(raw2 => {
      estado.ocsSemLista = JSON.parse(raw2);
      renderListaCompras();
      if (cb) cb();
    });
  });
}

// ─── Vínculos ─────────────────────────────────────────────────────────────────
function vincularEventos() {
  // Sidebar
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => navegarPara(link.dataset.view, link.dataset.view));
  });

  // FAB contextual
  document.getElementById('fab-incluir').addEventListener('click', () => {
    const cfg = FAB_CONFIG[estado.viewAtual];
    if (cfg) cfg.acao();
  });
  document.addEventListener('click', e => {
    const el = e.target.closest('.link-action[data-view]');
    if (el) navegarPara(el.dataset.view, el.dataset.view);
  });

  // Dashboard: mês
  document.getElementById('mes-ant').addEventListener('click', () => {
    estado.mesAtual = new Date(estado.mesAtual.getFullYear(), estado.mesAtual.getMonth() - 1, 1);
    renderDashboard();
  });
  document.getElementById('mes-prox').addEventListener('click', () => {
    estado.mesAtual = new Date(estado.mesAtual.getFullYear(), estado.mesAtual.getMonth() + 1, 1);
    renderDashboard();
  });

  // Lista de compras
  document.getElementById('btn-nova-lista').addEventListener('click', () => {
    document.getElementById('nova-lista-data').value = '';
    document.getElementById('modal-nova-lista').style.display = 'flex';
  });
  document.getElementById('modal-nova-lista-fechar').addEventListener('click', () => document.getElementById('modal-nova-lista').style.display = 'none');
  document.getElementById('modal-nova-lista-cancelar').addEventListener('click', () => document.getElementById('modal-nova-lista').style.display = 'none');
  document.getElementById('modal-nova-lista-confirmar').addEventListener('click', criarLista);
  document.getElementById('modal-nova-lista').addEventListener('click', e => {
    if (e.target === e.currentTarget) document.getElementById('modal-nova-lista').style.display = 'none';
  });

  document.getElementById('modal-excluir-lista-fechar').addEventListener('click', fecharModalExcluirLista);
  document.getElementById('modal-excluir-lista-cancelar').addEventListener('click', fecharModalExcluirLista);
  document.getElementById('modal-excluir-lista-confirmar').addEventListener('click', confirmarExcluirLista);
  document.getElementById('modal-excluir-lista').addEventListener('click', e => {
    if (e.target === e.currentTarget) fecharModalExcluirLista();
  });

  // OC — form de inclusão
  document.getElementById('btn-cancelar-oc').addEventListener('click', () => navegarPara('agenda', 'agenda'));
  document.getElementById('oc-upload-zone').addEventListener('click', () => abrirPDFsOC());
  document.getElementById('btn-salvar-oc').addEventListener('click', salvarOCAtual);
  document.getElementById('btn-pular-oc').addEventListener('click', avancarOCLote);

  // Notas Fiscais
  document.getElementById('btn-incluir-nf').addEventListener('click', () => {
    estado.viewAnteriorNF = 'pagamentos';
    resetarFormNF();
    navegarPara('incluir-nf', 'pagamentos');
  });
  document.getElementById('btn-cancelar-nf').addEventListener('click', () => navegarPara(estado.viewAnteriorNF, estado.viewAnteriorNF));
  document.getElementById('btn-cancelar-nf2').addEventListener('click', () => navegarPara(estado.viewAnteriorNF, estado.viewAnteriorNF));

  // Filtros NF
  ['filtro-orgao','filtro-status','filtro-mes'].forEach(id => {
    document.getElementById(id).addEventListener('change', aplicarFiltros);
  });
  document.getElementById('btn-limpar-filtros').addEventListener('click', limparFiltros);
  document.getElementById('btn-toggle-filtros').addEventListener('click', () => {
    const painel = document.getElementById('filtros-painel');
    painel.style.display = painel.style.display !== 'none' ? 'none' : 'flex';
  });

  // Checkbox "selecionar todas" — ajusta os checkboxes existentes e a barra,
  // sem reconstruir os cards (evita os mesmos artefatos do toggle individual).
  document.getElementById('check-todos-np').addEventListener('change', e => {
    const nfsVisiveis = nfsFiltradas().filter(nf => nf.status_pagamento !== 'pago');
    if (e.target.checked) {
      nfsVisiveis.forEach(nf => estado.selecionadas.add(nf.id));
    } else {
      estado.selecionadas.clear();
    }
    document.querySelectorAll('.nf-checkbox').forEach(cb => {
      cb.checked = estado.selecionadas.has(parseInt(cb.dataset.nfId));
    });
    atualizarBarraMassa();
  });

  // Marcação em massa
  document.getElementById('btn-marcar-massa').addEventListener('click', () => {
    document.getElementById('massa-data').value = isoHoje();
    document.getElementById('modal-massa-titulo').textContent =
      `Marcar ${estado.selecionadas.size} NF${estado.selecionadas.size > 1 ? 's' : ''} como pagas`;
    document.getElementById('modal-massa').style.display = 'flex';
  });
  document.getElementById('btn-cancelar-massa').addEventListener('click', () => {
    estado.selecionadas.clear();
    document.querySelectorAll('.nf-checkbox').forEach(cb => cb.checked = false);
    const todos = document.getElementById('check-todos-np');
    if (todos) todos.checked = false;
    atualizarBarraMassa();
  });
  document.getElementById('modal-massa-fechar').addEventListener('click', () => document.getElementById('modal-massa').style.display = 'none');
  document.getElementById('modal-massa-cancelar').addEventListener('click', () => document.getElementById('modal-massa').style.display = 'none');
  document.getElementById('modal-massa-confirmar').addEventListener('click', confirmarMassa);
  document.getElementById('modal-massa').addEventListener('click', e => {
    if (e.target === e.currentTarget) document.getElementById('modal-massa').style.display = 'none';
  });

  // Modal excluir OC (individual — ainda usado via botão no card de OC dentro da lista)
  document.getElementById('modal-excluir-oc-fechar').addEventListener('click', fecharModalExcluirOC);
  document.getElementById('modal-excluir-oc-cancelar').addEventListener('click', fecharModalExcluirOC);
  document.getElementById('modal-excluir-oc-confirmar').addEventListener('click', confirmarExcluirOC);
  document.getElementById('modal-excluir-oc').addEventListener('click', e => {
    if (e.target === e.currentTarget) fecharModalExcluirOC();
  });

  // Exclusão de NF — barra de massa e modal
  document.getElementById('btn-excluir-massa-nf').addEventListener('click', () => {
    abrirModalExcluirNF(null, [...estado.selecionadas]);
  });
  document.getElementById('modal-excluir-nf-fechar').addEventListener('click', fecharModalExcluirNF);
  document.getElementById('modal-excluir-nf-cancelar').addEventListener('click', fecharModalExcluirNF);
  document.getElementById('modal-excluir-nf-confirmar').addEventListener('click', confirmarExcluirNF);
  document.getElementById('modal-excluir-nf').addEventListener('click', e => {
    if (e.target === e.currentTarget) fecharModalExcluirNF();
  });

  // Modal pagamento simples
  document.getElementById('modal-pag-fechar').addEventListener('click', fecharModalPagamento);
  document.getElementById('modal-pag-cancelar').addEventListener('click', fecharModalPagamento);
  document.getElementById('modal-pag-confirmar').addEventListener('click', confirmarPagamento);
  document.getElementById('modal-pagamento').addEventListener('click', e => {
    if (e.target === e.currentTarget) fecharModalPagamento();
  });

  // Detalhe NF
  document.getElementById('btn-voltar-nf-det').addEventListener('click', () => navegarPara(estado.viewAnteriorNF, estado.viewAnteriorNF));
  document.getElementById('btn-marcar-pago-det').addEventListener('click', () => {
    if (estado.nfAtual) abrirModalPagamento(estado.nfAtual.id);
  });

  // Form NF: modo tabs
  document.getElementById('nf-modo-tabs').addEventListener('click', e => {
    const tab = e.target.closest('.modo-tab');
    if (!tab) return;
    document.querySelectorAll('.modo-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    mudarModoNF(tab.dataset.modo);
  });
  document.getElementById('nf-upload-zone').addEventListener('click', () => {
    if (estado.nfFormModo === 'pdf') abrirPDFsNF();
    else if (estado.nfFormModo === 'xml') abrirXMLsNF();
  });
  document.getElementById('toggle-pago').addEventListener('click', () => {
    document.getElementById('toggle-pago').classList.add('checked');
    document.getElementById('toggle-nao-pago').classList.remove('checked');
    document.getElementById('field-data-pagamento').style.display = '';
  });
  document.getElementById('toggle-nao-pago').addEventListener('click', () => {
    document.getElementById('toggle-nao-pago').classList.add('checked');
    document.getElementById('toggle-pago').classList.remove('checked');
    document.getElementById('field-data-pagamento').style.display = 'none';
  });
  // Máscara de moeda no campo de valor da NF (formata durante a digitação).
  document.getElementById('nf-valor').addEventListener('input', e => mascararMoeda(e.target));
  vincularTagsUnicas('nf-orgao-tags');
  // #nf-categoria-tags removido do HTML (2026-06-29) — sem vínculo aqui.
  document.getElementById('btn-salvar-nf').addEventListener('click', salvarNFAtual);
  document.getElementById('btn-pular-nf').addEventListener('click', avancarNFLote);
  // #btn-add-item-nf removido do HTML (2026-06-29) — sem vínculo aqui.

  // Configurações
  document.querySelectorAll('.btn-escolher-pasta').forEach(btn => {
    btn.addEventListener('click', () => {
      backend.abrir_dialogo_pasta(`Selecionar pasta`, caminho => {
        if (!caminho) return;
        document.getElementById(btn.dataset.input).value = caminho;
        estado.config[btn.dataset.cfg] = caminho;
      });
    });
  });
  document.getElementById('btn-salvar-config').addEventListener('click', () => {
    backend.salvar_config(JSON.stringify(estado.config), () => mostrarToast('Configurações salvas.'));
  });
  document.getElementById('btn-verificar-atualizacao').addEventListener('click', () => {
    backend.verificar_atualizacao();
  });
}

function vincularTagsUnicas(id) {
  document.getElementById(id).addEventListener('click', e => {
    const tag = e.target.closest('.tag');
    if (!tag) return;
    document.querySelectorAll(`#${id} .tag`).forEach(t => t.classList.remove('selected'));
    tag.classList.add('selected');
  });
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
function renderDashboard() {
  const ano = estado.mesAtual.getFullYear();
  const mes = estado.mesAtual.getMonth();

  document.getElementById('mes-label').textContent = `${MESES[mes]} ${ano}`;

  // Pills dos últimos 4 meses
  const pills = document.getElementById('month-pills');
  pills.innerHTML = '';
  for (let i = 3; i >= 0; i--) {
    const d = new Date(ano, mes - i, 1);
    const pill = document.createElement('span');
    pill.className = 'month-pill' + (i === 0 ? ' active' : '');
    pill.textContent = MESES[d.getMonth()].slice(0, 3);
    const capD = new Date(d);
    pill.addEventListener('click', () => { estado.mesAtual = capD; renderDashboard(); });
    pills.appendChild(pill);
  }

  // nfsMes: NFs emitidas no mês — base do KPI "Entradas" e da tabela do dashboard
  const nfsMes = estado.nfs.filter(nf => {
    if (!nf.data_emissao) return false;
    const [y, m] = nf.data_emissao.split('-').map(Number);
    return y === ano && m === mes + 1;
  });

  // nfsRecebidasMes: NFs pagas no mês (por data_pagamento) — base do KPI "Recebido"
  // e do gráfico de pizza. Mistura intencional de bases (regime de caixa para "recebido").
  const nfsRecebidasMes = estado.nfs.filter(nf => {
    if (!nf.data_pagamento) return false;
    const [y, m] = nf.data_pagamento.split('-').map(Number);
    return y === ano && m === mes + 1;
  });

  const entradas  = nfsMes.reduce((s, nf) => s + (nf.valor || 0), 0);
  const recebido  = nfsRecebidasMes.reduce((s, nf) => s + (nf.valor || 0), 0);
  // "A receber": NFs da mesma competência (nfsMes, por data_emissao) ainda não pagas.
  // Não usar nfsRecebidasMes aqui — bases de tempo diferentes tornariam o saldo negativo
  // quando uma NF é emitida em um mês e paga no seguinte.
  const aReceber  = nfsMes.filter(nf => nf.status_pagamento !== 'pago').reduce((s, nf) => s + (nf.valor || 0), 0);
  const pendentes = nfsMes.filter(nf => nf.status_pagamento !== 'pago').length;

  document.getElementById('kpi-entradas').textContent = fmtBRL(entradas);
  document.getElementById('kpi-recebido').textContent = fmtBRL(recebido);
  document.getElementById('kpi-saldo').textContent    = fmtBRL(aReceber);
  document.getElementById('dash-badge').textContent   = pendentes > 0
    ? `${pendentes} NF${pendentes > 1 ? 's' : ''} pendente${pendentes > 1 ? 's' : ''}`
    : 'Tudo em dia';

  // Faturado (emissão) x Recebido (pagamento) por órgão, ambos no mês selecionado
  renderBarsOrgao(nfsMes, nfsRecebidasMes);

  // Status
  const pagas = nfsMes.filter(nf => nf.status_pagamento === 'pago').length;
  const total  = nfsMes.length || 1;
  document.getElementById('dash-status').innerHTML = `
    <div class="breakdown-item">
      <div class="top"><span>Pagas</span><span class="num">${pagas}</span></div>
      <div class="breakdown-bar"><div class="fill" style="width:${(pagas/total*100).toFixed(1)}%;background:#1a1a1a;"></div></div>
    </div>
    <div class="breakdown-item">
      <div class="top"><span>Não pagas</span><span class="num">${nfsMes.length - pagas}</span></div>
      <div class="breakdown-bar"><div class="fill" style="width:${((nfsMes.length-pagas)/total*100).toFixed(1)}%;background:#c90914;"></div></div>
    </div>`;

  // Tabela
  const tbody = document.getElementById('dash-tabela');
  const empty = document.getElementById('dash-empty');
  if (!nfsMes.length) { tbody.innerHTML = ''; empty.style.display = ''; }
  else {
    empty.style.display = 'none';
    tbody.innerHTML = nfsMes.slice(0, 10).map(nf => `
      <tr style="cursor:pointer;" data-nf-id="${nf.id}">
        <td>NF ${escapeHtml(nf.numero) || '—'}</td>
        <td>${escapeHtml(nf.orgao_nome) || '—'}</td>
        <td>${fmtData(nf.data_emissao)}</td>
        <td>${fmtBRL(nf.valor)}</td>
        <td><span class="status-pill ${nf.status_pagamento === 'pago' ? 'pago' : 'nao-pago'}">${nf.status_pagamento === 'pago' ? 'pago' : 'não pago'}</span></td>
      </tr>`).join('');
    tbody.querySelectorAll('tr[data-nf-id]').forEach(tr => {
      tr.addEventListener('click', () => abrirDetalheNF(parseInt(tr.dataset.nfId), 'dashboard'));
    });
  }
}

function renderBarsOrgao(nfsFaturadoMes, nfsRecebidoMes) {
  // Agrega faturado (emissão) e recebido (pagamento) por órgão, a partir do cache local.
  const faturado = { 1: 0, 2: 0, 3: 0, 4: 0 };
  const recebido  = { 1: 0, 2: 0, 3: 0, 4: 0 };
  nfsFaturadoMes.forEach(nf => { if (nf.orgao_id) faturado[nf.orgao_id] = (faturado[nf.orgao_id] || 0) + (nf.valor || 0); });
  nfsRecebidoMes.forEach(nf => { if (nf.orgao_id) recebido[nf.orgao_id]  = (recebido[nf.orgao_id] || 0) + (nf.valor || 0); });

  const container = document.getElementById('dash-orgao-bars');
  const maxValor = Math.max(...Object.keys(ORGAOS).map(id => Math.max(faturado[id] || 0, recebido[id] || 0)), 0);

  if (maxValor === 0) {
    container.innerHTML = '<div class="orgao-bars-empty">Sem notas neste mês.</div>';
    return;
  }

  const ALTURA_MAX = 116; // px, deve casar com .orgao-bar-pair { height }
  container.innerHTML = Object.keys(ORGAOS).map(id => {
    const fVal = faturado[id] || 0;
    const rVal = recebido[id]  || 0;
    const fAlt = Math.max(fVal > 0 ? (fVal / maxValor) * ALTURA_MAX : 0, fVal > 0 ? 2 : 0);
    const rAlt = Math.max(rVal > 0 ? (rVal / maxValor) * ALTURA_MAX : 0, rVal > 0 ? 2 : 0);
    return `
      <div class="orgao-bar-group">
        <div class="orgao-bar-pair">
          <div class="orgao-bar faturado" style="height:${fAlt.toFixed(1)}px;" title="Faturado: ${fmtBRL(fVal)}"></div>
          <div class="orgao-bar recebido" style="height:${rAlt.toFixed(1)}px;" title="Recebido: ${fmtBRL(rVal)}"></div>
        </div>
        <div class="orgao-bar-label">${ORGAOS[id]}</div>
      </div>`;
  }).join('');
}

// ─── LISTA DE COMPRAS — renderização principal ────────────────────────────────
const PILL_CLS = { pendente: 'pendente', atrasada: 'atrasada', entregue: 'entregue' };

function renderListaCompras() {
  const container = document.getElementById('container-listas');
  const empty     = document.getElementById('agenda-empty');
  const semLista  = document.getElementById('secao-sem-lista');

  const totalListas = estado.listas.length;
  const totalAvulas = estado.ocsSemLista.length;

  document.getElementById('agenda-badge').textContent = totalListas
    ? `${totalListas} lista${totalListas > 1 ? 's' : ''}` : 'Nenhuma lista';
  empty.style.display = totalListas === 0 ? '' : 'none';

  // Descarta de listasAbertas/ocsAbertas ids que não existem mais
  const idsValidos = new Set(estado.listas.map(l => l.id));
  estado.listasAbertas.forEach(id => { if (!idsValidos.has(id)) estado.listasAbertas.delete(id); });
  estado.ocsAbertas.forEach(id => { if (!idsValidos.has(id)) estado.ocsAbertas.delete(id); });

  container.innerHTML = estado.listas.map(_htmlCardLista).join('');
  _vincularEventosListas(container);

  // ── Seção "Sem lista" ─────────────────────────────────────────────────────
  semLista.style.display = totalAvulas > 0 ? '' : 'none';
  if (totalAvulas > 0) {
    const avulsas = document.getElementById('lista-ocs-avulsas');
    avulsas.innerHTML = estado.ocsSemLista.map(oc => _htmlOCInterna(oc)).join('');
    avulsas.querySelectorAll('.btn-excluir-oc').forEach(btn => {
      btn.addEventListener('click', () => abrirModalExcluirOC(parseInt(btn.dataset.ocId), null));
    });
  }
}

function _htmlCardLista(lista) {
  const status    = lista.status_entrega || 'pendente';
  const pillCls   = PILL_CLS[status] || 'pendente';
  const dataLabel = lista.data_prevista ? 'Entrega: ' + fmtData(lista.data_prevista) : 'Sem prazo';
  const abertaCard = estado.listasAbertas.has(lista.id);
  const abertaOcs  = estado.ocsAbertas.has(lista.id);

  const agregadosHTML = lista.itens_agregados && lista.itens_agregados.length
    ? `<table>
         <thead><tr><th>Descrição</th><th>UN</th><th>Qtd</th><th>Valor Unit.</th><th>Total</th></tr></thead>
         <tbody>${lista.itens_agregados.map(it => `
           <tr>
             <td>${escapeHtml(it.descricao) || '—'}</td>
             <td>${escapeHtml(it.unidade)}</td>
             <td>${it.quantidade != null ? Number(it.quantidade).toLocaleString('pt-BR') : '—'}</td>
             <td>${fmtBRL(it.valor_unitario)}</td>
             <td>${fmtBRL(it.valor_total)}</td>
           </tr>`).join('')}
         </tbody>
       </table>`
    : '<div class="oc-sem-itens">Nenhum item ainda. Inclua OCs nesta lista.</div>';

  const ocsHTML = lista.ocs && lista.ocs.length
    ? lista.ocs.map(oc => _htmlOCInterna(oc)).join('')
    : '<div class="oc-sem-itens" style="padding:8px 0;">Nenhuma OC incluída.</div>';

  const nOcs   = lista.ocs ? lista.ocs.length : 0;
  const nItens = lista.itens_agregados ? lista.itens_agregados.length : 0;
  const resumo = `${nOcs} OC${nOcs !== 1 ? 's' : ''} · ${nItens} tipo${nItens !== 1 ? 's' : ''} de item`;

  return `<div class="lista-card" data-lista-id="${lista.id}">
    <div class="lista-card-header">
      <div class="lista-card-toggle-area" data-lista-id="${lista.id}">
        <span class="lista-card-chevron${abertaCard ? ' aberto' : ''}">▶</span>
        <div>
          <div class="lista-card-nome">${escapeHtml(lista.nome)}</div>
          <div class="lista-card-data">${dataLabel} &nbsp;·&nbsp; ${resumo}</div>
        </div>
      </div>
      <div class="lista-card-actions">
        <span class="status-pill ${pillCls}" data-pill-lista="${lista.id}">${status}</span>
        <select class="lista-status-select" data-lista-id="${lista.id}">
          <option value="pendente"${status==='pendente'?' selected':''}>Pendente</option>
          <option value="atrasada"${status==='atrasada'?' selected':''}>Atrasada</option>
          <option value="entregue"${status==='entregue'?' selected':''}>Entregue</option>
        </select>
        <button class="btn-incluir-ocs" data-lista-id="${lista.id}">+ Incluir OCs</button>
        <button class="btn-export-lista" data-lista-id="${lista.id}">↓ Exportar xlsx</button>
        <button class="btn-excluir-lista" data-lista-id="${lista.id}">Excluir lista</button>
      </div>
    </div>

    <div class="lista-card-body${abertaCard ? ' aberto' : ''}" id="lista-body-${lista.id}">
      <div class="lista-secao lista-agregados">
        <div class="lista-secao-titulo">Itens (agregados)</div>
        ${agregadosHTML}
      </div>

      <div class="lista-ocs-wrap">
        <div class="lista-ocs-header" data-lista-id="${lista.id}">
          <span class="lista-ocs-toggle${abertaOcs ? ' aberto' : ''}">▶</span>
          <span>OCs incluídas (${nOcs})</span>
        </div>
        <div class="lista-ocs-lista${abertaOcs ? ' aberto' : ''}" id="lista-ocs-${lista.id}">${ocsHTML}</div>
      </div>
    </div>
  </div>`;
}

function _vincularEventosListas(container) {
  // Troca de status: atualiza SÓ a pill daquela lista — sem rebuild do DOM,
  // o que evita os artefatos visuais e a perda de estado aberto/fechado.
  container.querySelectorAll('.lista-status-select').forEach(sel => {
    sel.addEventListener('change', () => {
      const id     = parseInt(sel.dataset.listaId);
      const status = sel.value;
      backend.atualizar_status_lista(JSON.stringify({ id, status_entrega: status }), () => {
        const l = estado.listas.find(x => x.id === id);
        if (l) l.status_entrega = status;
        const pill = container.querySelector(`.status-pill[data-pill-lista="${id}"]`);
        if (pill) {
          pill.textContent = status;
          pill.className = `status-pill ${PILL_CLS[status] || 'pendente'}`;
          pill.setAttribute('data-pill-lista', id);
        }
        mostrarToast('Status atualizado.');
      });
    });
  });

  container.querySelectorAll('.btn-incluir-ocs').forEach(btn => {
    btn.addEventListener('click', () => abrirIncluirOCsNaLista(parseInt(btn.dataset.listaId)));
  });
  container.querySelectorAll('.btn-export-lista').forEach(btn => {
    btn.addEventListener('click', () => exportarListaXlsx(parseInt(btn.dataset.listaId)));
  });
  container.querySelectorAll('.btn-excluir-lista').forEach(btn => {
    btn.addEventListener('click', () => abrirModalExcluirLista(parseInt(btn.dataset.listaId)));
  });

  // Toggle do card inteiro — atualiza o Set de estado (persiste entre renders)
  container.querySelectorAll('.lista-card-toggle-area').forEach(area => {
    area.addEventListener('click', () => {
      const id      = parseInt(area.dataset.listaId);
      const body    = document.getElementById(`lista-body-${id}`);
      const chevron = area.querySelector('.lista-card-chevron');
      const aberto  = body.classList.toggle('aberto');
      chevron.classList.toggle('aberto', aberto);
      aberto ? estado.listasAbertas.add(id) : estado.listasAbertas.delete(id);
    });
  });

  // Toggle da sub-lista de OCs
  container.querySelectorAll('.lista-ocs-header').forEach(header => {
    header.addEventListener('click', () => {
      const id   = parseInt(header.dataset.listaId);
      const body = document.getElementById(`lista-ocs-${id}`);
      const tog  = header.querySelector('.lista-ocs-toggle');
      const aberto = body.classList.toggle('aberto');
      tog.classList.toggle('aberto', aberto);
      aberto ? estado.ocsAbertas.add(id) : estado.ocsAbertas.delete(id);
    });
  });

  // Cliques nos controles de ação não devem abrir/fechar o card
  container.querySelectorAll('.lista-card-actions button, .lista-card-actions select').forEach(el => {
    el.addEventListener('click', e => e.stopPropagation());
    el.addEventListener('change', e => e.stopPropagation());
  });

  container.querySelectorAll('.btn-excluir-oc').forEach(btn => {
    btn.addEventListener('click', () => abrirModalExcluirOC(parseInt(btn.dataset.ocId), null));
  });
}

function _htmlOCInterna(oc) {
  const itensHTML = oc.itens && oc.itens.length
    ? `<table class="oc-itens-inline">
         <thead><tr><th>Descrição</th><th>UN</th><th>Qtd</th><th>Valor Unit.</th><th>Total</th></tr></thead>
         <tbody>${oc.itens.map(it => `
           <tr>
             <td>${escapeHtml(it.descricao) || '—'}</td>
             <td>${escapeHtml(it.unidade)}</td>
             <td>${it.quantidade != null ? it.quantidade : '—'}</td>
             <td>${fmtBRL(it.valor_unitario)}</td>
             <td>${fmtBRL(it.valor_total)}</td>
           </tr>`).join('')}
         </tbody>
       </table>`
    : '<div class="oc-sem-itens">Sem itens.</div>';

  return `<div class="oc-card" style="margin:8px 0;border-left-color:#ececec;">
    <div class="oc-card-header">
      <div class="oc-card-info">
        <div class="oc-num">OC ${escapeHtml(oc.numero) || oc.id}</div>
        <div class="oc-forn">${escapeHtml(oc.fornecedor) || '—'}</div>
        <div class="oc-data">${oc.data_entrega_prevista ? 'Entrega: ' + fmtData(oc.data_entrega_prevista) : ''}</div>
      </div>
      <div class="oc-card-actions">
        <button class="btn-excluir-oc" data-oc-id="${oc.id}" title="Excluir OC" style="font-size:11px;">Excluir</button>
      </div>
    </div>
    <div class="oc-itens-wrap">${itensHTML}</div>
  </div>`;
}

// ─── CRIAR LISTA ──────────────────────────────────────────────────────────────
function criarLista() {
  const data = document.getElementById('nova-lista-data').value || null;
  backend.criar_lista(JSON.stringify({ data_prevista: data }), raw => {
    const r = JSON.parse(raw);
    document.getElementById('modal-nova-lista').style.display = 'none';
    mostrarToast(`${r.nome} criada.`);
    recarregarListas(() => abrirIncluirOCsNaLista(r.id));
  });
}

function abrirIncluirOCsNaLista(listaId) {
  const lista = estado.listas.find(l => l.id === listaId);
  estado.listaAtualId = listaId;
  document.getElementById('oc-lote-sub').textContent =
    `Adicionando à lista — ${lista ? lista.nome : ''}`;
  resetarFormOC();
  navegarPara('incluir-oc', 'agenda');
}

// ─── EXPORTAR LISTA ───────────────────────────────────────────────────────────
function exportarListaXlsx(listaId) {
  const lista = estado.listas.find(l => l.id === listaId);
  const nome  = `${lista ? lista.nome.replace(/\s+/g, '_') : 'lista'}_itens.xlsx`;
  backend.abrir_dialogo_salvar('Salvar planilha da lista', nome, caminho => {
    if (!caminho) return;
    backend.exportar_lista_xlsx(listaId, caminho, raw => {
      mostrarToast(JSON.parse(raw).ok ? 'Planilha exportada.' : 'Erro ao exportar.', !JSON.parse(raw).ok);
    });
  });
}

// ─── EXCLUIR LISTA ────────────────────────────────────────────────────────────
function abrirModalExcluirLista(listaId) {
  estado.listaExcluindoId = listaId;
  const lista = estado.listas.find(l => l.id === listaId);
  document.getElementById('modal-excluir-lista-titulo').textContent =
    `Excluir ${lista ? lista.nome : 'lista'}`;
  document.getElementById('modal-excluir-lista').style.display = 'flex';
}
function fecharModalExcluirLista() {
  document.getElementById('modal-excluir-lista').style.display = 'none';
  estado.listaExcluindoId = null;
}
function confirmarExcluirLista() {
  const id = estado.listaExcluindoId;
  if (!id) return;
  backend.excluir_lista(id, () => {
    fecharModalExcluirLista();
    mostrarToast('Lista excluída. OCs movidas para "Sem lista".');
    recarregarListas();
  });
}

// ─── EXCLUSÃO DE OC (individual e em massa) ──────────────────────────────────
function abrirModalExcluirOC(idUnico, idsMassa) {
  estado.ocExcluindoId = idUnico;
  const titulo = document.getElementById('modal-excluir-oc-titulo');
  const texto  = document.getElementById('modal-excluir-oc-texto');
  if (idsMassa && idsMassa.length) {
    titulo.textContent = `Excluir ${idsMassa.length} OC${idsMassa.length > 1 ? 's' : ''}`;
    texto.textContent  = `Tem certeza que deseja excluir ${idsMassa.length} ordem(ns) de compra selecionada(s)? Os itens serão excluídos junto. Essa ação não pode ser desfeita.`;
  } else {
    titulo.textContent = 'Excluir ordem de compra';
    texto.textContent  = 'Tem certeza que deseja excluir esta ordem de compra? Os itens serão excluídos junto. Essa ação não pode ser desfeita.';
  }
  document.getElementById('modal-excluir-oc').style.display = 'flex';
}
function fecharModalExcluirOC() {
  document.getElementById('modal-excluir-oc').style.display = 'none';
  estado.ocExcluindoId = null;
}
function confirmarExcluirOC() {
  const id = estado.ocExcluindoId;
  if (id == null) { fecharModalExcluirOC(); return; }
  backend.excluir_ordem_compra(id, () => {
    fecharModalExcluirOC();
    mostrarToast('Ordem de compra excluída.');
    recarregarListas();
  });
}

// ─── INCLUIR OC — lote ────────────────────────────────────────────────────────
function resetarFormOC() {
  estado.ocFilaLote = [];
  estado.ocFilaIdx  = 0;
  mostrarLendoOC(false);
  document.getElementById('oc-passo-selecao').style.display      = '';
  document.getElementById('oc-passo-confirmacao').style.display  = 'none';
  document.getElementById('oc-lote-progress').innerHTML          = '';
}

function abrirPDFsOC() {
  backend.abrir_dialogo_multiplos_arquivos('Selecionar PDFs de OC', 'PDF (*.pdf)', raw => {
    const caminhos = JSON.parse(raw);
    if (!caminhos.length) return;
    estado.ocFilaLote = caminhos;
    estado.ocFilaIdx  = 0;
    document.getElementById('oc-passo-selecao').style.display     = 'none';
    document.getElementById('oc-passo-confirmacao').style.display = '';
    processarProximaOC();
  });
}

function processarProximaOC() {
  const idx   = estado.ocFilaIdx;
  const total = estado.ocFilaLote.length;
  if (idx >= total) {
    mostrarToast(`${total} OC${total > 1 ? 's' : ''} salva${total > 1 ? 's' : ''}.`);
    recarregarListas();
    navegarPara('agenda', 'agenda');
    return;
  }

  document.getElementById('oc-conf-titulo').textContent = `OC ${idx + 1} de ${total}`;
  atualizarProgressoOC();
  mostrarLendoOC(true);

  extrairAsync('ler_pdf_oc', estado.ocFilaLote[idx], raw => {
    mostrarLendoOC(false);
    const d = JSON.parse(raw);
    document.getElementById('oc-numero').value       = d.numero || '';
    document.getElementById('oc-fornecedor').value   = d.fornecedor || '';
    document.getElementById('oc-data-emissao').value = d.data_emissao || '';
    document.getElementById('oc-data-entrega').value = d.data_entrega_prevista || '';

    const tbody = document.getElementById('oc-itens-preview');
    const empty = document.getElementById('oc-preview-empty');
    if (!d.itens || !d.itens.length) { tbody.innerHTML = ''; empty.style.display = ''; }
    else {
      empty.style.display = 'none';
      tbody.innerHTML = d.itens.map((it, i) => `
        <tr><td>${i+1}</td><td>${escapeHtml(it.descricao)||'—'}</td>
        <td>${escapeHtml(it.unidade)||'—'}</td>
        <td>${it.quantidade!=null?it.quantidade:'—'}</td>
        <td>${fmtBRL(it.valor_unitario)}</td><td>${fmtBRL(it.valor_total)}</td></tr>`).join('');
    }
  });
}

function atualizarProgressoOC() {
  const total = estado.ocFilaLote.length;
  document.getElementById('oc-lote-progress').innerHTML = estado.ocFilaLote.map((_, i) => `
    <span class="prog-dot ${i < estado.ocFilaIdx ? 'done' : i === estado.ocFilaIdx ? 'atual' : ''}"></span>
  `).join('');
}

function salvarOCAtual() {
  const itens = [];
  document.querySelectorAll('#oc-itens-preview tr').forEach(tr => {
    const tds = tr.querySelectorAll('td');
    if (tds.length >= 6) itens.push({
      descricao: tds[1].textContent, unidade: tds[2].textContent === '—' ? '' : tds[2].textContent,
      quantidade: parseBRL(tds[3].textContent),
      valor_unitario: parseBRL(tds[4].textContent), valor_total: parseBRL(tds[5].textContent),
    });
  });
  const dados = {
    numero: document.getElementById('oc-numero').value.trim(),
    fornecedor: document.getElementById('oc-fornecedor').value.trim(),
    data_emissao: document.getElementById('oc-data-emissao').value || null,
    data_entrega_prevista: document.getElementById('oc-data-entrega').value || null,
    arquivo_pdf: estado.ocFilaLote[estado.ocFilaIdx] || '',
    lista_id: estado.listaAtualId,
    itens,
  };
  backend.salvar_ordem_compra(JSON.stringify(dados), () => { avancarOCLote(); });
}

function avancarOCLote() {
  estado.ocFilaIdx++;
  processarProximaOC();
}

// ─── NOTAS FISCAIS — board ───────────────────────────────────────────────────
function nfsFiltradas() {
  const f = estado.filtros;
  return estado.nfs.filter(nf => {
    if (f.orgao_id && String(nf.orgao_id) !== String(f.orgao_id)) return false;
    if (f.status && nf.status_pagamento !== f.status) return false;
    if (f.mes) {
      const [fano, fmes] = f.mes.split('-');
      if (!nf.data_emissao) return false;
      const [nfano, nfmes] = nf.data_emissao.split('-');
      if (nfano !== fano || nfmes !== fmes) return false;
    }
    return true;
  });
}

function aplicarFiltros() {
  estado.filtros.orgao_id  = document.getElementById('filtro-orgao').value;
  estado.filtros.status    = document.getElementById('filtro-status').value;
  estado.filtros.mes       = document.getElementById('filtro-mes').value;
  estado.selecionadas.clear();
  atualizarResumoFiltros();
  renderNFs();
}

function limparFiltros() {
  ['filtro-orgao','filtro-status','filtro-mes'].forEach(id => {
    document.getElementById(id).value = '';
  });
  estado.filtros = { orgao_id: '', status: '', mes: '' };
  estado.selecionadas.clear();
  atualizarResumoFiltros();
  renderNFs();
}

function atualizarResumoFiltros() {
  const f = estado.filtros;
  const partes = [];
  if (f.orgao_id) partes.push(ORGAOS[f.orgao_id] || f.orgao_id);
  if (f.status) partes.push(f.status === 'pago' ? 'Pagas' : 'Não pagas');
  if (f.mes) {
    const [ano, mes] = f.mes.split('-');
    partes.push(`${MESES[parseInt(mes, 10) - 1]}/${ano}`);
  }
  const badge = document.getElementById('filtros-badge');
  const resumo = document.getElementById('filtros-resumo');
  const btnLimpar = document.getElementById('btn-limpar-filtros');
  const btnToggle = document.getElementById('btn-toggle-filtros');
  if (partes.length > 0) {
    badge.textContent = partes.length;
    badge.style.display = 'inline-block';
    resumo.textContent = partes.join(' · ');
    btnLimpar.style.display = 'inline-block';
    btnToggle.classList.add('ativo');
  } else {
    badge.style.display = 'none';
    resumo.textContent = '';
    btnLimpar.style.display = 'none';
    btnToggle.classList.remove('ativo');
  }
}

// Atualiza só a barra de marcação em massa (visibilidade + contagem). Os totais
// pago/não-pago não mudam ao (de)selecionar, então alternar seleção não precisa
// reconstruir o board — ver renderNFs.
function atualizarBarraMassa() {
  document.getElementById('massa-bar').style.display = estado.selecionadas.size > 0 ? '' : 'none';
  document.getElementById('massa-contagem').textContent =
    `${estado.selecionadas.size} NF${estado.selecionadas.size > 1 ? 's' : ''} selecionada${estado.selecionadas.size > 1 ? 's' : ''}`;
}

function renderNFs() {
  const visíveis = nfsFiltradas();
  const naoPagas = visíveis.filter(nf => nf.status_pagamento !== 'pago');
  const pagas    = visíveis.filter(nf => nf.status_pagamento === 'pago');

  document.getElementById('total-nao-pago').textContent = fmtBRL(naoPagas.reduce((s,nf)=>s+(nf.valor||0),0));
  document.getElementById('total-pago').textContent     = fmtBRL(pagas.reduce((s,nf)=>s+(nf.valor||0),0));
  document.getElementById('pag-badge').textContent      = naoPagas.length
    ? `${fmtBRL(naoPagas.reduce((s,nf)=>s+(nf.valor||0),0))} a pagar` : 'Tudo pago';

  atualizarBarraMassa();

  const listaNP = document.getElementById('lista-nao-pago');
  const emptyNP = document.getElementById('nao-pago-empty');
  if (!naoPagas.length) { listaNP.innerHTML = ''; emptyNP.style.display = ''; }
  else {
    emptyNP.style.display = 'none';
    listaNP.innerHTML = naoPagas.map(nf => cartaoNF(nf, false)).join('');
  }

  const listaP = document.getElementById('lista-pago');
  const emptyP = document.getElementById('pago-empty');
  if (!pagas.length) { listaP.innerHTML = ''; emptyP.style.display = ''; }
  else {
    emptyP.style.display = 'none';
    listaP.innerHTML = pagas.map(nf => cartaoNF(nf, true)).join('');
  }

  // Bind checkboxes — alterna a seleção atualizando SÓ a barra de massa, sem
  // reconstruir o board. Rebuild do innerHTML a cada clique destruía/recriava
  // todos os cards (e o próprio checkbox clicado), causando artefatos/flicker
  // no QWebEngine — mesma classe de bug já corrigida na tela de listas.
  document.querySelectorAll('.nf-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const id = parseInt(cb.dataset.nfId);
      cb.checked ? estado.selecionadas.add(id) : estado.selecionadas.delete(id);
      atualizarBarraMassa();
    });
  });

  // Bind info (clique para detalhe)
  document.querySelectorAll('.nf-card-info[data-nf-id]').forEach(el => {
    el.addEventListener('click', () => abrirDetalheNF(parseInt(el.dataset.nfId), 'pagamentos'));
  });

  // Bind ações
  document.querySelectorAll('.btn-marcar-pago[data-nf-id]').forEach(btn =>
    btn.addEventListener('click', () => abrirModalPagamento(parseInt(btn.dataset.nfId))));
  document.querySelectorAll('.btn-desfazer[data-nf-id]').forEach(btn =>
    btn.addEventListener('click', () => desfazerPagamento(parseInt(btn.dataset.nfId))));
  document.querySelectorAll('.btn-excluir-nf[data-nf-id]').forEach(btn =>
    btn.addEventListener('click', () => abrirModalExcluirNF(parseInt(btn.dataset.nfId), null)));
}

function cartaoNF(nf, paga) {
  const checked   = estado.selecionadas.has(nf.id) ? 'checked' : '';
  const vencInfo  = paga
    ? `<div class="vencimento pago-em">${nf.data_pagamento ? 'pago em ' + fmtData(nf.data_pagamento) : 'pago'}</div>`
    : `<div class="vencimento">${nf.data_vencimento ? 'vence ' + fmtData(nf.data_vencimento) : ''}</div>`;
  const btnAcao   = paga
    ? `<button class="btn-acao btn-desfazer" data-nf-id="${nf.id}">Desfazer</button>`
    : `<button class="btn-acao btn-marcar-pago" data-nf-id="${nf.id}">Marcar paga</button>`;
  const checkbox  = !paga
    ? `<input type="checkbox" class="nf-checkbox" data-nf-id="${nf.id}" ${checked} />`
    : '';

  return `<div class="nf-card">
    ${checkbox}
    <div class="info nf-card-info" data-nf-id="${nf.id}" style="cursor:pointer;flex:1;">
      <div class="num">NF ${escapeHtml(nf.numero) || '—'}</div>
      ${nf.orgao_nome ? `<div class="orgao-tag">${escapeHtml(nf.orgao_nome)}${nf.categoria ? ' · ' + escapeHtml(nf.categoria) : ''}</div>` : ''}
    </div>
    <div class="right"><div class="valor">${fmtBRL(nf.valor)}</div>${vencInfo}</div>
    ${btnAcao}
    <button class="btn-acao btn-excluir-nf" data-nf-id="${nf.id}" title="Excluir NF" style="color:#c90914;background:#fdeceb;">✕</button>
  </div>`;
}

function abrirModalPagamento(id) {
  estado.nfPagandoId = id;
  document.getElementById('pag-data').value = isoHoje();
  document.getElementById('modal-pagamento').style.display = 'flex';
}
function fecharModalPagamento() {
  document.getElementById('modal-pagamento').style.display = 'none';
  estado.nfPagandoId = null;
}
function confirmarPagamento() {
  const id   = estado.nfPagandoId;
  const data = document.getElementById('pag-data').value || isoHoje();
  backend.atualizar_status_nf(JSON.stringify({ id, status_pagamento: 'pago', data_pagamento: data }), () => {
    const nf = estado.nfs.find(n => n.id === id);
    if (nf) { nf.status_pagamento = 'pago'; nf.data_pagamento = data; }
    fecharModalPagamento();
    renderNFs(); renderDashboard();
    if (estado.nfAtual && estado.nfAtual.id === id) abrirDetalheNF(id, estado.viewAnteriorNF);
    mostrarToast('NF marcada como paga.');
  });
}
function desfazerPagamento(id) {
  backend.atualizar_status_nf(JSON.stringify({ id, status_pagamento: 'nao_pago', data_pagamento: null }), () => {
    const nf = estado.nfs.find(n => n.id === id);
    if (nf) { nf.status_pagamento = 'nao_pago'; nf.data_pagamento = null; }
    renderNFs(); renderDashboard();
    mostrarToast('Pagamento desfeito.');
  });
}
function confirmarMassa() {
  const ids  = [...estado.selecionadas];
  const data = document.getElementById('massa-data').value || isoHoje();
  backend.marcar_pagas_em_massa(JSON.stringify({ ids, data_pagamento: data }), raw => {
    const r = JSON.parse(raw);
    estado.nfs.forEach(nf => {
      if (ids.includes(nf.id)) { nf.status_pagamento = 'pago'; nf.data_pagamento = data; }
    });
    estado.selecionadas.clear();
    document.getElementById('modal-massa').style.display = 'none';
    renderNFs(); renderDashboard();
    mostrarToast(`${r.atualizadas} NF${r.atualizadas > 1 ? 's' : ''} marcada${r.atualizadas > 1 ? 's' : ''} como pagas.`);
  });
}

// ─── EXCLUSÃO DE NF ──────────────────────────────────────────────────────────
function abrirModalExcluirNF(idUnico, idsMassa) {
  estado.nfExcluindoId  = idUnico;
  estado.nfExcluindoIds = idsMassa || [];
  const n = estado.nfExcluindoIds.length;
  const massa = n > 1 || (idUnico == null && n > 0);
  document.getElementById('modal-excluir-nf-titulo').textContent = massa
    ? `Excluir ${n} nota${n > 1 ? 's' : ''} fiscal${n > 1 ? 'is' : ''}`
    : 'Excluir nota fiscal';
  document.getElementById('modal-excluir-nf-texto').textContent = massa
    ? `Tem certeza que deseja excluir ${n} NFs? Os arquivos PDF copiados também serão removidos. Essa ação não pode ser desfeita.`
    : 'Tem certeza que deseja excluir esta NF? O arquivo PDF copiado também será removido. Essa ação não pode ser desfeita.';
  document.getElementById('modal-excluir-nf').style.display = 'flex';
}
function fecharModalExcluirNF() {
  document.getElementById('modal-excluir-nf').style.display = 'none';
  estado.nfExcluindoId  = null;
  estado.nfExcluindoIds = [];
}
function confirmarExcluirNF() {
  if (estado.nfExcluindoIds.length > 0) {
    const ids = estado.nfExcluindoIds;
    backend.excluir_nfs_em_massa(JSON.stringify({ ids }), raw => {
      const r = JSON.parse(raw);
      estado.nfs = estado.nfs.filter(nf => !ids.includes(nf.id));
      estado.selecionadas.clear();
      fecharModalExcluirNF();
      renderNFs(); renderDashboard();
      mostrarToast(`${r.excluidas} NF${r.excluidas > 1 ? 's' : ''} excluída${r.excluidas > 1 ? 's' : ''}.`);
    });
  } else if (estado.nfExcluindoId != null) {
    const id = estado.nfExcluindoId;
    backend.excluir_nf(id, () => {
      estado.nfs = estado.nfs.filter(nf => nf.id !== id);
      fecharModalExcluirNF();
      renderNFs(); renderDashboard();
      mostrarToast('NF excluída.');
    });
  }
}

// ─── DETALHE NF ───────────────────────────────────────────────────────────────
function abrirDetalheNF(id, viewOrigem) {
  const nf = estado.nfs.find(n => n.id === id);
  if (!nf) return;
  estado.nfAtual        = nf;
  estado.viewAnteriorNF = viewOrigem || 'pagamentos';

  document.getElementById('nf-det-titulo').textContent = `NF ${nf.numero || '—'}`;
  document.getElementById('nf-det-sub').textContent    = nf.orgao_nome || '—';

  const btnPago = document.getElementById('btn-marcar-pago-det');
  btnPago.style.display = nf.status_pagamento === 'pago' ? 'none' : '';

  document.getElementById('nf-det-info').innerHTML = `
    <tr><td style="color:#999;font-size:11px;width:120px;">Número</td><td>${escapeHtml(nf.numero) || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Emissão</td><td>${fmtData(nf.data_emissao)}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Valor</td><td><strong>${fmtBRL(nf.valor)}</strong></td></tr>
    <tr><td style="color:#999;font-size:11px;">Vencimento</td><td>${fmtData(nf.data_vencimento)}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Pagamento</td><td>${nf.data_pagamento ? fmtData(nf.data_pagamento) : '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Status</td><td><span class="status-pill ${nf.status_pagamento === 'pago' ? 'pago' : 'nao-pago'}">${nf.status_pagamento === 'pago' ? 'pago' : 'não pago'}</span></td></tr>`;

  document.getElementById('nf-det-extra').innerHTML = `
    <tr><td style="color:#999;font-size:11px;width:120px;">Órgão</td><td>${escapeHtml(nf.orgao_nome) || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Categoria</td><td>${escapeHtml(nf.categoria) || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Origem</td><td>${escapeHtml(nf.origem) || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Incluída em</td><td>${nf.criado_em ? escapeHtml(nf.criado_em.slice(0, 16)) : '—'}</td></tr>`;

  backend.listar_itens_nf(id, raw => {
    const itens = JSON.parse(raw);
    const tbody = document.getElementById('nf-det-itens');
    const empty = document.getElementById('nf-det-itens-empty');
    if (!itens.length) { tbody.innerHTML = ''; empty.style.display = ''; }
    else {
      empty.style.display = 'none';
      tbody.innerHTML = itens.map((it, i) => `
        <tr>
          <td>${i+1}</td><td>${escapeHtml(it.descricao)||'—'}</td>
          <td>${it.quantidade!=null?it.quantidade:'—'}</td>
          <td>${fmtBRL(it.valor_unitario)}</td><td>${fmtBRL(it.valor_total)}</td>
          <td>${escapeHtml(it.ncm)||'—'}</td><td>${escapeHtml(it.cfop)||'—'}</td>
        </tr>`).join('');
    }
  });

  navegarPara('detalhe-nf', viewOrigem);
}

// ─── INCLUIR NF — lote PDF/XML + manual ──────────────────────────────────────
function resetarFormNF() {
  estado.nfFormModo    = 'pdf';
  estado.nfFormCaminho = null;
  estado.nfFormItens   = [];
  estado.nfFilaLote    = [];
  estado.nfFilaIdx     = 0;
  estado.nfRevisaoCaminho = null;

  const dupAviso = document.getElementById('nf-dup-aviso');
  if (dupAviso) dupAviso.style.display = 'none';

  mostrarLendoNF(false);
  document.querySelectorAll('.modo-tab').forEach(t => t.classList.toggle('active', t.dataset.modo === 'pdf'));
  document.getElementById('nf-sec-arquivo').style.display  = '';
  document.getElementById('nf-form-dados').style.display   = 'none';
  document.getElementById('nf-lote-progress').style.display = 'none';
  document.getElementById('nf-upload-icon').textContent    = 'PDF';
  document.getElementById('nf-upload-texto').textContent   = 'Clique para selecionar um ou mais arquivos';
  document.getElementById('btn-pular-nf').style.display    = 'none';
  document.getElementById('nf-modo-wrap').style.display    = '';

  ['nf-numero','nf-data-emissao','nf-valor',
   'nf-data-vencimento','nf-data-pagamento'].forEach(id => document.getElementById(id).value = '');
  document.querySelectorAll('#nf-orgao-tags .tag').forEach(t => t.classList.remove('selected'));
  document.getElementById('toggle-nao-pago').classList.add('checked');
  document.getElementById('toggle-pago').classList.remove('checked');
  document.getElementById('field-data-pagamento').style.display = 'none';
}

function mudarModoNF(modo) {
  estado.nfFormModo  = modo;
  estado.nfFormItens = [];
  estado.nfFilaLote  = [];
  estado.nfFilaIdx   = 0;

  document.getElementById('nf-form-dados').style.display   = modo === 'manual' ? '' : 'none';
  document.getElementById('nf-sec-arquivo').style.display  = modo !== 'manual' ? '' : 'none';
  document.getElementById('nf-modo-wrap').style.display    = '';
  document.getElementById('btn-pular-nf').style.display    = 'none';
  document.getElementById('nf-lote-progress').style.display = 'none';

  if (modo === 'xml') {
    document.getElementById('nf-upload-icon').textContent  = 'XML';
    document.getElementById('nf-upload-texto').textContent = 'Clique para selecionar um ou mais XMLs da NFe';
    document.getElementById('nf-upload-hint').textContent  = 'NFe modelo 55 · Múltipla seleção permitida';
  } else if (modo === 'pdf') {
    document.getElementById('nf-upload-icon').textContent  = 'PDF';
    document.getElementById('nf-upload-texto').textContent = 'Clique para selecionar um ou mais arquivos';
    document.getElementById('nf-upload-hint').textContent  = 'Múltipla seleção permitida';
  }
  if (modo === 'manual') {
    ['nf-numero','nf-data-emissao','nf-valor'].forEach(id => {
      document.getElementById(id).value = '';
    });
  }
}

function abrirPDFsNF() {
  backend.abrir_dialogo_multiplos_arquivos('Selecionar PDF(s) de NF', 'PDF (*.pdf)', raw => {
    const caminhos = JSON.parse(raw);
    if (!caminhos.length) return;
    estado.nfFilaLote = caminhos;
    estado.nfFilaIdx  = 0;
    iniciarLoteNF();
  });
}

function abrirXMLsNF() {
  backend.abrir_dialogo_multiplos_arquivos('Selecionar XML(s) da NFe', 'XML NFe (*.xml)', raw => {
    const caminhos = JSON.parse(raw);
    if (!caminhos.length) return;
    estado.nfFilaLote = caminhos;
    estado.nfFilaIdx  = 0;
    iniciarLoteNF();
  });
}

function iniciarLoteNF() {
  const total = estado.nfFilaLote.length;
  if (total > 1) {
    document.getElementById('nf-lote-progress').style.display = '';
    document.getElementById('btn-pular-nf').style.display = '';
  }
  processarProximaNF();
}

function atualizarProgressoNF() {
  const el = document.getElementById('nf-lote-progress');
  if (!el) return;
  el.innerHTML = estado.nfFilaLote.map((_, i) => `
    <span class="prog-dot ${i < estado.nfFilaIdx ? 'done' : i === estado.nfFilaIdx ? 'atual' : ''}"></span>
  `).join('');
  // Título sempre no padrão "NF X de N" (igual à confirmação de OC), mesmo
  // para um único arquivo — reforça que esta é uma tela de confirmação,
  // não a de inclusão manual.
  document.getElementById('nf-conf-titulo').textContent =
    `NF ${estado.nfFilaIdx + 1} de ${estado.nfFilaLote.length}`;
}

function processarProximaNF() {
  const idx   = estado.nfFilaIdx;
  const total = estado.nfFilaLote.length;
  if (idx >= total) {
    mostrarToast(`${total} NF${total > 1 ? 's' : ''} salva${total > 1 ? 's' : ''}.`);
    backend.listar_nfs(raw => { estado.nfs = JSON.parse(raw); renderNFs(); renderDashboard(); });
    navegarPara('pagamentos', 'pagamentos');
    return;
  }
  atualizarProgressoNF();

  const caminho = estado.nfFilaLote[idx];
  const modo    = estado.nfFormModo;
  estado.nfFormCaminho  = caminho;
  estado.nfFormItens    = [];

  const metodo = modo === 'xml' ? 'ler_xml_nf' : 'ler_pdf_nf';
  mostrarLendoNF(true);

  extrairAsync(metodo, caminho, raw => {
    mostrarLendoNF(false);
    const d = JSON.parse(raw);
    if (d._erro) { mostrarToast(`Erro: ${d._erro}`, true); avancarNFLote(); return; }
    document.getElementById('nf-numero').value       = d.numero || '';

    document.getElementById('nf-data-emissao').value = d.data_emissao || '';
    if (d.valor != null) document.getElementById('nf-valor').value = moedaParaMascara(d.valor);

    // Detecção automática do órgão (CLAUDE.md seção 6.3) — pré-seleciona a
    // tag sem exigir confirmação manual; usuário pode trocar antes de salvar.
    document.querySelectorAll('#nf-orgao-tags .tag').forEach(t => t.classList.remove('selected'));
    if (d.orgao_id) {
      const tagOrgao = document.querySelector(`#nf-orgao-tags .tag[data-val="${d.orgao_id}"]`);
      if (tagOrgao) tagOrgao.classList.add('selected');
    }

    // Coleta de itens desativada por decisão de produto (2026-06-29).
    // nfFormItens permanece vazio; salvarNFAtual envia itens: [].
    document.getElementById('nf-sec-arquivo').style.display = 'none';
    document.getElementById('nf-form-dados').style.display  = '';
    // Some as abas de modo (PDF/XML/Manual) na confirmação — a tela passa a
    // se parecer com a confirmação da OC, não com a inclusão manual.
    document.getElementById('nf-modo-wrap').style.display    = 'none';
  });
}

function avancarNFLote() {
  estado.nfFilaIdx++;
  // Reseta campos para o próximo arquivo
  ['nf-numero','nf-data-emissao','nf-valor'].forEach(id => document.getElementById(id).value = '');
  estado.nfFormItens = [];
  document.getElementById('nf-form-dados').style.display = estado.nfFilaIdx < estado.nfFilaLote.length ? '' : 'none';
  processarProximaNF();
}

function renderItensNFForm(editavel) {
  const tbody = document.getElementById('nf-itens-tabela');
  const empty = document.getElementById('nf-itens-empty');
  if (!estado.nfFormItens.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';
  tbody.innerHTML = estado.nfFormItens.map((it, i) => `
    <tr>
      <td>${i+1}</td>
      <td>${editavel ? `<input type="text" value="${escapeHtml(it.descricao)}" style="width:100%;" oninput="estado.nfFormItens[${i}].descricao=this.value" />` : (escapeHtml(it.descricao)||'—')}</td>
      <td>${editavel ? `<input type="number" value="${it.quantidade||''}" style="width:70px;" oninput="estado.nfFormItens[${i}].quantidade=parseFloat(this.value)||null" />` : (it.quantidade!=null?it.quantidade:'—')}</td>
      <td>${editavel ? `<input type="text" value="${it.valor_unitario!=null?moedaParaMascara(it.valor_unitario):''}" style="width:80px;" oninput="mascararMoeda(this);estado.nfFormItens[${i}].valor_unitario=parseBRL(this.value)" />` : fmtBRL(it.valor_unitario)}</td>
      <td>${editavel ? `<input type="text" value="${it.valor_total!=null?it.valor_total:''}" style="width:80px;" oninput="estado.nfFormItens[${i}].valor_total=parseBRL(this.value)" />` : fmtBRL(it.valor_total)}</td>
      <td>${escapeHtml(it.ncm)}</td>
      <td>${editavel ? `<button class="btn-remover-item" onclick="removerItemNF(${i})">✕</button>` : ''}</td>
    </tr>`).join('');
}

function adicionarLinhaItemNF() {
  estado.nfFormItens.push({ descricao:'', quantidade:null, valor_unitario:null, valor_total:null, ncm:'', cfop:'' });
  renderItensNFForm(true);
}
function removerItemNF(idx) {
  estado.nfFormItens.splice(idx, 1);
  renderItensNFForm(true);
}

function salvarNFAtual() {
  const statusPago = document.getElementById('toggle-pago').classList.contains('checked');
  const orgaoTag   = document.querySelector('#nf-orgao-tags .tag.selected');
  const modo       = estado.nfFormModo;

  const dados = {
    numero:          document.getElementById('nf-numero').value.trim() || null,
    data_emissao:    document.getElementById('nf-data-emissao').value || null,
    valor:           parseBRL(document.getElementById('nf-valor').value),
    orgao_id:        orgaoTag ? parseInt(orgaoTag.dataset.val) : null,
    // categoria desativada por decisão de produto (2026-06-29)
    categoria:       null,
    status_pagamento:statusPago ? 'pago' : 'nao_pago',
    data_vencimento: document.getElementById('nf-data-vencimento').value || null,
    data_pagamento:  statusPago ? (document.getElementById('nf-data-pagamento').value || isoHoje()) : null,
    arquivo_pdf:     modo === 'pdf' ? (estado.nfFormCaminho || '') : '',
    origem:          modo,
    // itens desativados por decisão de produto (2026-06-29)
    itens:           [],
  };

  if (!dados.valor) { mostrarToast('Informe o valor da NF.', true); return; }

  backend.salvar_nf(JSON.stringify(dados), () => {
    if (estado.nfFilaLote.length > 1) {
      avancarNFLote();
    } else {
      mostrarToast('Nota fiscal salva.');
      // Se veio da fila de revisão, dispensa o item (já está no banco; não
      // reaparecerá porque o arquivo_pdf agora consta em notas_fiscais).
      const caminhoRev = estado.nfRevisaoCaminho;
      estado.nfRevisaoCaminho = null;
      if (caminhoRev) backend.descartar_revisao(caminhoRev, () => {});
      backend.listar_nfs(raw => { estado.nfs = JSON.parse(raw); renderNFs(); renderDashboard(); });
      navegarPara('pagamentos', 'pagamentos');
    }
  });
}

// ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
function renderConfiguracoes() {
  const mapa = {
    'pasta_nfs':           'cfg-pasta-nfs',
    'pasta_ordens_compra': 'cfg-pasta-oc',
    'pasta_backup':        'cfg-pasta-bkp',
  };
  Object.entries(mapa).forEach(([chave, inputId]) => {
    const el = document.getElementById(inputId);
    if (el) el.value = estado.config[chave] || '';
  });
  backend.versao_atual(raw => {
    document.getElementById('cfg-versao-atual').textContent = JSON.parse(raw).versao || '—';
  });
}

// ─── ATUALIZAÇÕES (GitHub Releases) ────────────────────────────────────────────
// Checagem automática ao abrir o app (main.py, com atraso) e botão manual em
// Configurações chamam o mesmo backend.verificar_atualizacao(); o resultado
// chega por este sinal, com estados intermediários. Ao encontrar versão nova,
// baixa e instala silenciosamente, sem pedir confirmação — o app fecha sozinho
// ao final (o instalador o reabre já atualizado).
function tratarStatusAtualizacao(statusJson) {
  const s = JSON.parse(statusJson);
  const linha = document.getElementById('cfg-update-status');
  const btn   = document.getElementById('btn-verificar-atualizacao');

  switch (s.estado) {
    case 'verificando':
      if (linha) linha.textContent = 'Verificando atualizações…';
      if (btn) btn.disabled = true;
      break;
    case 'nenhuma':
      if (linha) linha.textContent = 'Você está na versão mais recente.';
      if (btn) btn.disabled = false;
      break;
    case 'baixando':
      if (linha) linha.textContent = `Baixando atualização v${s.versao}…`;
      mostrarToast(`Nova versão v${s.versao} encontrada — baixando…`);
      break;
    case 'instalando':
      if (linha) linha.textContent = `Instalando v${s.versao}…`;
      mostrarToast('Instalando atualização — o aplicativo vai reiniciar.');
      break;
    case 'erro':
      if (linha) linha.textContent = 'Falha ao verificar/instalar atualização.';
      if (btn) btn.disabled = false;
      mostrarToast('Não foi possível concluir a atualização.', true);
      break;
  }
}
