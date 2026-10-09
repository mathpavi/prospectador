// ---------------- Fila de envio e Fontes de leads (substituem os comandos do console) ----------------
function opsEl(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
}

async function opsPost(url, body) {
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    return r.json();
}

const GRUPOS = {
    na_fila: ['Na fila de envio', 'Aprovados, vão sair pelo piloto'], cnpj_aguardando_site: ['CNPJ aguardando site', 'O piloto procura o site e aprova sozinho'],
    pendente_ok: ['Pendentes que podem ser aprovados', 'E-mail válido e passam nas checagens'], pendente_barrado: ['Pendentes barrados', 'Alguma checagem reprovou'],
    falhou_temporaria: ['Falhas temporárias', 'Rede ou timeout: podem ser reenviadas'], falhou: ['Falhas definitivas', 'Endereço inexistente etc.'],
    sem_email_com_telefone: ['Sem e-mail, com telefone', 'Seguem pela Central WhatsApp'], sem_contato: ['Sem nenhum contato', 'Não servem'],
    email_ruim: ['E-mail inválido', ''], bloqueado: ['E-mail bloqueado', 'Pediu para sair ou rejeitou'], rejeitado: ['Barrados pelas checagens', 'Fora do perfil'], enviado: ['Já enviados', '']
};

async function loadFila() {
    let d;
    try {
        const r = await fetch('/api/fila');
        d = await r.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        document.getElementById('fila-cards').textContent = 'Não foi possível carregar: ' + e.message;
        return;
    }
    const cards = document.getElementById('fila-cards');
    cards.innerHTML = '';
    ['na_fila', 'cnpj_aguardando_site', 'pendente_ok', 'falhou_temporaria', 'sem_email_com_telefone', 'enviado'].forEach(k => {
        const c = opsEl('div', null, 'dia-kpi'); c.appendChild(opsEl('b', d.grupos[k] || 0)); c.appendChild(opsEl('span', GRUPOS[k][0])); c.title = GRUPOS[k][1]; cards.appendChild(c);
    });
    document.getElementById('fila-aprovar-n').textContent = d.aprovaveis;
    document.getElementById('fila-reenviar-n').textContent = d.temporarias;
    document.getElementById('fila-aprovar').disabled = !d.aprovaveis;
    document.getElementById('fila-reenviar').disabled = !d.temporarias;

    const box = document.getElementById('fila-proximos'); box.innerHTML = '';
    if (!d.fila.proximos.length) box.appendChild(opsEl('p', 'A fila está vazia. Veja "Fontes de leads": a importação do CNPJ e a descoberta de site alimentam a fila.', 'ls-muted'));
    d.fila.proximos.forEach(p => {
        const row = opsEl('div', null, 'dia-lead');
        const left = opsEl('div'); const nm = opsEl('strong', p.empresa); nm.style.cursor = 'pointer'; nm.style.textDecoration = 'underline'; nm.onclick = () => openLeadSheet(p.id); left.appendChild(nm);
        left.appendChild(opsEl('small', `${p.segmento} · ${p.cidade} · faixa: ${p.faixa || 'a definir'} · esboço: ${p.esboco || '-'}`));
        const acts = opsEl('div', null, 'acts'); const b = opsEl('button', 'Tirar da fila');
        b.onclick = async () => { if (!confirm('Tirar ' + p.empresa + ' da fila de envio?')) return; await opsPost('/api/fila/remover/' + p.id); loadFila(); };
        acts.appendChild(b); row.appendChild(left); row.appendChild(acts); box.appendChild(row);
    });
    document.getElementById('fila-total').textContent = d.fila.total;

    const f = d.followups, fb = document.getElementById('fila-followups'); fb.innerHTML = '';
    fb.appendChild(opsEl('p', `Follow-up automático: ${f.ligado ? 'ligado' : 'DESLIGADO (Configurações)'} · devidos agora: ${f.total} · enviados hoje: ${f.enviados_hoje}`, 'ls-muted'));
    f.lista.forEach(x => { const row = opsEl('div', `${x.empresa}: ${x.passo === 'aviso' ? 'aviso de vencimento do esboço' : 'passo ' + x.passo + ' de 3'}`); row.style.cssText = 'cursor:pointer;padding:6px 0;border-top:1px solid rgba(255,255,255,.08);font-size:.9rem'; row.onclick = () => openLeadSheet(x.id); fb.appendChild(row); });
    document.getElementById('fila-caixa-estado').textContent = d.caixa_ligada ? 'Leitura automática da caixa: ligada' : 'Leitura automática da caixa: desligada (ligue em Configurações depois de testar aqui)';
}

