'use strict';

// ─── Estado global ────────────────────────────────────────────────────────────
const estado = {
  mesAtual:       new Date(),
  nfs:            [],           // todas as NFs (cache)
  ocs:            [],           // OCs com itens aninhados
  config:         {},
  // Detalhe NF
  nfAtual:        null,
  viewAnteriorNF: 'pagamentos',
  // Filtros NF
  filtros:        { orgao_id: '', categoria: '', status: '', mes: '' },
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
};

const ORGAOS = { 1: 'Administração', 2: 'Saúde', 3: 'Educação', 4: 'Assistência Social' };
const CORES_ORGAO = { 1: '#c90914', 2: '#f2972c', 3: '#1a1a1a', 4: '#2e7d32' };
const MESES  = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                 'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

// ─── Utilitários ──────────────────────────────────────────────────────────────
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
}

// ─── Inicialização ────────────────────────────────────────────────────────────
new QWebChannel(qt.webChannelTransport, channel => {
  window.backend = channel.objects.backend;
  iniciar();
});

function iniciar() {
  atualizarHora();
  setInterval(atualizarHora, 60000);
  vincularEventos();
  carregarTudo();
}
function atualizarHora() {
  const ag = new Date();
  document.getElementById('sidebar-hora').textContent =
    'Atualizado ' + ag.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function carregarTudo() {
  backend.listar_nfs(raw => { estado.nfs = JSON.parse(raw); renderDashboard(); renderNFs(); });
  backend.listar_ordens_compra_com_itens(raw => { estado.ocs = JSON.parse(raw); renderLista(); });
  backend.carregar_config(raw => { estado.config = JSON.parse(raw); renderConfiguracoes(); });
}

// ─── Vínculos ─────────────────────────────────────────────────────────────────
function vincularEventos() {
  // Sidebar
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => navegarPara(link.dataset.view, link.dataset.view));
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
  document.getElementById('btn-incluir-oc').addEventListener('click', () => {
    resetarFormOC();
    navegarPara('incluir-oc', 'agenda');
  });
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
  ['filtro-orgao','filtro-categoria','filtro-status','filtro-mes'].forEach(id => {
    document.getElementById(id).addEventListener('change', aplicarFiltros);
  });
  document.getElementById('btn-limpar-filtros').addEventListener('click', limparFiltros);

  // Checkbox "selecionar todas"
  document.getElementById('check-todos-np').addEventListener('change', e => {
    const nfsVisiveis = nfsFiltradas().filter(nf => nf.status_pagamento !== 'pago');
    if (e.target.checked) {
      nfsVisiveis.forEach(nf => estado.selecionadas.add(nf.id));
    } else {
      estado.selecionadas.clear();
    }
    renderNFs();
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
    renderNFs();
  });
  document.getElementById('modal-massa-fechar').addEventListener('click', () => document.getElementById('modal-massa').style.display = 'none');
  document.getElementById('modal-massa-cancelar').addEventListener('click', () => document.getElementById('modal-massa').style.display = 'none');
  document.getElementById('modal-massa-confirmar').addEventListener('click', confirmarMassa);
  document.getElementById('modal-massa').addEventListener('click', e => {
    if (e.target === e.currentTarget) document.getElementById('modal-massa').style.display = 'none';
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
  vincularTagsUnicas('nf-orgao-tags');
  vincularTagsUnicas('nf-categoria-tags');
  document.getElementById('btn-salvar-nf').addEventListener('click', salvarNFAtual);
  document.getElementById('btn-pular-nf').addEventListener('click', avancarNFLote);
  document.getElementById('btn-add-item-nf').addEventListener('click', adicionarLinhaItemNF);

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

  const nfsMes = estado.nfs.filter(nf => {
    if (!nf.data_emissao) return false;
    const [y, m] = nf.data_emissao.split('-').map(Number);
    return y === ano && m === mes + 1;
  });

  const entradas  = nfsMes.reduce((s, nf) => s + (nf.valor || 0), 0);
  const recebido  = nfsMes.filter(nf => nf.status_pagamento === 'pago').reduce((s, nf) => s + (nf.valor || 0), 0);
  const pendentes = nfsMes.filter(nf => nf.status_pagamento !== 'pago').length;

  document.getElementById('kpi-entradas').textContent = fmtBRL(entradas);
  document.getElementById('kpi-recebido').textContent = fmtBRL(recebido);
  document.getElementById('kpi-saldo').textContent    = fmtBRL(entradas - recebido);
  document.getElementById('dash-badge').textContent   = pendentes > 0
    ? `${pendentes} NF${pendentes > 1 ? 's' : ''} pendente${pendentes > 1 ? 's' : ''}`
    : 'Tudo em dia';

  // Gráfico de pizza por órgão
  renderPieOrgao(mes + 1, ano, nfsMes);

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
        <td>NF ${nf.numero || '—'}</td>
        <td>${nf.fornecedor || '—'}</td>
        <td>${nf.orgao_nome || '—'}</td>
        <td>${fmtData(nf.data_emissao)}</td>
        <td>${fmtBRL(nf.valor)}</td>
        <td><span class="status-pill ${nf.status_pagamento === 'pago' ? 'pago' : 'nao-pago'}">${nf.status_pagamento === 'pago' ? 'pago' : 'não pago'}</span></td>
      </tr>`).join('');
    tbody.querySelectorAll('tr[data-nf-id]').forEach(tr => {
      tr.addEventListener('click', () => abrirDetalheNF(parseInt(tr.dataset.nfId), 'dashboard'));
    });
  }
}

function renderPieOrgao(mes, ano, nfsMes) {
  // Agrega por órgão a partir do cache local (sem nova chamada ao backend)
  const totais = { 1: 0, 2: 0, 3: 0, 4: 0 };
  nfsMes.forEach(nf => { if (nf.orgao_id) totais[nf.orgao_id] = (totais[nf.orgao_id] || 0) + (nf.valor || 0); });
  const somaTotal = Object.values(totais).reduce((a, b) => a + b, 0);

  const pie    = document.getElementById('dash-pie');
  const legend = document.getElementById('dash-pie-legend');

  if (somaTotal === 0) {
    pie.style.background = '#f1f1f1';
    legend.innerHTML = '<div style="color:#bbb;font-size:13px;">Sem notas neste mês.</div>';
    return;
  }

  // Constrói conic-gradient
  let acum = 0;
  const partes = Object.entries(totais).map(([id, val]) => {
    const pct = somaTotal > 0 ? (val / somaTotal) * 100 : 0;
    const trecho = `${CORES_ORGAO[id]} ${acum.toFixed(2)}% ${(acum + pct).toFixed(2)}%`;
    acum += pct;
    return { id: parseInt(id), val, pct, trecho };
  });

  pie.style.background = `conic-gradient(${partes.map(p => p.trecho).join(', ')})`;

  legend.innerHTML = partes.map(p => `
    <div class="legend-item">
      <span class="sw" style="background:${CORES_ORGAO[p.id]};"></span>
      ${ORGAOS[p.id]}
      <span class="val">${fmtBRL(p.val)}</span>
    </div>`).join('');
}

// ─── LISTA DE COMPRAS ─────────────────────────────────────────────────────────
function renderLista() {
  const lista = document.getElementById('lista-ocs');
  const empty = document.getElementById('agenda-empty');
  const total = estado.ocs.length;

  document.getElementById('agenda-badge').textContent = total
    ? `${total} OC${total > 1 ? 's' : ''}` : 'Nenhuma OC';
  empty.style.display = total === 0 ? '' : 'none';

  if (!total) { lista.innerHTML = ''; return; }

  lista.innerHTML = estado.ocs.map(oc => {
    const dias   = diasAte(oc.data_entrega_prevista);
    const status = oc.status_entrega || 'pendente';
    const corBorda = status === 'entregue' ? '#2e7d32' : status === 'atrasada' ? '#c90914' : '#f2972c';
    const pillClass = status === 'entregue' ? 'entregue' : status === 'atrasada' ? 'atrasada' : 'pendente';
    let prazoLabel = '';
    if (status === 'entregue') prazoLabel = 'Entregue';
    else if (dias == null) prazoLabel = 'Sem prazo';
    else if (dias < 0)    prazoLabel = `${Math.abs(dias)}d atraso`;
    else if (dias === 0)  prazoLabel = 'Hoje';
    else if (dias === 1)  prazoLabel = 'Amanhã';
    else                  prazoLabel = `Em ${dias}d`;

    const itensHTML = oc.itens && oc.itens.length
      ? `<table class="oc-itens-inline">
           <thead><tr><th>Descrição</th><th>Qtd</th><th>Valor Unit.</th><th>Total</th></tr></thead>
           <tbody>${oc.itens.map(it => `
             <tr>
               <td>${it.descricao || '—'}</td>
               <td>${it.quantidade != null ? it.quantidade : '—'}</td>
               <td>${fmtBRL(it.valor_unitario)}</td>
               <td>${fmtBRL(it.valor_total)}</td>
             </tr>`).join('')}
           </tbody>
         </table>`
      : '<div class="oc-sem-itens">Nenhum item registrado.</div>';

    const exportBtn = oc.itens && oc.itens.length
      ? `<button class="btn-export-oc" data-oc-id="${oc.id}">↓ Exportar xlsx</button>` : '';

    return `<div class="oc-card" style="border-left-color:${corBorda};">
      <div class="oc-card-header">
        <div class="oc-card-info">
          <div class="oc-num">OC ${oc.numero || oc.id}</div>
          <div class="oc-forn">${oc.fornecedor || '—'}</div>
          <div class="oc-data">${oc.data_entrega_prevista ? 'Entrega: ' + fmtData(oc.data_entrega_prevista) : 'Sem data de entrega'}</div>
        </div>
        <div class="oc-card-actions">
          <span class="status-pill ${pillClass}">${prazoLabel}</span>
          ${exportBtn}
          <select class="oc-status-select" data-oc-id="${oc.id}">
            <option value="pendente"${status==='pendente'?' selected':''}>Pendente</option>
            <option value="atrasada"${status==='atrasada'?' selected':''}>Atrasada</option>
            <option value="entregue"${status==='entregue'?' selected':''}>Entregue</option>
          </select>
        </div>
      </div>
      <div class="oc-itens-wrap">${itensHTML}</div>
    </div>`;
  }).join('');

  // Eventos dinâmicos
  lista.querySelectorAll('.oc-status-select').forEach(sel => {
    sel.addEventListener('change', () => {
      backend.atualizar_status_entrega_oc(JSON.stringify({
        id: parseInt(sel.dataset.ocId), status_entrega: sel.value
      }), () => {
        const oc = estado.ocs.find(o => o.id === parseInt(sel.dataset.ocId));
        if (oc) oc.status_entrega = sel.value;
        renderLista();
        mostrarToast('Status atualizado.');
      });
    });
  });

  lista.querySelectorAll('.btn-export-oc').forEach(btn => {
    btn.addEventListener('click', () => {
      const oc = estado.ocs.find(o => o.id === parseInt(btn.dataset.ocId));
      if (!oc) return;
      const nome = `OC_${oc.numero || oc.id}_itens.xlsx`;
      backend.abrir_dialogo_salvar('Salvar planilha', nome, caminho => {
        if (!caminho) return;
        backend.exportar_oc_xlsx(oc.id, caminho, raw => {
          mostrarToast(JSON.parse(raw).ok ? 'Planilha exportada.' : 'Erro ao exportar.', !JSON.parse(raw).ok);
        });
      });
    });
  });
}

// ─── INCLUIR OC — lote ────────────────────────────────────────────────────────
function resetarFormOC() {
  estado.ocFilaLote = [];
  estado.ocFilaIdx  = 0;
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
    backend.listar_ordens_compra_com_itens(raw => { estado.ocs = JSON.parse(raw); renderLista(); });
    navegarPara('agenda', 'agenda');
    return;
  }

  document.getElementById('oc-conf-titulo').textContent = `OC ${idx + 1} de ${total}`;
  atualizarProgressoOC();

  backend.ler_pdf_oc(estado.ocFilaLote[idx], raw => {
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
        <tr><td>${i+1}</td><td>${it.descricao||'—'}</td>
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
    if (tds.length >= 5) itens.push({
      descricao: tds[1].textContent, quantidade: parseBRL(tds[2].textContent),
      valor_unitario: parseBRL(tds[3].textContent), valor_total: parseBRL(tds[4].textContent),
    });
  });
  const dados = {
    numero: document.getElementById('oc-numero').value.trim(),
    fornecedor: document.getElementById('oc-fornecedor').value.trim(),
    data_emissao: document.getElementById('oc-data-emissao').value || null,
    data_entrega_prevista: document.getElementById('oc-data-entrega').value || null,
    arquivo_pdf: estado.ocFilaLote[estado.ocFilaIdx] || '',
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
    if (f.categoria && nf.categoria !== f.categoria) return false;
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
  estado.filtros.categoria = document.getElementById('filtro-categoria').value;
  estado.filtros.status    = document.getElementById('filtro-status').value;
  estado.filtros.mes       = document.getElementById('filtro-mes').value;
  estado.selecionadas.clear();
  renderNFs();
}

function limparFiltros() {
  ['filtro-orgao','filtro-categoria','filtro-status','filtro-mes'].forEach(id => {
    document.getElementById(id).value = '';
  });
  estado.filtros = { orgao_id: '', categoria: '', status: '', mes: '' };
  estado.selecionadas.clear();
  renderNFs();
}

function renderNFs() {
  const visíveis = nfsFiltradas();
  const naoPagas = visíveis.filter(nf => nf.status_pagamento !== 'pago');
  const pagas    = visíveis.filter(nf => nf.status_pagamento === 'pago');

  document.getElementById('total-nao-pago').textContent = fmtBRL(naoPagas.reduce((s,nf)=>s+(nf.valor||0),0));
  document.getElementById('total-pago').textContent     = fmtBRL(pagas.reduce((s,nf)=>s+(nf.valor||0),0));
  document.getElementById('pag-badge').textContent      = naoPagas.length
    ? `${fmtBRL(naoPagas.reduce((s,nf)=>s+(nf.valor||0),0))} a pagar` : 'Tudo pago';

  // Barra de massa
  const massaBar = document.getElementById('massa-bar');
  massaBar.style.display = estado.selecionadas.size > 0 ? '' : 'none';
  document.getElementById('massa-contagem').textContent =
    `${estado.selecionadas.size} NF${estado.selecionadas.size > 1 ? 's' : ''} selecionada${estado.selecionadas.size > 1 ? 's' : ''}`;

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

  // Bind checkboxes
  document.querySelectorAll('.nf-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const id = parseInt(cb.dataset.nfId);
      cb.checked ? estado.selecionadas.add(id) : estado.selecionadas.delete(id);
      renderNFs();
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
      <div class="num">NF ${nf.numero || '—'}</div>
      <div class="forn">${nf.fornecedor || '—'}</div>
      ${nf.orgao_nome ? `<div class="orgao-tag">${nf.orgao_nome}${nf.categoria ? ' · ' + nf.categoria : ''}</div>` : ''}
    </div>
    <div class="right"><div class="valor">${fmtBRL(nf.valor)}</div>${vencInfo}</div>
    ${btnAcao}
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

// ─── DETALHE NF ───────────────────────────────────────────────────────────────
function abrirDetalheNF(id, viewOrigem) {
  const nf = estado.nfs.find(n => n.id === id);
  if (!nf) return;
  estado.nfAtual        = nf;
  estado.viewAnteriorNF = viewOrigem || 'pagamentos';

  document.getElementById('nf-det-titulo').textContent = `NF ${nf.numero || '—'}`;
  document.getElementById('nf-det-sub').textContent    = nf.fornecedor || '—';

  const btnPago = document.getElementById('btn-marcar-pago-det');
  btnPago.style.display = nf.status_pagamento === 'pago' ? 'none' : '';

  document.getElementById('nf-det-info').innerHTML = `
    <tr><td style="color:#999;font-size:11px;width:120px;">Número</td><td>${nf.numero || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Fornecedor</td><td>${nf.fornecedor || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Emissão</td><td>${fmtData(nf.data_emissao)}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Valor</td><td><strong>${fmtBRL(nf.valor)}</strong></td></tr>
    <tr><td style="color:#999;font-size:11px;">Vencimento</td><td>${fmtData(nf.data_vencimento)}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Pagamento</td><td>${nf.data_pagamento ? fmtData(nf.data_pagamento) : '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Status</td><td><span class="status-pill ${nf.status_pagamento === 'pago' ? 'pago' : 'nao-pago'}">${nf.status_pagamento === 'pago' ? 'pago' : 'não pago'}</span></td></tr>`;

  document.getElementById('nf-det-extra').innerHTML = `
    <tr><td style="color:#999;font-size:11px;width:120px;">Órgão</td><td>${nf.orgao_nome || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Categoria</td><td>${nf.categoria || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Origem</td><td>${nf.origem || '—'}</td></tr>
    <tr><td style="color:#999;font-size:11px;">Incluída em</td><td>${nf.criado_em ? nf.criado_em.slice(0, 16) : '—'}</td></tr>`;

  backend.listar_itens_nf(id, raw => {
    const itens = JSON.parse(raw);
    const tbody = document.getElementById('nf-det-itens');
    const empty = document.getElementById('nf-det-itens-empty');
    if (!itens.length) { tbody.innerHTML = ''; empty.style.display = ''; }
    else {
      empty.style.display = 'none';
      tbody.innerHTML = itens.map((it, i) => `
        <tr>
          <td>${i+1}</td><td>${it.descricao||'—'}</td>
          <td>${it.quantidade!=null?it.quantidade:'—'}</td>
          <td>${fmtBRL(it.valor_unitario)}</td><td>${fmtBRL(it.valor_total)}</td>
          <td>${it.ncm||'—'}</td><td>${it.cfop||'—'}</td>
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

  document.querySelectorAll('.modo-tab').forEach(t => t.classList.toggle('active', t.dataset.modo === 'pdf'));
  document.getElementById('nf-sec-arquivo').style.display  = '';
  document.getElementById('nf-form-dados').style.display   = 'none';
  document.getElementById('nf-sec-itens').style.display    = 'none';
  document.getElementById('nf-lote-progress').style.display = 'none';
  document.getElementById('nf-upload-icon').textContent    = 'PDF';
  document.getElementById('nf-upload-texto').textContent   = 'Clique para selecionar um ou mais arquivos';
  document.getElementById('btn-pular-nf').style.display    = 'none';

  ['nf-numero','nf-fornecedor','nf-data-emissao','nf-valor',
   'nf-data-vencimento','nf-data-pagamento'].forEach(id => document.getElementById(id).value = '');
  document.querySelectorAll('#nf-orgao-tags .tag, #nf-categoria-tags .tag').forEach(t => t.classList.remove('selected'));
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
  document.getElementById('nf-sec-itens').style.display    = modo === 'manual' ? '' : 'none';
  document.getElementById('btn-add-item-nf').style.display = modo === 'manual' ? '' : 'none';
  document.getElementById('nf-itens-tabela').innerHTML     = '';
  document.getElementById('nf-itens-empty').style.display  = modo === 'manual' ? '' : 'none';
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
    ['nf-numero','nf-fornecedor','nf-data-emissao','nf-valor'].forEach(id => {
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
  if (estado.nfFilaLote.length > 1) {
    document.getElementById('nf-conf-titulo').textContent =
      `NF ${estado.nfFilaIdx + 1} de ${estado.nfFilaLote.length}`;
  }
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

  const extrator = modo === 'xml'
    ? (cb => backend.ler_xml_nf(caminho, cb))
    : (cb => backend.ler_pdf_nf(caminho, cb));

  extrator(raw => {
    const d = JSON.parse(raw);
    if (d._erro) { mostrarToast(`Erro: ${d._erro}`, true); avancarNFLote(); return; }
    document.getElementById('nf-numero').value       = d.numero || '';
    document.getElementById('nf-fornecedor').value   = d.fornecedor || '';
    document.getElementById('nf-data-emissao').value = d.data_emissao || '';
    if (d.valor != null) document.getElementById('nf-valor').value =
      Number(d.valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 });

    if (modo === 'xml' && d.itens && d.itens.length) {
      estado.nfFormItens = d.itens;
      renderItensNFForm(false);
      document.getElementById('nf-sec-itens').style.display  = '';
      document.getElementById('nf-itens-label').textContent  = 'Itens extraídos do XML';
    }
    document.getElementById('nf-sec-arquivo').style.display = 'none';
    document.getElementById('nf-form-dados').style.display  = '';
  });
}

function avancarNFLote() {
  estado.nfFilaIdx++;
  // Reseta campos para o próximo arquivo
  ['nf-numero','nf-fornecedor','nf-data-emissao','nf-valor'].forEach(id => document.getElementById(id).value = '');
  estado.nfFormItens = [];
  document.getElementById('nf-sec-itens').style.display = 'none';
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
      <td>${editavel ? `<input type="text" value="${it.descricao||''}" style="width:100%;" oninput="estado.nfFormItens[${i}].descricao=this.value" />` : (it.descricao||'—')}</td>
      <td>${editavel ? `<input type="number" value="${it.quantidade||''}" style="width:70px;" oninput="estado.nfFormItens[${i}].quantidade=parseFloat(this.value)||null" />` : (it.quantidade!=null?it.quantidade:'—')}</td>
      <td>${editavel ? `<input type="text" value="${it.valor_unitario!=null?it.valor_unitario:''}" style="width:80px;" oninput="estado.nfFormItens[${i}].valor_unitario=parseBRL(this.value)" />` : fmtBRL(it.valor_unitario)}</td>
      <td>${editavel ? `<input type="text" value="${it.valor_total!=null?it.valor_total:''}" style="width:80px;" oninput="estado.nfFormItens[${i}].valor_total=parseBRL(this.value)" />` : fmtBRL(it.valor_total)}</td>
      <td>${it.ncm||''}</td>
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
  const catTag     = document.querySelector('#nf-categoria-tags .tag.selected');
  const modo       = estado.nfFormModo;

  const dados = {
    numero:          document.getElementById('nf-numero').value.trim() || null,
    fornecedor:      document.getElementById('nf-fornecedor').value.trim() || null,
    data_emissao:    document.getElementById('nf-data-emissao').value || null,
    valor:           parseBRL(document.getElementById('nf-valor').value),
    orgao_id:        orgaoTag ? parseInt(orgaoTag.dataset.val) : null,
    categoria:       catTag ? catTag.dataset.val : null,
    status_pagamento:statusPago ? 'pago' : 'nao_pago',
    data_vencimento: document.getElementById('nf-data-vencimento').value || null,
    data_pagamento:  statusPago ? (document.getElementById('nf-data-pagamento').value || isoHoje()) : null,
    arquivo_pdf:     modo === 'pdf' ? (estado.nfFormCaminho || '') : '',
    origem:          modo,
    itens:           (modo === 'xml' || modo === 'manual') ? estado.nfFormItens : [],
  };

  if (!dados.valor) { mostrarToast('Informe o valor da NF.', true); return; }

  backend.salvar_nf(JSON.stringify(dados), () => {
    if (estado.nfFilaLote.length > 1) {
      avancarNFLote();
    } else {
      mostrarToast('Nota fiscal salva.');
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
}
