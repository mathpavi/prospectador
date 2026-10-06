// ---------------- U1: Painel do Dia ----------------
function diaEl(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
}

async function diaSetStage(id, stage) {
    try {
        const r = await fetch(`/api/prospects/${id}/stage`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({stage})});
        const j = await r.json();
        if (!j.success) throw new Error(j.error || 'erro');
        showToast('Estágio atualizado: ' + stage);
        loadDia();
    } catch (e) {
        showToast('Não foi possível atualizar: ' + e.message, 'error');
    }
}

async function loadDia() {
    let d;
    try {
        const r = await fetch('/api/dia');
        d = await r.json();
        if (d.error) throw new Error(d.error);
    } catch (e) {
        const box = document.getElementById('dia-chamar');
        if (box) box.textContent = 'Não foi possível carregar o painel: ' + e.message;
        return;
    }
    document.getElementById('dia-hora').textContent = 'Atualizado às ' + d.gerado_em;
    const k = d.kpi, kp = document.getElementById('dia-kpis');
    kp.innerHTML = '';
    [[`${k.enviados_hoje}/${k.limite_hoje}`, 'e-mails hoje'], [k.followups_hoje, 'follow-ups hoje'], [k.respostas_24h, 'respostas (24 h)'],
     [`${k.whatsapp_hoje}/${k.meta_whatsapp}`, 'WhatsApp hoje'], [k.esbocos_24h, 'esboços (24 h)'], [k.interessados, 'interessados'], [k.ganhos, 'ganhos']].forEach(([v, l]) => {
        const c = diaEl('div', null, 'dia-kpi'); c.appendChild(diaEl('b', v)); c.appendChild(diaEl('span', l)); kp.appendChild(c);
    });
    const av = document.getElementById('dia-avisos');
    av.innerHTML = '';
    d.avisos.forEach(a => av.appendChild(diaEl('div', a, 'dia-warn')));
    document.getElementById('dia-avisos-box').style.display = d.avisos.length ? '' : 'none';

    const ch = document.getElementById('dia-chamar');
    ch.innerHTML = '';
    if (!d.chamar.length) ch.appendChild(diaEl('span', 'Ninguém esquentou ainda. Quando alguém responder, abrir o esboço ou for marcado como interessado, aparece aqui.'));
    d.chamar.forEach(l => {
        const row = diaEl('div', null, 'dia-lead');
        const left = diaEl('div');
        const t = diaEl('div'); t.appendChild(diaEl('strong', l.empresa)); t.appendChild(diaEl('span', '  ' + l.segmento)); left.appendChild(t);
        left.appendChild(diaEl('small', `${l.motivo} · estágio: ${l.estagio}${l.email ? ' · ' + l.email : ''}${l.telefone ? ' · ' + l.telefone : ''}`));
        if (l.resposta) left.appendChild(diaEl('small', '“' + l.resposta + '”'));
        const acts = diaEl('div', null, 'acts');
        if (l.whatsapp) { const a = diaEl('a', 'WhatsApp'); a.href = l.whatsapp; a.target = '_blank'; a.rel = 'noopener'; acts.appendChild(a); }
        if (l.email) { const a = diaEl('a', 'E-mail'); a.href = 'mailto:' + l.email; acts.appendChild(a); }
        if (l.esboco) { const a = diaEl('a', 'Esboço'); a.href = l.esboco; a.target = '_blank'; a.rel = 'noopener'; acts.appendChild(a); }
        [['respondeu', 'Respondeu'], ['interessado', 'Interessado'], ['reuniao', 'Reunião'], ['ganho', 'Ganho'], ['perdido', 'Perdido']].forEach(([s, label]) => {
            const b = diaEl('button', label); b.onclick = () => diaSetStage(l.id, s); acts.appendChild(b);
        });
        row.appendChild(left); row.appendChild(acts); ch.appendChild(row);
    });

    const sv = document.getElementById('dia-sistema');
    sv.innerHTML = '';
    const s = d.sistema;
    [['Piloto de envio', s.piloto_envio], ['Piloto de busca', s.piloto_busca], ['Follow-up', s.followup], ['Caixa de entrada', s.caixa_entrada], ['Alertas', s.alertas], ['Esboço no e-mail', s.esbocos_no_email], ['SMTP', s.smtp]]
        .forEach(([n, on]) => sv.appendChild(diaEl('span', `${n}: ${on ? 'ligado' : 'desligado'}`, 'dia-pill' + (on ? '' : ' off'))));
    const fila = diaEl('div', `Fila de envio: ${s.fila_aprovados} aprovado(s) · ${s.pendentes_com_email} pendente(s) com e-mail aguardando aprovação`);
    fila.style.marginTop = '10px';
    sv.appendChild(fila);

    const fn = document.getElementById('dia-funil');
    fn.innerHTML = '';
    Object.entries(d.funil).sort((a, b) => b[1] - a[1]).forEach(([st, n]) => {
        const sp = diaEl('span'); sp.appendChild(diaEl('strong', n)); sp.appendChild(document.createTextNode(' ' + st)); fn.appendChild(sp);
    });
}

document.addEventListener('DOMContentLoaded', () => { if (typeof loadDia === 'function') loadDia(); });
