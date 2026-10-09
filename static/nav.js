// ---------------- Navegacao em 6 telas (Hoje, Leads, Campanha, Fontes, WhatsApp, Configuracoes) ----------------
// As telas antigas continuam existindo: cada secao agrupa as suas como abas no topo da pagina.
const NAV_SECTIONS = {
    hoje: {tabs: [['tab-dia', 'Painel do dia'], ['tab-resultados', 'Resultados']]},
    leads: {tabs: [['tab-leads', 'Meus leads'], ['tab-followup', 'Acompanhamento']]},
    campanha: {tabs: [['tab-fila', 'Fila de envio'], ['tab-queue', 'Disparos e histórico'], ['tab-automation', 'Piloto automático']]},
    fontes: {tabs: [['tab-fontes', 'Visão geral'], ['tab-prospector', 'Buscar leads'], ['tab-surgical', 'Prospecção cirúrgica'], ['tab-international', 'Internacional'], ['tab-directories', 'Diretórios']]},
    whatsapp: {tabs: [['tab-whatsapp', 'Central WhatsApp']]},
    config: {tabs: [['tab-settings', 'Configurações']]},
};

function navSectionOf(tabId) {
    return Object.keys(NAV_SECTIONS).find(k => NAV_SECTIONS[k].tabs.some(t => t[0] === tabId)) || 'hoje';
}


// ---------------- Ajuda por tela (fase 4) ----------------
const NAV_HELP = {
    'tab-dia': ['Para que serve', 'É a sua tela de todo dia. Mostra quem chamar hoje, o que o piloto automático fez e se algo precisa de você.', 'Comece pelo bloco "Quem chamar hoje": clique no nome para ver a ficha. Se aparecer um aviso vermelho, resolva primeiro.'],
    'tab-resultados': ['Para que serve', 'Mostra se a campanha está funcionando: quantos e-mails saíram, quantos abriram o esboço, clicaram no portfólio, responderam e fecharam.', 'O sistema não rastreia a abertura do e-mail em si (de propósito). O sinal principal é a pessoa abrir o esboço do site. Compare faixas, segmentos e cidades para saber onde investir.'],
    'tab-leads': ['Para que serve', 'Lista de todas as empresas que o sistema já encontrou, com estágio e contatos.', 'Clique em "Ver ficha e e-mail" para ver o que foi enviado, o histórico e mudar o estágio (respondeu, interessado, reunião, ganho, perdido).'],
    'tab-followup': ['Para que serve', 'Acompanha quem já recebeu e-mail e ainda não respondeu.', 'Os follow-ups saem sozinhos nos dias 3, 7 e 14. Aqui você só confere ou age em um caso específico.'],
    'tab-fila': ['Para que serve', 'Mostra onde estão os leads e quem sai a seguir. Substitui os comandos de console.', 'Use "Aprovar pendentes" quando houver leads prontos, "Devolver à fila" para falhas de rede e "Ler a caixa" para o sistema registrar respostas. "Tirar da fila" impede o envio de um lead específico.'],
    'tab-queue': ['Para que serve', 'Disparos manuais em lote e histórico de tudo que já foi enviado.', 'No dia a dia o piloto automático envia sozinho. Use o histórico para consultar um e-mail: clique em "Ver E-mail" para abrir a ficha.'],
    'tab-automation': ['Para que serve', 'Liga e desliga o piloto automático (envio, busca de leads e leitura da caixa) e define limites.', 'Comece com um limite diário baixo (cerca de 30 e-mails) e aumente aos poucos, para proteger a reputação do seu domínio.'],
    'tab-fontes': ['Para que serve', 'De onde vêm as empresas: a base de CNPJ da Receita (gratuita) e a busca automática na internet.', 'Use "Importar mais leads do CNPJ" quando a fila estiver baixando. A importação leva de 30 minutos a 3 horas em segundo plano. Não faça deploy enquanto ela roda.'],
    'tab-prospector': ['Para que serve', 'Busca manual de empresas por segmento e cidade.', 'O piloto já faz isso sozinho por rodízio de cidades. Use aqui só para um alvo específico.'],
    'tab-surgical': ['Para que serve', 'Busca precisa de empresas específicas, para casos pontuais.', 'Útil quando você já sabe qual empresa ou nicho quer abordar.'],
    'tab-international': ['Para que serve', 'Busca de empresas fora do Brasil.', 'Fora do foco atual (Sul do Brasil). Use apenas se mudar a estratégia.'],
    'tab-directories': ['Para que serve', 'Busca de empresas em diretórios e listas públicas.', 'É uma fonte complementar ao CNPJ. Os resultados são filtrados por estado e cidade.'],
    'tab-whatsapp': ['Para que serve', 'Empresas que têm telefone mas não têm e-mail utilizável: o contato é pelo WhatsApp.', 'Abra a conversa, use o texto sugerido e marque o resultado. Evite ligar ou mandar mensagem fora do horário comercial.'],
    'tab-settings': ['Para que serve', 'Chaves de API, e-mail de envio, dados do remetente, preços e regras do piloto.', 'Use a barra de atalhos no topo para ir direto a uma seção. Chaves e senhas nunca devem ser coladas em conversas: só aqui.'],
};