async function filaAcao(url, rotulo, confirmar) {
    if (confirmar && !confirm(confirmar)) return;
    try {
        const j = await opsPost(url);
        showToast(rotulo + ': ' + (j.aprovados !== undefined ? j.aprovados + ' lead(s) aprovado(s)' : j.devolvidos !== undefined ? j.devolvidos + ' lead(s) devolvido(s) à fila' : 'feito'));
    } catch (e) {
        showToast('Não foi possível: ' + e.message, 'error');
    }
    loadFila();
}

async function lerCaixa(simular) {
    const out = document.getElementById('fila-caixa-saida');
    out.textContent = 'Lendo a caixa de entrada…';
    const j = await opsPost('/api/caixa/ler', {simular});
    out.innerHTML = '';
    if (!j.ok) { out.textContent = 'Não consegui ler a caixa: ' + j.erro + ' (confira usuário e senha do e-mail em Configurações).'; return; }
    out.appendChild(opsEl('p', `${j.simulacao ? 'SIMULAÇÃO (nada foi alterado) · ' : ''}Mensagens lidas: ${j.lidas} · relevantes: ${j.novas}`));
    j.acoes.forEach(a => out.appendChild(opsEl('div', '• ' + a, 'ls-muted')));
    if (!j.simulacao) loadFila();
}

// ---------------- Fontes ----------------
let fontesTimer = null;
async function loadFontes() {
    let d;
    try {
        const r = await fetch('/api/fontes');
        d = await r.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        document.getElementById('fontes-cnpj').textContent = 'Não foi possível carregar: ' + e.message;
        return;
    }
    const c = d.cnpj, box = document.getElementById('fontes-cnpj'); box.innerHTML = '';
    const line = (t) => box.appendChild(opsEl('p', t, 'ls-line'));
    line(c.rodando ? '🟢 Importação EM ANDAMENTO' + (c.progresso_download !== null ? ` (baixando arquivo: ${c.progresso_download}%)` : '') : '⚪ Nenhuma importação rodando');
    line(`Leads do CNPJ no sistema: ${c.leads_do_cnpj} · aguardando o site ser procurado: ${c.aguardando_site} · aprovados: ${c.aprovados} · já enviados: ${c.enviados}`);
    if (c.estagio && c.estagio.empresas_no_banco !== undefined) line(`Base lida da Receita: ${c.estagio.empresas_no_banco.toLocaleString('pt-BR')} empresas dos seus segmentos · ainda não trazidas ao sistema: ${c.estagio.ainda_nao_importadas.toLocaleString('pt-BR')}`);
    if (c.ultima_linha) line('Último passo: ' + c.ultima_linha);
    document.getElementById('fontes-importar').disabled = !!c.rodando;
    if (fontesTimer) clearTimeout(fontesTimer);
    if (c.rodando) fontesTimer = setTimeout(() => { if (document.getElementById('tab-fontes').classList.contains('active')) loadFontes(); }, 8000);

    const b = d.busca, bb = document.getElementById('fontes-busca'); bb.innerHTML = '';
    const bl = (t) => bb.appendChild(opsEl('p', t, 'ls-line'));
    bl(`Busca automática: ${b.ligada ? 'ligada' : 'DESLIGADA'} · buscas hoje: ${b.buscas_hoje} de ${b.teto_dia} · fila de envio: ${b.estoque_fila} de ${b.meta_fila} (a busca descansa quando a fila enche)`);
    if (b.buscadores_fora.length) b.buscadores_fora.forEach(x => bb.appendChild(opsEl('div', `⛔ ${x.nome}: ${x.motivo} (tenta de novo até ${x.ate})`, 'dia-warn')));
    else bl('Todos os buscadores configurados estão respondendo.');
    if (b.aviso) bb.appendChild(opsEl('div', b.aviso, 'dia-warn'));
    if (b.em_descanso.length) { bl('Alvos em descanso (saturados):'); b.em_descanso.forEach(x => bb.appendChild(opsEl('div', `${x.segmento} · ${x.regiao} · ${x.tipo}: ${x.motivo} (volta em ${x.volta_em})`, 'ls-muted'))); }
}

async function importarCnpj() {
    const n = document.getElementById('fontes-limite').value;
    if (!confirm(`Importar até ${n} leads novos do CNPJ da Receita? A leitura dos arquivos leva de 30 minutos a 3 horas e roda em segundo plano (pode fechar a tela).`)) return;
    const j = await opsPost('/api/fontes/cnpj/importar', {limite: parseInt(n, 10)});
    showToast(j.message, j.success ? 'success' : 'error');
    setTimeout(loadFontes, 1500);
}
