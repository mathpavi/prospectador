// ---------------- Ficha do lead + tela Resultados ----------------
function crmEl(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
}

const CRM_STAGES = [['respondeu', 'Respondeu'], ['interessado', 'Interessado'], ['reuniao', 'Reunião'], ['ganho', 'Ganho'], ['perdido', 'Perdido']];

async function crmSetStage(id, stage) {
    let body = {stage};
    if (stage === 'ganho') {
        const v = window.prompt('Valor do negócio em R$ (só números, ex.: 1920):', '');
        if (v === null) return;
        body.deal_value = parseFloat(String(v).replace(/\./g, '').replace(',', '.')) || null;
        const o = window.prompt('De onde veio? (email, whatsapp, telefone ou indicacao):', 'email');
        body.source = o || 'email';
    }
    try {
        const r = await fetch(`/api/prospects/${id}/stage`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const j = await r.json();
        if (!j.success) throw new Error(j.error || 'erro');
        showToast('Estágio atualizado.');
        openLeadSheet(id);
        if (typeof loadDia === 'function') loadDia();
    } catch (e) {
        showToast('Não foi possível atualizar: ' + e.message, 'error');
    }
}

async function openLeadSheet(id) {
    const modal = document.getElementById('lead-sheet-modal');
    const body = document.getElementById('lead-sheet-body');
    if (!modal || !body) return;
    body.innerHTML = '';
    body.appendChild(crmEl('p', 'Carregando…'));
    modal.classList.add('active');
    let d;
    try {
        const r = await fetch('/api/lead/' + id);
        d = await r.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        body.innerHTML = '';
        body.appendChild(crmEl('p', 'Não consegui abrir a ficha: ' + e.message));
        return;
    }
    document.getElementById('lead-sheet-title').textContent = d.empresa;
    body.innerHTML = '';
    const sec = (titulo) => { const s = crmEl('div', null, 'ls-sec'); s.appendChild(crmEl('h4', titulo)); body.appendChild(s); return s; };

    const head = sec('Resumo');
    const chips = crmEl('div', null, 'ls-chips');
    [d.segmento, d.regiao, 'Estágio: ' + d.estagio_nome, d.faixa_nome ? 'Faixa: ' + d.faixa_nome : '', d.enviado_em ? 'Enviado em ' + d.enviado_em : 'Ainda não enviado']
        .filter(Boolean).forEach(t => chips.appendChild(crmEl('span', t, 'ls-chip')));
    head.appendChild(chips);
    const c = d.contagens;
    head.appendChild(crmEl('p', `E-mails: ${c.emails} · Follow-ups: ${c.followups} · Respostas: ${c.respostas} · Cliques no portfólio: ${c.cliques} · Aberturas do esboço: ${c.aberturas_esboco}`, 'ls-muted'));
    const acts = crmEl('div', null, 'ls-acts');
    CRM_STAGES.forEach(([s, n]) => { const b = crmEl('button', n); b.onclick = () => crmSetStage(d.id, s); acts.appendChild(b); });
    head.appendChild(acts);

    const ct = sec('Contatos');
    const line = (k, v, href) => { if (!v) return; const p = crmEl('p', null, 'ls-line'); p.appendChild(crmEl('b', k + ': ')); if (href) { const a = crmEl('a', v); a.href = href; a.target = '_blank'; a.rel = 'noopener'; p.appendChild(a); } else p.appendChild(document.createTextNode(v)); ct.appendChild(p); };
    line('E-mail', d.email, d.email ? 'mailto:' + d.email : '');
    line('WhatsApp', d.whatsapp, d.whatsapp ? 'https://wa.me/55' + d.whatsapp.replace(/\D/g, '').replace(/^55/, '') : '');
    line('Telefone', d.telefone);
    line('Site', d.site, d.site && d.site.startsWith('http') ? d.site : '');

    if (d.esboco) {
        const e = sec('Esboço do site');
        const st = d.esboco.status === 'ready' ? (d.esboco.expirado ? 'vencido' : 'no ar') : 'não liberado';
        e.appendChild(crmEl('p', `Situação: ${st}${d.esboco.vence ? ' · vence em ' + d.esboco.vence : ''} · aberturas: ${d.esboco.aberturas}${d.esboco.ultima ? ' (última em ' + d.esboco.ultima + ')' : ''}`, 'ls-line'));
        if (d.esboco.motivo) e.appendChild(crmEl('p', 'Motivo: ' + d.esboco.motivo, 'ls-muted'));
        if (d.esboco.url) { const a = crmEl('a', 'Abrir o esboço'); a.href = d.esboco.url; a.target = '_blank'; a.rel = 'noopener'; e.appendChild(a); }
        if (d.esboco.status === 'ready') {
            const pb = crmEl('button', 'Manter no ar por mais 7 dias'); pb.style.marginLeft = '10px';
            pb.onclick = async () => { const j = await (await fetch('/api/esboco/prorrogar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prospect_id: d.id, dias: 7})})).json(); showToast(j.success ? 'Esboço prorrogado até ' + j.vence : (j.message || 'Não foi possível'), j.success ? 'success' : 'error'); openLeadSheet(d.id); };
            e.appendChild(pb);
        }
    }

    const em = sec('E-mail enviado');
    if (d.corpo) {
        em.appendChild(crmEl('p', d.assunto, 'ls-line')).style.fontWeight = '600';
        const pre = crmEl('pre', d.corpo, 'ls-email');
        em.appendChild(pre);
        const cp = crmEl('button', 'Copiar texto'); cp.onclick = () => { navigator.clipboard.writeText('Assunto: ' + d.assunto + '\n\n' + d.corpo); showToast('Texto copiado.'); }; em.appendChild(cp);
    } else {
        em.appendChild(crmEl('p', 'Ainda não há texto de e-mail para este lead.', 'ls-muted'));
    }

    const tl = sec('Linha do tempo');
    if (!d.linha_do_tempo.length) tl.appendChild(crmEl('p', 'Nada registrado ainda.', 'ls-muted'));
    d.linha_do_tempo.forEach(x => {
        const row = crmEl('div', null, 'ls-tl');
        row.appendChild(crmEl('span', x.quando, 'ls-when'));
        row.appendChild(crmEl('span', `${x.icone} ${x.texto}${x.detalhe ? ' — ' + x.detalhe : ''}`));
        tl.appendChild(row);
    });
    if (d.notas) { const n = sec('Notas do sistema'); n.appendChild(crmEl('p', d.notas, 'ls-muted')); }
}

function closeLeadSheet() {
    const m = document.getElementById('lead-sheet-modal');
    if (m) m.classList.remove('active');
}

// ---------------- Resultados ----------------
async function loadResultados() {
    const dias = (document.getElementById('res-dias') || {value: '30'}).value;
    let d;
    try {
        const r = await fetch('/api/resultados?dias=' + dias);
        d = await r.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        const k = document.getElementById('res-kpis');
        if (k) k.textContent = 'Não foi possível carregar: ' + e.message;
        return;
    }
    const k = d.kpi, t = k.taxas;
    const box = document.getElementById('res-kpis');
    box.innerHTML = '';
    [[k.enviados, 'e-mails enviados'], [k.followups, 'follow-ups'], [`${k.esboco_aberto} (${t.esboco_aberto}%)`, 'abriram o esboço'], [`${k.cliques} (${t.cliques}%)`, 'clicaram no portfólio'],
     [`${k.respostas} (${t.respostas}%)`, 'responderam'], [`${k.interessados} (${t.interessados}%)`, 'interessados'], [k.ganhos, 'ganhos'],
     [`${k.pediram_sair} (${t.pediram_sair}%)`, 'pediram para sair'], [`${k.rejeitados} (${t.rejeitados}%)`, 'e-mails rejeitados']].forEach(([v, l]) => {
        const c = crmEl('div', null, 'dia-kpi'); c.appendChild(crmEl('b', v)); c.appendChild(crmEl('span', l)); box.appendChild(c);
    });
    const table = (id, rows, firstCol) => {
        const el = document.getElementById(id); el.innerHTML = '';
        if (!rows.length) { el.appendChild(crmEl('p', 'Sem envios neste período.', 'ls-muted')); return; }
        const tb = crmEl('table', null, 'res-table');
        const hr = crmEl('tr'); [firstCol, 'Enviados', 'Abriram esboço', 'Responderam', 'Interessados', 'Ganhos'].forEach(h => hr.appendChild(crmEl('th', h))); tb.appendChild(hr);
        rows.forEach(r => { const tr = crmEl('tr'); [r.nome, r.enviados, r.esboco_aberto, r.respostas, r.interessados, r.ganhos].forEach(v => tr.appendChild(crmEl('td', v))); tb.appendChild(tr); });
        el.appendChild(tb);
    };
    table('res-faixa', d.por_faixa, 'Faixa'); table('res-segmento', d.por_segmento, 'Segmento'); table('res-cidade', d.por_cidade, 'Cidade');
    const sr = document.getElementById('res-serie'); sr.innerHTML = '';
    const max = Math.max(1, ...d.serie.map(x => x.enviados));
    d.serie.forEach(x => {
        const col = crmEl('div', null, 'res-col');
        const bar = crmEl('div', null, 'res-bar'); bar.style.height = Math.max(3, Math.round(70 * x.enviados / max)) + 'px'; bar.title = `${x.enviados} enviados, ${x.respostas} respostas`;
        col.appendChild(crmEl('small', x.enviados)); col.appendChild(bar); col.appendChild(crmEl('small', x.dia)); sr.appendChild(col);
    });
    const fd = document.getElementById('res-atividade'); fd.innerHTML = '';
    if (!d.atividade.length) fd.appendChild(crmEl('p', 'Nenhuma resposta, clique ou mudança de estágio neste período ainda.', 'ls-muted'));
    d.atividade.forEach(a => {
        const row = crmEl('div', null, 'ls-tl'); row.style.cursor = 'pointer';
        row.appendChild(crmEl('span', a.quando, 'ls-when'));
        row.appendChild(crmEl('span', `${a.icone} ${a.empresa}: ${a.texto}${a.detalhe ? ' — ' + a.detalhe : ''}`));
        row.onclick = () => openLeadSheet(a.id);
        fd.appendChild(row);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const m = document.getElementById('lead-sheet-modal');
    if (m) m.addEventListener('click', ev => { if (ev.target === m) closeLeadSheet(); });
});