function helpHidden(tabId) { try { return localStorage.getItem('help_off_' + tabId) === '1'; } catch (e) { return false; } }
function helpSet(tabId, off) { try { localStorage.setItem('help_off_' + tabId, off ? '1' : '0'); } catch (e) {} }

function renderHelp(tabId) {
    const pane = document.getElementById(tabId);
    const h = NAV_HELP[tabId];
    if (!pane || !h) return;
    let box = pane.querySelector(':scope > .tab-help');
    if (!box) { box = document.createElement('div'); box.className = 'tab-help'; pane.insertBefore(box, pane.firstChild); }
    box.innerHTML = '';
    if (helpHidden(tabId)) {
        const b = document.createElement('button'); b.type = 'button'; b.className = 'subnav-btn'; b.textContent = '? Ajuda desta tela';
        b.onclick = () => { helpSet(tabId, false); renderHelp(tabId); };
        box.appendChild(b); return;
    }
    const t = document.createElement('strong'); t.textContent = h[0] + ': '; box.appendChild(t);
    box.appendChild(document.createTextNode(h[1] + ' '));
    const how = document.createElement('div'); how.textContent = h[2]; how.className = 'tab-help-how'; box.appendChild(how);
    const x = document.createElement('button'); x.type = 'button'; x.className = 'subnav-btn'; x.textContent = 'Entendi, esconder';
    x.onclick = () => { helpSet(tabId, true); renderHelp(tabId); };
    box.appendChild(x);
}

function showTab(tabId) {
    const old = document.querySelector('.nav-item[data-tab="' + tabId + '"]');
    if (old) old.click();
}

function renderSubnav(tabId) {
    const sec = navSectionOf(tabId);
    document.querySelectorAll('.nav-sec').forEach(a => a.classList.toggle('active', a.dataset.sec === sec));
    const bar = document.getElementById('subnav');
    if (!bar) return;
    const tabs = NAV_SECTIONS[sec].tabs;
    bar.innerHTML = '';
    bar.style.display = tabs.length > 1 ? 'flex' : 'none';
    tabs.forEach(([id, label]) => {
        const b = document.createElement('button');
        b.type = 'button'; b.textContent = label; b.className = 'subnav-btn' + (id === tabId ? ' active' : '');
        b.onclick = () => showTab(id);
        bar.appendChild(b);
    });
    renderHelp(tabId);
    if (tabId === 'tab-settings') renderSettingsJump();
}

function renderSettingsJump() {
    const bar = document.getElementById('settings-jump');
    if (!bar || bar.dataset.done) return;
    const heads = document.querySelectorAll('#settings-form h3.card-title');
    if (!heads.length) return;
    bar.dataset.done = '1';
    heads.forEach((h, i) => {
        h.id = 'cfg-sec-' + i;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'subnav-btn';
        b.textContent = h.textContent.trim().replace(/\s+/g, ' ').slice(0, 34);
        b.onclick = () => h.scrollIntoView({behavior: 'smooth', block: 'start'});
        bar.appendChild(b);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-sec').forEach(a => a.addEventListener('click', () => showTab(NAV_SECTIONS[a.dataset.sec].tabs[0][0])));
    document.querySelectorAll('.nav-item[data-tab]').forEach(a => a.addEventListener('click', () => renderSubnav(a.dataset.tab)));
    renderSubnav('tab-dia');
});
