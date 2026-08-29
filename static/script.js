// Global State
let currentTab = 'tab-prospector';
let searchInterval = null;
let queueInterval = null;
let currentFilter = 'all';
let allProspects = [];
let systemSettings = {};



// Helper to format WhatsApp draft dynamic text based on email sent status
function getFormattedWhatsappDraft(lead) {
    let draft = lead.whatsapp_draft || '';
    if (lead.status === 'sent' || lead.sent_at) {
        const phrase = "Te enviei um e-mail mas não sei se já viu... ";
        if (draft.includes("Olá, tudo bem?")) {
            draft = draft.replace("Olá, tudo bem?", "Olá, tudo bem? Te enviei um e-mail mas não sei se já viu... ");
        } else if (draft.includes("Olá!")) {
            draft = draft.replace("Olá!", "Olá! Te enviei um e-mail mas não sei se já viu... ");
        } else {
            draft = phrase + draft;
        }
    }
    return draft;
}

// Helper to format date and time in Portuguese
function formatDateTime(dateStr) {
    if (!dateStr) return 'Não informado';
    try {
        const parts = dateStr.split(' ');
        if (parts.length === 2) {
            const [year, month, day] = parts[0].split('-');
            const [hour, minute] = parts[1].split(':');
            return `${day}/${month}/${year} às ${hour}:${minute}`;
        }
        const d = new Date(dateStr);
        if (!isNaN(d.getTime())) {
            const day = String(d.getDate()).padStart(2, '0');
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const year = d.getFullYear();
            const hour = String(d.getHours()).padStart(2, '0');
            const minute = String(d.getMinutes()).padStart(2, '0');
            return `${day}/${month}/${year} às ${hour}:${minute}`;
        }
        return dateStr;
    } catch(e) {
        return dateStr;
    }
}

// DOM Elements
const navItems = document.querySelectorAll('.nav-item');
const tabPanes = document.querySelectorAll('.tab-pane');
const toastContainer = document.getElementById('toast-container');

// Toast Notification Helper
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button style="background:none;border:none;color:var(--text-secondary);cursor:pointer;margin-left:10px;">&times;</button>
    `;
    
    // Close on button click
    toast.querySelector('button').addEventListener('click', () => {
        toast.remove();
    });
    
    toastContainer.appendChild(toast);
    
    // Auto remove
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}

// Tab Switching
navItems.forEach(item => {
    item.addEventListener('click', () => {
        const tabId = item.getAttribute('data-tab');
        
        navItems.forEach(nav => nav.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        
        item.classList.add('active');
        document.getElementById(tabId).classList.add('active');
        
        currentTab = tabId;
        
        // Tab specific loading
        if (tabId === 'tab-leads') {
            loadLeads();
        } else if (tabId === 'tab-queue') {
            loadQueueStatus();
            loadSentHistory();
        } else if (tabId === 'tab-followup') {
            loadFollowupList();
        } else if (tabId === 'tab-settings') {
            loadSettings();
        } else if (tabId === 'tab-surgical') {
            loadSurgicalTab();
        } else if (tabId === 'tab-international') {
            loadInternationalTab();
        } else if (tabId === 'tab-automation') {
            loadAutomationTab();
        }
        
        // Clear automation/importer polling when leaving automation tab
        if (tabId !== 'tab-automation') {
            if (automationInterval) {
                clearInterval(automationInterval);
                automationInterval = null;
            }
            if (importerInterval) {
                clearInterval(importerInterval);
                importerInterval = null;
            }
        }
    });
});

// ==========================================
// 1. SETTINGS TAB
// ==========================================
const settingsForm = document.getElementById('settings-form');

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        systemSettings = data;
        
        // Populate form
        for (const key in data) {
            const input = document.getElementById(key);
            if (input) {
                input.value = data[key];
            }
        }
    } catch (error) {
        showToast('Erro ao carregar configurações.', 'error');
    }
}

settingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(settingsForm);
    const settings = {};
    formData.forEach((value, key) => {
        settings[key] = value;
    });
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        showToast(data.message, 'success');
        
        // Reload settings (in case passwords were obfuscated)
        loadSettings();
    } catch (error) {
        showToast('Erro ao salvar configurações.', 'error');
    }
});

// Test SMTP Settings
const testSmtpBtn = document.getElementById('test-smtp-btn');
testSmtpBtn.addEventListener('click', async () => {
    const testRecipientInput = document.getElementById('smtp_test_recipient');
    const testEmail = testRecipientInput ? testRecipientInput.value.trim() : '';
    
    if (!testEmail) {
        showToast('Por favor, informe o e-mail do destinatário para o teste.', 'error');
        return;
    }
    
    testSmtpBtn.disabled = true;
    testSmtpBtn.textContent = '🧪 Testando Conexão...';
    
    const settings = {
        smtp_host: document.getElementById('smtp_host').value,
        smtp_port: document.getElementById('smtp_port').value,
        smtp_user: document.getElementById('smtp_user').value,
        smtp_password: document.getElementById('smtp_password').value,
        smtp_security: document.getElementById('smtp_security').value,
        sender_name: document.getElementById('sender_name').value,
        test_email: testEmail
    };
    
    try {
        const response = await fetch('/api/smtp/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        showToast('Erro de conexão ao testar servidor SMTP.', 'error');
    } finally {
        testSmtpBtn.disabled = false;
        testSmtpBtn.textContent = 'Enviar E-mail de Teste';
    }
});

// ==========================================
// 2. PROSPECTOR (SEARCH) TAB
// ==========================================
const searchForm = document.getElementById('search-form');
const startSearchBtn = document.getElementById('start-search-btn');
const consoleLogs = document.getElementById('console-logs');
const consoleStatusDot = document.getElementById('console-status-dot');

// Conditional dropdown / custom input handler for Segment
const segmentSelect = document.getElementById('segment-select');
const segmentCustomGroup = document.getElementById('segment-custom-group');
const segmentCustomInput = document.getElementById('segment-custom');
const segmentHiddenInput = document.getElementById('segment');

if (segmentSelect) {
    segmentSelect.addEventListener('change', () => {
        if (segmentSelect.value === 'custom') {
            segmentCustomGroup.style.display = 'block';
            segmentHiddenInput.value = segmentCustomInput.value;
        } else {
            segmentCustomGroup.style.display = 'none';
            segmentHiddenInput.value = segmentSelect.value;
        }
    });
}

if (segmentCustomInput) {
    segmentCustomInput.addEventListener('input', () => {
        if (segmentSelect.value === 'custom') {
            segmentHiddenInput.value = segmentCustomInput.value;
        }
    });
}

// ==========================================
// GEOLOCATION PICKER (IBGE API)
// ==========================================
const stateSelect = document.getElementById('state-select');
const citySelect = document.getElementById('city-select');
const radiusSelect = document.getElementById('radius-select');
const radiusGroup = document.getElementById('radius-group');

const hiddenRegion = document.getElementById('region');
const hiddenStateUf = document.getElementById('state_uf');
const hiddenCityName = document.getElementById('city_name');
const hiddenRadiusKm = document.getElementById('radius_km');

async function loadStates() {
    try {
        const response = await fetch('https://servicodados.ibge.gov.br/api/v1/localidades/estados');
        const states = await response.json();
        
        // Sort states alphabetically by name
        states.sort((a, b) => a.nome.localeCompare(b.nome));
        
        stateSelect.innerHTML = '<option value="">Selecione um Estado...</option>';
        states.forEach(state => {
            const option = document.createElement('option');
            option.value = state.sigla;
            option.textContent = `${state.nome} (${state.sigla})`;
            stateSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Erro ao carregar estados do IBGE:', error);
        stateSelect.innerHTML = '<option value="">Erro ao carregar estados</option>';
    }
}

async function loadCities(uf) {
    if (!uf) {
        citySelect.innerHTML = '<option value="">Selecione um Estado...</option>';
        citySelect.disabled = true;
        if (radiusGroup) radiusGroup.style.display = 'none';
        updateHiddenInputs();
        return;
    }
    
    citySelect.disabled = true;
    citySelect.innerHTML = '<option value="">Carregando cidades...</option>';
    
    try {
        const response = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/estados/${uf}/municipios`);
        const cities = await response.json();
        
        // Sort cities alphabetically by name
        cities.sort((a, b) => a.nome.localeCompare(b.nome));
        
        citySelect.innerHTML = '<option value="">Estado Inteiro (Todo o Estado)</option>';
        cities.forEach(city => {
            const option = document.createElement('option');
            option.value = city.nome;
            option.textContent = city.nome;
            citySelect.appendChild(option);
        });
        citySelect.disabled = false;
    } catch (error) {
        console.error('Erro ao carregar cidades do IBGE:', error);
        citySelect.innerHTML = '<option value="">Erro ao carregar cidades</option>';
    }
    updateHiddenInputs();
}

function updateHiddenInputs() {
    const uf = stateSelect.value;
    const city = citySelect.value;
    const radius = radiusSelect ? radiusSelect.value : '0';
    
    hiddenStateUf.value = uf;
    hiddenCityName.value = city;
    hiddenRadiusKm.value = radius;
    
    if (uf) {
        if (city) {
            if (parseInt(radius) > 0) {
                hiddenRegion.value = `${city} - ${uf} (+${radius}km)`;
            } else {
                hiddenRegion.value = `${city} - ${uf}`;
            }
            if (radiusGroup) radiusGroup.style.display = 'block';
        } else {
            hiddenRegion.value = uf;
            if (radiusGroup) radiusGroup.style.display = 'none';
        }
    } else {
        hiddenRegion.value = '';
        if (radiusGroup) radiusGroup.style.display = 'none';
    }
}

if (stateSelect) {
    stateSelect.addEventListener('change', () => {
        loadCities(stateSelect.value);
    });
}

if (citySelect) {
    citySelect.addEventListener('change', () => {
        updateHiddenInputs();
    });
}

if (radiusSelect) {
    radiusSelect.addEventListener('change', () => {
        updateHiddenInputs();
    });
}

// Call on startup
loadStates();

searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const segment = document.getElementById('segment').value;
    const region = document.getElementById('region').value;
    const max_results = document.getElementById('max_results').value;
    const state_uf = document.getElementById('state_uf').value;
    const city_name = document.getElementById('city_name').value;
    const radius_km = document.getElementById('radius_km').value;
    const source_mode = document.getElementById('source-mode-select') ? document.getElementById('source-mode-select').value : 'organic';
    
    if (!state_uf) {
        showToast('Por favor, selecione pelo menos um Estado.', 'error');
        return;
    }
    
    startSearchBtn.disabled = true;
    startSearchBtn.innerHTML = `
        <span class="console-dot active" style="display:inline-block; margin-right:8px;"></span>
        Rastreando Empresas...
    `;
    consoleStatusDot.classList.add('active');
    
    try {
        const response = await fetch('/api/prospect/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ segment, region, max_results, state_uf, city_name, radius_km, source_mode })
        });
        const data = await response.json();
        
        if (response.ok) {
            showToast(data.message, 'success');
            startPollingLogs();
        } else {
            showToast(data.error || 'Erro ao iniciar busca.', 'error');
            startSearchBtn.disabled = false;
            startSearchBtn.textContent = 'Rodar Agente de Prospecção';
            consoleStatusDot.classList.remove('active');
        }
    } catch (error) {
        showToast('Erro de rede ao disparar buscador.', 'error');
        startSearchBtn.disabled = false;
        startSearchBtn.textContent = 'Rodar Agente de Prospecção';
        consoleStatusDot.classList.remove('active');
    }
});

function startPollingLogs() {
    if (searchInterval) clearInterval(searchInterval);
    
    searchInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/prospect/status');
            const data = await response.json();
            
            // Render logs
            consoleLogs.innerHTML = '';
            if (data.logs.length === 0) {
                consoleLogs.innerHTML = `
                    <div class="log-item">
                        <span class="log-time">[Processo]</span>
                        <span class="log-msg">Iniciando análise dos sites...</span>
                    </div>
                `;
            } else {
                data.logs.forEach(log => {
                    const item = document.createElement('div');
                    item.className = 'log-item';
                    item.innerHTML = `
                        <span class="log-time">[${log.time}]</span>
                        <span class="log-msg">${log.message}</span>
                    `;
                    consoleLogs.appendChild(item);
                });
            }
            
            // Auto scroll
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
            
            // Check status
            if (!data.is_searching) {
                clearInterval(searchInterval);
                searchInterval = null;
                
                startSearchBtn.disabled = false;
                startSearchBtn.textContent = 'Rodar Agente de Prospecção';
                consoleStatusDot.classList.remove('active');
                showToast('Varredura concluída com sucesso!', 'success');
                
                // Add system done message
                const item = document.createElement('div');
                item.className = 'log-item';
                item.innerHTML = `
                    <span class="log-time">[Fim]</span>
                    <span class="log-msg" style="color:var(--success);">Processo terminado. Revise os resultados na aba "Meus Leads"!</span>
                `;
                consoleLogs.appendChild(item);
                consoleLogs.scrollTop = consoleLogs.scrollHeight;
            }
        } catch (error) {
            console.error('Erro ao buscar logs:', error);
        }
    }, 1500);
}

document.getElementById('clear-logs-btn').addEventListener('click', () => {
    consoleLogs.innerHTML = `
        <div class="log-item">
            <span class="log-time">[Terminal]</span>
            <span class="log-msg">Logs limpos.</span>
        </div>
    `;
});

// Check on load if search is already running
async function checkActiveSearch() {
    try {
        const response = await fetch('/api/prospect/status');
        const data = await response.json();
        if (data.is_searching) {
            startSearchBtn.disabled = true;
            startSearchBtn.innerHTML = `
                <span class="console-dot active" style="display:inline-block; margin-right:8px;"></span>
                Rastreando Empresas...
            `;
            consoleStatusDot.classList.add('active');
            startPollingLogs();
        }
    } catch (e) {
        console.error(e);
    }
}
checkActiveSearch();

// ==========================================
// 3. LEADS (DASHBOARD) TAB
// ==========================================
const filterTags = document.querySelectorAll('.filter-tag');
const leadsContainer = document.getElementById('leads-container');

filterTags.forEach(tag => {
    tag.addEventListener('click', () => {
        filterTags.forEach(t => t.classList.remove('active'));
        tag.classList.add('active');
        currentFilter = tag.getAttribute('data-filter');
        loadLeads();
    });
});

async function loadLeads() {
    try {
        const url = currentFilter === 'all' ? '/api/prospects' : `/api/prospects?status=${currentFilter}`;
        const response = await fetch(url);
        const data = await response.json();
        
        allProspects = data.prospects;
        
        // Update stats
        document.getElementById('stats-total').textContent = data.stats.total;
        document.getElementById('stats-pending').textContent = data.stats.pending;
        document.getElementById('stats-approved').textContent = data.stats.approved;
        document.getElementById('stats-sent').textContent = data.stats.sent;
        document.getElementById('stats-failed').textContent = data.stats.failed;
        
        document.getElementById('sent-today-count').textContent = data.stats.sent_today;
        document.getElementById('daily-limit-val').textContent = data.stats.daily_limit;
        
        // In Queue Tab as well
        const queuePending = document.getElementById('queue-pending-count');
        if (queuePending) queuePending.textContent = `${data.stats.approved} e-mails`;
        
        const queueSentToday = document.getElementById('queue-sent-today');
        if (queueSentToday) queueSentToday.textContent = `${data.stats.sent_today} / ${data.stats.daily_limit}`;
        
        renderLeadCards(allProspects);
    } catch (error) {
        showToast('Erro ao carregar leads.', 'error');
    }
}

function renderLeadCards(prospects) {
    leadsContainer.innerHTML = '';
    
    if (prospects.length === 0) {
        leadsContainer.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="8" y1="12" x2="16" y2="12"></line>
                </svg>
                <h3>Nenhum lead encontrado</h3>
                <p>Nenhuma empresa correspondente ao filtro "${currentFilter}" foi encontrada.</p>
            </div>
        `;
        return;
    }
    
    prospects.forEach(lead => {
        const card = document.createElement('div');
        card.className = 'lead-card';
        
        // Setup status badge
        let statusBadge = `<span class="badge badge-pending">Pendente</span>`;
        if (lead.status === 'approved') statusBadge = `<span class="badge badge-approved">Aprovado</span>`;
        if (lead.status === 'sent') statusBadge = `<span class="badge badge-sent">Enviado</span>`;
        if (lead.status === 'failed') statusBadge = `<span class="badge badge-failed" title="${lead.error_message || ''}">Falha</span>`;
        if (lead.status === 'rejected') statusBadge = `<span class="badge badge-rejected">Arquivado</span>`;
        
        // Setup issues HTML
        let issuesHtml = '';
        if (lead.detected_issues && lead.detected_issues.length > 0) {
            issuesHtml = `
                <div class="issues-container">
                    ${lead.detected_issues.map(issue => `<span class="issue-tag">${issue}</span>`).join('')}
                </div>
            `;
        } else {
            issuesHtml = `<div style="font-size:0.8rem; color:var(--text-muted);">Nenhuma falha estrutural detectada</div>`;
        }
        
        let waButton = '';
        if (lead.contact_whatsapp) {
            const waText = encodeURIComponent(getFormattedWhatsappDraft(lead));
            waButton = `<a href="https://wa.me/${lead.contact_whatsapp.replace(/\D/g, '')}?text=${waText}" target="_blank" class="btn btn-success btn-sm" style="background-color:#128c7e;color:white;border:none;">WhatsApp ↗</a>`;
        }

        let actionButtons = '';
        if (lead.status === 'pending') {
            actionButtons = `
                ${waButton}
                <button class="btn btn-secondary btn-sm" onclick="archiveLead(${lead.id})">Arquivar</button>
                <button class="btn btn-secondary btn-sm" onclick="openEditModal(${lead.id})">Editar E-mail</button>
                <button class="btn btn-primary btn-sm" onclick="approveLead(${lead.id})">Aprovar</button>
            `;
        } else if (lead.status === 'approved') {
            actionButtons = `
                ${waButton}
                <button class="btn btn-secondary btn-sm" onclick="pendingLead(${lead.id})">Desfazer</button>
                <button class="btn btn-secondary btn-sm" onclick="openEditModal(${lead.id})">Editar</button>
                <button class="btn btn-success btn-sm" onclick="sendEmailNow(${lead.id})">Enviar Agora</button>
            `;
        } else if (lead.status === 'rejected') {
            actionButtons = `
                <button class="btn btn-secondary btn-sm" onclick="pendingLead(${lead.id})">Recuperar Lead</button>
                <button class="btn btn-danger btn-sm" onclick="deleteLead(${lead.id})">Excluir</button>
            `;
        } else if (lead.status === 'failed') {
            actionButtons = `
                ${waButton}
                <button class="btn btn-secondary btn-sm" onclick="openEditModal(${lead.id})">Editar E-mail</button>
                <button class="btn btn-success btn-sm" onclick="sendEmailNow(${lead.id})">Reenviar</button>
            `;
        } else if (lead.status === 'sent') {
            actionButtons = `
                <span style="font-size:0.8rem; color:var(--success); font-weight:600; display:flex; align-items:center; gap:4px;">
                    ✅ Enviado com Sucesso
                </span>
                ${waButton}
                <button class="btn btn-secondary btn-sm" style="margin-left:auto;" onclick="deleteLead(${lead.id})">Excluir</button>
            `;
        }
        
        let screenshotHtml = '';
        if (lead.screenshot) {
            screenshotHtml = `<img src="/static/screenshots/${lead.screenshot}" class="lead-screenshot" alt="${lead.company_name} screenshot" onerror="this.style.display='none'">`;
        }
        
        const pilotBadge = lead.is_autopilot ? `<span class="badge" style="background-color:rgba(56,189,248,0.15); color:#38bdf8; font-size:0.7rem; padding:2px 6px; border-radius:4px; display:inline-flex; align-items:center; gap:2px; border:1px solid rgba(56,189,248,0.3); vertical-align:middle; margin-left:6px;">⚡ Autopilot</span>` : '';
        
        // Setup B2B/KipFlow data HTML
        let b2bHtml = '';
        if (lead.cnpj) {
            let partnersHtml = '';
            if (lead.socios) {
                try {
                    const partners = typeof lead.socios === 'string' ? JSON.parse(lead.socios) : lead.socios;
                    if (partners && partners.length > 0) {
                        partnersHtml = `
                            <div style="font-size:0.75rem; margin-top: 6px; color: var(--text-secondary); border-top: 1px solid rgba(255,255,255,0.05); padding-top: 4px;">
                                👥 <strong>Sócios:</strong> ${partners.map(p => `${p.nome} (${p.cargo || 'Sócio'})`).join(', ')}
                            </div>
                        `;
                    }
                } catch(e) {}
            }
            
            let socialsHtml = '';
            if (lead.redes_sociais) {
                try {
                    const socials = typeof lead.redes_sociais === 'string' ? JSON.parse(lead.redes_sociais) : lead.redes_sociais;
                    if (socials && (socials.instagram || socials.facebook || socials.linkedin)) {
                        socialsHtml = `
                            <div style="margin-top: 6px; display:flex; gap: 12px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 4px;">
                                ${socials.instagram ? `<a href="${socials.instagram}" target="_blank" style="font-size:0.75rem; text-decoration:none; color:#e1306c;" title="Instagram">📸 Instagram</a>` : ''}
                                ${socials.facebook ? `<a href="${socials.facebook}" target="_blank" style="font-size:0.75rem; text-decoration:none; color:#1877f2;" title="Facebook">📘 Facebook</a>` : ''}
                                ${socials.linkedin ? `<a href="${socials.linkedin}" target="_blank" style="font-size:0.75rem; text-decoration:none; color:#0a66c2;" title="LinkedIn">💼 LinkedIn</a>` : ''}
                            </div>
                        `;
                    }
                } catch(e) {}
            }
            
            b2bHtml = `
                <div style="background: rgba(15,23,42,0.4); padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); margin-top: 12px; line-height: 1.4;">
                    <div style="display:flex; justify-content:space-between; font-size: 0.75rem; margin-bottom: 4px;">
                        <span>📋 <strong>CNPJ:</strong> ${lead.cnpj}</span>
                        <span>🏢 <strong>Porte:</strong> ${lead.porte || 'N/A'}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size: 0.75rem;">
                        <span>💰 <strong>Faturamento:</strong> ${lead.faturamento || 'N/A'}</span>
                        <span>👥 <strong>Funcionários:</strong> ${lead.funcionarios || 'N/A'}</span>
                    </div>
                    ${partnersHtml}
                    ${socialsHtml}
                </div>
            `;
        } else {
            b2bHtml = `
                <div style="margin-top: 12px;">
                    <button type="button" class="btn btn-secondary btn-block btn-sm" style="width:100%; text-align:center; display:block;" onclick="enrichLead(${lead.id}, this)">
                        🔍 Enriquecer com KipFlow
                    </button>
                </div>
            `;
        }

        card.innerHTML = `
            ${screenshotHtml}
            <div class="lead-header">
                <div>
                    <div class="lead-company">${lead.company_name}${pilotBadge}</div>
                    <a href="${lead.website}" target="_blank" class="lead-website">
                        ${lead.website}
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                    </a>
                    <div style="font-size:0.72rem; color:var(--text-muted); margin-top:4px;">
                        📅 Captado em: <strong>${formatDateTime(lead.created_at)}</strong>
                    </div>
                </div>
                ${statusBadge}
            </div>
            <div class="lead-body">
                ${issuesHtml}
                
                <div class="lead-meta-row">
                    <span>📧 <strong>E-mail:</strong> ${lead.contact_email || '<span style="color:var(--danger)">Não encontrado</span>'}</span>
                </div>
                
                <div class="lead-meta-row">
                    <span>💬 <strong>WhatsApp:</strong> 
                        ${lead.contact_whatsapp ? 
                            `<a href="https://wa.me/${lead.contact_whatsapp.replace(/\D/g, '')}?text=${encodeURIComponent(getFormattedWhatsappDraft(lead))}" target="_blank" style="color:var(--success);text-decoration:none;">${lead.contact_whatsapp} ↗</a>` : 
                            `<span style="color:var(--text-muted)">Não encontrado</span>`
                        }
                    </span>
                </div>
                
                ${lead.notes ? `<div class="lead-notes">${lead.notes}</div>` : ''}
                ${b2bHtml}
                
                ${lead.error_message ? `
                    <div style="font-size:0.8rem; color:var(--danger); background-color:rgba(244,63,94,0.05); padding:8px; border-radius:6px; border-left:2px solid var(--danger); margin-top:8px;">
                        <strong>Erro de Envio:</strong> ${lead.error_message}
                    </div>
                ` : ''}
            </div>
            <div class="lead-actions">
                ${actionButtons}
            </div>
        `;
        
        leadsContainer.appendChild(card);
    });
}

// Action Functions
async function approveLead(id) {
    await updateLeadStatus(id, 'approved');
}

async function archiveLead(id) {
    await updateLeadStatus(id, 'rejected');
}

async function pendingLead(id) {
    await updateLeadStatus(id, 'pending');
}

async function updateLeadStatus(id, status) {
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        if (response.ok) {
            showToast(`Lead atualizado para: ${status}!`);
            loadLeads();
            if (typeof loadSurgicalLeads === 'function') {
                loadSurgicalLeads();
            }
        }
    } catch (e) {
        showToast('Erro ao atualizar lead.', 'error');
    }
}

async function deleteLead(id) {
    if (!confirm('Deseja realmente excluir este lead permanentemente?')) return;
    
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            showToast('Lead deletado com sucesso!');
            loadLeads();
            if (typeof loadSurgicalLeads === 'function') {
                loadSurgicalLeads();
            }
        }
    } catch (e) {
        showToast('Erro ao deletar lead.', 'error');
    }
}

async function enrichLead(id, button) {
    if (button) {
        button.disabled = true;
        button.textContent = 'Enriquecendo... ⌛';
    }
    
    try {
        const response = await fetch(`/api/prospects/${id}/enrich`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (response.ok) {
            showToast('Lead enriquecido com sucesso!', 'success');
            loadLeads();
            if (typeof loadSurgicalLeads === 'function') {
                loadSurgicalLeads();
            }
        } else {
            showToast(data.message || 'Falha ao enriquecer lead.', 'error');
            if (button) {
                button.disabled = false;
                button.textContent = '🔍 Enriquecer com KipFlow';
            }
        }
    } catch (error) {
        showToast('Erro ao conectar ao servidor para enriquecer.', 'error');
        if (button) {
            button.disabled = false;
            button.textContent = '🔍 Enriquecer com KipFlow';
        }
    }
}

window.enrichLead = enrichLead;
window.approveLead = approveLead;
window.archiveLead = archiveLead;
window.pendingLead = pendingLead;
window.deleteLead = deleteLead;


async function sendEmailNow(id) {
    const btn = event.target;
    const oldText = btn.textContent;
    
    const sentToday = parseInt(document.getElementById('sent-today-count').textContent) || 0;
    const dailyLimit = parseInt(document.getElementById('daily-limit-val').textContent) || 20;
    let bypassLimit = false;
    
    if (sentToday >= dailyLimit) {
        if (!confirm('Você já atingiu o limite diário de envios de e-mail. Deseja forçar o envio deste e-mail ignorando o limite?')) {
            return;
        }
        bypassLimit = true;
    }
    
    btn.disabled = true;
    btn.textContent = 'Enviando...';
    
    try {
        const response = await fetch(`/api/prospects/${id}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bypass_limit: bypassLimit })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast('E-mail enviado com sucesso!', 'success');
        } else {
            showToast(data.message || 'Erro ao enviar e-mail.', 'error');
        }
        loadLeads();
        if (typeof loadSurgicalLeads === 'function') {
            loadSurgicalLeads();
        }
    } catch (error) {
        showToast('Erro de conexão ao enviar e-mail.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}

// ==========================================
// 4. EDIT MODAL HANDLERS
// ==========================================
const editModal = document.getElementById('edit-lead-modal');
const editForm = document.getElementById('edit-lead-form');
const closeModalBtn = document.getElementById('close-modal-btn');
const cancelEditBtn = document.getElementById('cancel-edit-btn');
const saveLeadBtn = document.getElementById('save-lead-btn');

function openEditModal(id) {
    const lead = allProspects.find(l => l.id === id) || (typeof surgicalProspects !== 'undefined' ? surgicalProspects.find(l => l.id === id) : null);
    if (!lead) return;
    
    document.getElementById('edit-lead-id').value = lead.id;
    document.getElementById('modal-company-title').textContent = `Editar Lead: ${lead.company_name}`;
    document.getElementById('edit-company-name').value = lead.company_name;
    document.getElementById('edit-website').value = lead.website;
    document.getElementById('edit-email').value = lead.contact_email;
    document.getElementById('edit-whatsapp').value = lead.contact_whatsapp;
    document.getElementById('edit-phone').value = lead.contact_phone;
    document.getElementById('edit-subject').value = lead.email_subject || '';
    document.getElementById('edit-body').value = lead.email_body || '';
    document.getElementById('edit-whatsapp-draft').value = lead.whatsapp_draft || '';
    
    editModal.classList.add('active');
}

function closeModal() {
    editModal.classList.remove('active');
}

closeModalBtn.addEventListener('click', closeModal);
cancelEditBtn.addEventListener('click', closeModal);

saveLeadBtn.addEventListener('click', async () => {
    const id = document.getElementById('edit-lead-id').value;
    const update = {
        company_name: document.getElementById('edit-company-name').value,
        website: document.getElementById('edit-website').value,
        contact_email: document.getElementById('edit-email').value,
        contact_whatsapp: document.getElementById('edit-whatsapp').value,
        contact_phone: document.getElementById('edit-phone').value,
        email_subject: document.getElementById('edit-subject').value,
        email_body: document.getElementById('edit-body').value,
        whatsapp_draft: document.getElementById('edit-whatsapp-draft').value
    };
    
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(update)
        });
        if (response.ok) {
            showToast('Alterações salvas com sucesso!');
            closeModal();
            loadLeads();
            if (typeof loadSurgicalLeads === 'function') {
                loadSurgicalLeads();
            }
        }
    } catch (e) {
        showToast('Erro ao salvar edições.', 'error');
    }
});

// ==========================================
// 5. BATCH QUEUE TAB
// ==========================================
const startQueueBtn = document.getElementById('start-queue-btn');
const queueProgressBar = document.getElementById('queue-progress-bar');
const queueProgressLabel = document.getElementById('queue-progress-label');
const queueLogs = document.getElementById('queue-logs');
const queueStatusDot = document.getElementById('queue-status-dot');

startQueueBtn.addEventListener('click', async () => {
    const bypassLimit = document.getElementById('queue-bypass-limit').checked;
    
    startQueueBtn.disabled = true;
    startQueueBtn.textContent = 'Enviando Lote...';
    queueStatusDot.classList.add('active');
    
    try {
        const response = await fetch('/api/queue/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bypass_limit: bypassLimit })
        });
        const data = await response.json();
        
        if (response.ok) {
            showToast(data.message, 'success');
            startPollingQueue();
        } else {
            showToast(data.error || 'Erro ao iniciar envio de fila.', 'error');
            startQueueBtn.disabled = false;
            startQueueBtn.textContent = 'Iniciar Envio do Lote';
            queueStatusDot.classList.remove('active');
        }
    } catch (error) {
        showToast('Erro de rede ao iniciar fila.', 'error');
        startQueueBtn.disabled = false;
        startQueueBtn.textContent = 'Iniciar Envio do Lote';
        queueStatusDot.classList.remove('active');
    }
});

async function loadQueueStatus() {
    try {
        const response = await fetch('/api/queue/status');
        const data = await response.json();
        
        renderQueueUI(data.status, data.is_sending_queue);
    } catch (e) {
        console.error('Erro ao ler fila:', e);
    }
}

function renderQueueUI(status, isSending) {
    // Render progress
    if (status.total > 0) {
        const pct = Math.round((status.current / status.total) * 100);
        queueProgressBar.style.width = `${pct}%`;
        queueProgressLabel.textContent = `${pct}% concluído (${status.current}/${status.total})`;
    } else {
        queueProgressBar.style.width = `0%`;
        queueProgressLabel.textContent = `0% concluído`;
    }
    
    // Render logs
    queueLogs.innerHTML = '';
    status.logs.forEach(log => {
        const item = document.createElement('div');
        item.className = 'log-item';
        item.innerHTML = `<span class="log-msg">${log}</span>`;
        queueLogs.appendChild(item);
    });
    queueLogs.scrollTop = queueLogs.scrollHeight;
    
    if (isSending) {
        startQueueBtn.disabled = true;
        startQueueBtn.textContent = 'Enviando Lote...';
        queueStatusDot.classList.add('active');
    } else {
        startQueueBtn.disabled = false;
        startQueueBtn.textContent = 'Iniciar Envio do Lote';
        queueStatusDot.classList.remove('active');
    }
}

function startPollingQueue() {
    if (queueInterval) clearInterval(queueInterval);
    
    queueInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/queue/status');
            const data = await response.json();
            
            renderQueueUI(data.status, data.is_sending_queue);
            
            if (!data.is_sending_queue) {
                clearInterval(queueInterval);
                queueInterval = null;
                showToast('Envio de fila finalizado!');
                loadLeads(); // Reload counters
                loadSentHistory(); // Reload sent history table
            }
        } catch (error) {
            console.error(error);
        }
    }, 2000);
}

// Check on load if queue is already running
async function checkActiveQueue() {
    try {
        const response = await fetch('/api/queue/status');
        const data = await response.json();
        if (data.is_sending_queue) {
            startPollingQueue();
        }
    } catch (e) {
        console.error(e);
    }
}
checkActiveQueue();

// Load initial counts for dashboard
loadLeads();
loadSettings();
loadSentHistory(); // Load initial sent history

// ==========================================
// 6. SENT HISTORY TAB & TABLE HANDLERS
// ==========================================
async function loadSentHistory() {
    try {
        const response = await fetch('/api/prospects?status=sent');
        const data = await response.json();
        
        const tbody = document.getElementById('queue-sent-table-body');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (data.prospects.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="padding: 24px; text-align: center; color: var(--text-muted);">
                        Nenhum e-mail enviado ainda.
                    </td>
                </tr>
            `;
            return;
        }
        
        data.prospects.forEach(lead => {
            const tr = document.createElement('tr');
            
            // Format sent date
            let sentDateStr = 'Sem data';
            if (lead.sent_at) {
                try {
                    const parts = lead.sent_at.split(' ');
                    const dateParts = parts[0].split('-');
                    sentDateStr = `${dateParts[2]}/${dateParts[1]}/${dateParts[0]} ${parts[1]}`;
                } catch (e) {
                    sentDateStr = lead.sent_at;
                }
            }
            
            let waButton = '';
            if (lead.contact_whatsapp) {
                const waText = encodeURIComponent(getFormattedWhatsappDraft(lead));
                waButton = `<a href="https://wa.me/${lead.contact_whatsapp.replace(/\D/g, '')}?text=${waText}" target="_blank" class="btn btn-success btn-sm" style="background-color:#128c7e;color:white;border:none;padding: 4px 8px; font-size:0.75rem;">WhatsApp ↗</a>`;
            }
            
            tr.innerHTML = `
                <td style="padding: 12px; font-weight: 600;">${lead.company_name}</td>
                <td style="padding: 12px;"><a href="${lead.website}" target="_blank" style="color:var(--secondary); text-decoration:none;">${lead.website}</a></td>
                <td style="padding: 12px; color:var(--text-secondary);">${lead.contact_email}</td>
                <td style="padding: 12px; color:var(--text-muted);">${sentDateStr}</td>
                <td style="padding: 12px; text-align: right;">
                    <div style="display:flex; gap:6px; justify-content:flex-end;">
                        ${waButton}
                        <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size:0.75rem;" onclick="openEditModal(${lead.id})">Ver E-mail</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error('Erro ao carregar histórico de envios:', error);
    }
}

// ==========================================
// 7. FOLLOW-UP (ACOMPANHAMENTO) TAB HANDLERS
// ==========================================

function getDaysElapsed(sentAtStr) {
    if (!sentAtStr) return "Desconhecido";
    
    const cleanStr = sentAtStr.replace(' ', 'T');
    const sentDate = new Date(cleanStr);
    if (isNaN(sentDate.getTime())) {
        return sentAtStr;
    }
    
    const now = new Date();
    const diffTime = now - sentDate;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays <= 0) {
        return "Enviado hoje";
    } else if (diffDays === 1) {
        return "Enviado ontem";
    } else {
        return `Enviado há ${diffDays} dias`;
    }
}

async function loadFollowupList() {
    try {
        const response = await fetch('/api/prospects?status=sent');
        const data = await response.json();
        
        const tbody = document.getElementById('followup-table-body');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (data.prospects.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="padding: 24px; text-align: center; color: var(--text-muted);">
                        Nenhum lead com e-mail enviado para acompanhamento.
                    </td>
                </tr>
            `;
            return;
        }
        
        data.prospects.forEach(lead => {
            const tr = document.createElement('tr');
            
            // Calculate elapsed days
            const daysElapsedText = getDaysElapsed(lead.sent_at);
            
            // Format status badge
            let statusBadge = '';
            if (lead.followup_status === 'done') {
                statusBadge = '<span class="badge badge-sent" style="background-color: var(--success); color: white;">Contatado</span>';
            } else {
                statusBadge = '<span class="badge badge-pending" style="background-color: var(--warning); color: #000; font-weight: 600;">Aguardando Retorno</span>';
            }
            
            // WhatsApp button HTML
            let waButton = '';
            if (lead.contact_whatsapp) {
                const senderName = systemSettings.sender_name || 'Matheus Paviani';
                
                // Varied templates to avoid WhatsApp spam detection
                const templates = [
                    `Olá! Sou o ${senderName}. Enviei um e-mail para vocês recentemente apresentando uma proposta de modernização para o site da ${lead.company_name}. Gostaria de confirmar se receberam e se teriam 5 minutos para conversarmos sobre essa oportunidade? Abraço!`,
                    `Olá! Tudo bem? Meu nome é ${senderName}. Recentemente enviei um e-mail para a equipe da ${lead.company_name} com algumas sugestões e ideias de design para o site de vocês. Você saberia me dizer se conseguiram dar uma olhada, ou com quem eu poderia falar sobre isso? Obrigado!`,
                    `Oi, tudo bem? Aqui é o ${senderName}. Dei uma olhada no site da ${lead.company_name} esses dias e mandei um e-mail com um estudo visual mostrando como ele poderia ficar mais moderno e adaptado para celular. Queria ver se vocês receberam e se teriam uns minutinhos para conversarmos. Abraço!`,
                    `Olá! Me chamo ${senderName} e escrevo para confirmar o recebimento de um e-mail que enviei para a ${lead.company_name} há pouco tempo sobre a modernização e otimização do site de vocês. Caso tenha interesse em ver o design conceitual que criei, estou à disposição para bater um papo rápido!`
                ];
                
                // Select template consistently based on lead ID
                const templateIndex = lead.id % templates.length;
                const messageText = templates[templateIndex];
                const waUrl = `https://wa.me/${lead.contact_whatsapp.replace(/\D/g, '')}?text=${encodeURIComponent(messageText)}`;
                waButton = `
                    <a href="${waUrl}" target="_blank" class="btn btn-success btn-sm" style="background-color:#128c7e; color:white; border:none; padding: 6px 12px; font-size:0.8rem; text-decoration:none; display:inline-flex; align-items:center; gap:4px;" onclick="handleWaFollowupClick(${lead.id})">
                        WhatsApp ↗
                    </a>
                `;
            } else {
                waButton = `
                    <button class="btn btn-secondary btn-sm" disabled style="padding: 6px 12px; font-size:0.8rem; opacity:0.5; cursor:not-allowed;">
                        Sem WhatsApp
                    </button>
                `;
            }
            
            // Toggle action button HTML
            let toggleButton = '';
            if (lead.followup_status === 'done') {
                toggleButton = `
                    <button class="btn btn-secondary btn-sm" style="padding: 6px 12px; font-size:0.8rem;" onclick="resetFollowupStatus(${lead.id})">
                        Reverter para Pendente
                    </button>
                `;
            } else {
                toggleButton = `
                    <button class="btn btn-primary btn-sm" style="padding: 6px 12px; font-size:0.8rem;" onclick="markFollowupContacted(${lead.id})">
                        Marcar como Contatado
                    </button>
                `;
            }
            
            tr.innerHTML = `
                <td style="padding: 16px 12px; font-weight: 600; vertical-align: middle;">
                    <div>${lead.company_name}</div>
                    <div style="font-size:0.72rem; color:var(--text-muted); font-weight:400; margin-top:2px;">📅 Captado em: <strong>${formatDateTime(lead.created_at)}</strong></div>
                </td>
                <td style="padding: 16px 12px; color:var(--text-secondary); vertical-align: middle;">${lead.contact_email || '<span style="color:var(--text-muted)">Sem e-mail</span>'}</td>
                <td style="padding: 16px 12px; color:var(--text-secondary); vertical-align: middle;">${daysElapsedText}</td>
                <td style="padding: 16px 12px; vertical-align: middle;">${statusBadge}</td>
                <td style="padding: 16px 12px; text-align: right; vertical-align: middle;">
                    <div style="display:flex; gap:8px; justify-content:flex-end; align-items:center;">
                        ${waButton}
                        ${toggleButton}
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        console.error('Erro ao carregar lista de acompanhamento:', error);
        showToast('Erro ao carregar lista de acompanhamento.', 'error');
    }
}

async function markFollowupContacted(id) {
    const nowStr = new Date().toISOString().slice(0, 19).replace('T', ' ');
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                followup_status: 'done',
                followup_sent_at: nowStr
            })
        });
        if (response.ok) {
            showToast('Lead marcado como contatado!');
            loadFollowupList();
        } else {
            showToast('Erro ao atualizar status do acompanhamento.', 'error');
        }
    } catch (e) {
        showToast('Erro de rede ao atualizar status.', 'error');
    }
}

async function resetFollowupStatus(id) {
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                followup_status: 'pending',
                followup_sent_at: null
            })
        });
        if (response.ok) {
            showToast('Acompanhamento revertido para pendente.');
            loadFollowupList();
        } else {
            showToast('Erro ao reverter status do acompanhamento.', 'error');
        }
    } catch (e) {
        showToast('Erro de rede ao atualizar status.', 'error');
    }
}

function handleWaFollowupClick(id) {
    // Automatically mark contacted after clicking WhatsApp link
    setTimeout(() => {
        markFollowupContacted(id);
    }, 1000);
}

// ==========================================
// 7. SURGICAL PROSPECTING TAB
// ==========================================
let surgicalProspects = [];
let surgicalSearchInterval = null;
let surgicalFilter = 'all';

// Load Surgical tab details
async function loadSurgicalTab() {
    loadSurgicalLeads();
    checkActiveSurgicalSearch();
}

// Check if search is running on load
async function checkActiveSurgicalSearch() {
    try {
        const response = await fetch('/api/surgical/status');
        const data = await response.json();
        const runBtn = document.getElementById('btn-run-surgical');
        const statusDot = document.getElementById('surgical-console-status-dot');
        if (data.is_searching) {
            runBtn.disabled = true;
            runBtn.innerHTML = `
                <span class="console-dot active" style="display:inline-block; margin-right:8px; width:10px; height:10px; background-color:#10b981; border-radius:50%; animation: pulse 1.5s infinite;"></span>
                Escaneando Cirurgicamente...
            `;
            if (statusDot) statusDot.classList.add('active');
            startPollingSurgicalLogs();
        } else {
            runBtn.disabled = false;
            runBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Iniciar Varredura Cirúrgica
            `;
            if (statusDot) statusDot.classList.remove('active');
        }
    } catch (e) {
        console.error("Erro ao verificar busca cirúrgica ativa:", e);
    }
}

// Poll logs
function startPollingSurgicalLogs() {
    if (surgicalSearchInterval) clearInterval(surgicalSearchInterval);
    
    const consoleLogs = document.getElementById('surgical-console-logs');
    const runBtn = document.getElementById('btn-run-surgical');
    const statusDot = document.getElementById('surgical-console-status-dot');
    if (statusDot) statusDot.classList.add('active');
    
    surgicalSearchInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/surgical/status');
            const data = await response.json();
            
            consoleLogs.innerHTML = '';
            if (data.logs.length === 0) {
                consoleLogs.innerHTML = `
                    <div class="log-item">
                        <span class="log-time">[Processo]</span>
                        <span class="log-msg">Pesquisando e analisando alvos cirúrgicos...</span>
                    </div>
                `;
            } else {
                data.logs.forEach(log => {
                    const item = document.createElement('div');
                    item.className = 'log-item';
                    item.innerHTML = `
                        <span class="log-time">[${log.time}]</span>
                        <span class="log-msg">${log.message}</span>
                    `;
                    consoleLogs.appendChild(item);
                });
            }
            
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
            
            if (!data.is_searching) {
                clearInterval(surgicalSearchInterval);
                surgicalSearchInterval = null;
                
                runBtn.disabled = false;
                runBtn.innerHTML = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                    Iniciar Varredura Cirúrgica
                `;
                if (statusDot) statusDot.classList.remove('active');
                
                showToast('Busca cirúrgica concluída com sucesso!', 'success');
                
                const item = document.createElement('div');
                item.className = 'log-item';
                item.innerHTML = `
                    <span class="log-time">[Fim]</span>
                    <span class="log-msg" style="color:var(--success);">Varredura terminada. Resultados atualizados na tabela abaixo!</span>
                `;
                consoleLogs.appendChild(item);
                consoleLogs.scrollTop = consoleLogs.scrollHeight;
                
                loadSurgicalLeads();
            }
        } catch (error) {
            console.error('Erro ao buscar logs cirúrgicos:', error);
        }
    }, 1500);
}

// Submit search form
const surgicalSearchForm = document.getElementById('surgical-search-form');
if (surgicalSearchForm) {
    // Show/hide custom options
    document.getElementById('surgical-segment-select').addEventListener('change', (e) => {
        document.getElementById('surgical-segment-custom-group').style.display = e.target.value === 'custom' ? 'block' : 'none';
    });
    
    document.getElementById('surgical-city-select').addEventListener('change', (e) => {
        document.getElementById('surgical-city-custom-group').style.display = e.target.value === 'custom' ? 'block' : 'none';
    });
    
    surgicalSearchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const segmentSelect = document.getElementById('surgical-segment-select').value;
        const segment = segmentSelect === 'custom' ? document.getElementById('surgical-segment-custom').value : segmentSelect;
        
        const state_uf = document.getElementById('surgical-state-select').value;
        const citySelect = document.getElementById('surgical-city-select').value;
        const city_name = citySelect === 'custom' ? document.getElementById('surgical-city-custom').value : citySelect;
        
        const radius_km = document.getElementById('surgical-radius-select').value;
        const max_results = document.getElementById('surgical-limit').value;
        const surgical_type = document.getElementById('surgical-target-type').value;
        
        if (!segment) {
            showToast('Por favor, informe o segmento.', 'warning');
            return;
        }
        
        const runBtn = document.getElementById('btn-run-surgical');
        runBtn.disabled = true;
        runBtn.innerHTML = `
            <span class="console-dot active" style="display:inline-block; margin-right:8px; width:10px; height:10px; background-color:#10b981; border-radius:50%; animation: pulse 1.5s infinite;"></span>
            Escaneando...
        `;
        
        try {
            let region = 'Brasil';
            if (state_uf) {
                region = city_name && city_name !== 'Estado Inteiro' ? `${city_name} - ${state_uf}` : state_uf;
            }
            
            const response = await fetch('/api/surgical/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    segment, region, state_uf, city_name, radius_km, max_results, surgical_type
                })
            });
            const data = await response.json();
            
            if (response.ok) {
                showToast('Busca cirúrgica iniciada no servidor!');
                startPollingSurgicalLogs();
            } else {
                showToast(data.error || 'Erro ao iniciar busca cirúrgica.', 'error');
                runBtn.disabled = false;
                runBtn.innerHTML = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                    Iniciar Varredura Cirúrgica
                `;
            }
        } catch (error) {
            showToast('Erro de rede ao disparar buscador cirúrgico.', 'error');
            runBtn.disabled = false;
            runBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Iniciar Varredura Cirúrgica
            `;
        }
    });
}

// Load Surgical Leads list
async function loadSurgicalLeads() {
    try {
        const statusParam = surgicalFilter === 'all' ? '' : `&status=${surgicalFilter}`;
        const response = await fetch(`/api/prospects?is_surgical=1${statusParam}`);
        const data = await response.json();
        
        surgicalProspects = data.prospects;
        
        // Update surgical stats
        document.getElementById('sstats-total').textContent = data.stats.total;
        document.getElementById('sstats-pending').textContent = data.stats.pending;
        document.getElementById('sstats-approved').textContent = data.stats.approved;
        document.getElementById('sstats-sent').textContent = data.stats.sent;
        document.getElementById('sstats-failed').textContent = data.stats.failed;
        
        renderSurgicalTable(surgicalProspects);
    } catch (e) {
        showToast('Erro ao carregar leads cirúrgicos.', 'error');
    }
}

// Render Table Rows
function renderSurgicalTable(leads) {
    const tbody = document.getElementById('surgical-leads-tbody');
    tbody.innerHTML = '';
    
    if (leads.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">
                    Nenhum lead cirúrgico encontrado para o filtro "${surgicalFilter}".
                </td>
            </tr>
        `;
        return;
    }
    
    leads.forEach(lead => {
        const tr = document.createElement('tr');
        
        const pilotBadge = lead.is_autopilot ? `<span class="badge" style="background-color:rgba(56,189,248,0.15); color:#38bdf8; font-size:0.7rem; padding:2px 6px; border-radius:4px; display:inline-flex; align-items:center; gap:2px; border:1px solid rgba(56,189,248,0.3); vertical-align:middle; margin-left:6px;">⚡ Autopilot</span>` : '';
        
        // Website link formatting
        const websiteLink = lead.website ? `<a href="${lead.website}" target="_blank" class="lead-link">${lead.website.replace('https://', '').replace('http://', '').split('/')[0]}</a>` : 'Não possui';
        
        // Badges
        let statusBadge = `<span class="badge badge-pending">Pendente</span>`;
        if (lead.status === 'approved') statusBadge = `<span class="badge badge-approved">Aprovado</span>`;
        if (lead.status === 'sent') statusBadge = `<span class="badge badge-sent">Enviado</span>`;
        if (lead.status === 'failed') statusBadge = `<span class="badge badge-failed" title="${lead.error_message || ''}">Falha</span>`;
        if (lead.status === 'rejected') statusBadge = `<span class="badge badge-rejected">Arquivado</span>`;
        
        let typeBadge = `<span class="badge" style="background-color: #ef4444; color: white;">Site Crítico</span>`;
        if (lead.surgical_type === 'no_site') {
            typeBadge = `<span class="badge" style="background-color: #f59e0b; color: white;">Sem Site</span>`;
        } else if (lead.surgical_type === 'maps_only') {
            typeBadge = `<span class="badge" style="background-color: #3b82f6; color: white;">Google Maps</span>`;
        }
            
        // Issues list
        let issuesHtml = '';
        if (lead.detected_issues && lead.detected_issues.length > 0) {
            issuesHtml = lead.detected_issues.map(iss => `<span class="issue-tag" style="display:inline-block; font-size:0.7rem; padding: 2px 6px; background-color:rgba(239, 68, 68, 0.1); color:#ef4444; border-radius:4px; margin: 2px;">${iss}</span>`).join('');
        }
        
        // Contact email, phone, actions
        let actionButtons = '';
        if (lead.status === 'pending') {
            actionButtons = `
                <button class="btn btn-primary btn-sm" onclick="approveLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem; margin-right:4px;">Aprovar</button>
                <button class="btn btn-danger btn-sm" onclick="archiveLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem;">Arquivar</button>
            `;
        } else if (lead.status === 'approved') {
            actionButtons = `
                <button class="btn btn-success btn-sm" onclick="sendEmailNow(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem; margin-right:4px;">Enviar E-mail</button>
                <button class="btn btn-secondary btn-sm" onclick="pendingLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem;">Reverter</button>
            `;
        } else if (lead.status === 'rejected') {
            actionButtons = `
                <button class="btn btn-secondary btn-sm" onclick="pendingLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem; margin-right:4px;">Recuperar</button>
                <button class="btn btn-danger btn-sm" onclick="deleteLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem;">Excluir</button>
            `;
        } else {
            actionButtons = `
                <button class="btn btn-secondary btn-sm" onclick="pendingLead(${lead.id})" style="padding: 4px 8px; font-size: 0.75rem;">Reverter</button>
            `;
        }
        
        actionButtons += `
            <div style="margin-top: 6px;">
                <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size:0.75rem; width:100%;" onclick="openEditModal(${lead.id})">Ver / Editar E-mail</button>
            </div>
        `;
        
        let waButton = '';
        if (lead.contact_whatsapp) {
            const waMsg = encodeURIComponent(getFormattedWhatsappDraft(lead));
            const waLink = `https://wa.me/${lead.contact_whatsapp.replace(/\D/g, '')}?text=${waMsg}`;
            waButton = `
                <div style="margin-top: 6px;">
                    <a href="${waLink}" target="_blank" class="btn btn-success btn-sm" style="display:inline-block; text-align:center; padding: 4px 8px; font-size:0.75rem; width:100%; text-decoration:none; background-color:#10b981;" onclick="handleWaFollowupClick(${lead.id})">WhatsApp</a>
                </div>
            `;
        }
        
        tr.innerHTML = `
            <td>
                <div style="font-weight: 600; color: var(--text-primary);">${lead.company_name}${pilotBadge}</div>
                <div style="margin-top: 4px;">${websiteLink}</div>
                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 4px;">📅 Captado em: <strong>${formatDateTime(lead.created_at)}</strong></div>
            </td>
            <td>
                <div>${lead.segment}</div>
                <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px;">${lead.region}</div>
            </td>
            <td>
                ${typeBadge}
                <div style="margin-top: 6px;">${statusBadge}</div>
            </td>
            <td>
                <div style="max-height: 100px; overflow-y: auto; font-size: 0.8rem;">
                    <div style="font-weight: 600; margin-bottom:4px;">Falhas:</div>
                    ${issuesHtml || '<span style="color:var(--text-muted);">Nenhuma</span>'}
                    <div style="font-weight: 600; margin-top:6px; margin-bottom:2px;">Notas:</div>
                    <span style="color:var(--text-secondary); font-style:italic;">${lead.notes || 'Sem observações.'}</span>
                </div>
            </td>
            <td>
                <div style="font-size: 0.8rem; margin-bottom: 8px;">
                    <div>📧: ${lead.contact_email || '<span style="color:var(--text-muted);">Não possui</span>'}</div>
                    <div style="margin-top: 2px;">📱: ${lead.contact_whatsapp || lead.contact_phone || '<span style="color:var(--text-muted);">Não possui</span>'}</div>
                </div>
                <div>
                    ${actionButtons}
                    ${waButton}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Bind Filter tags click
const sfilterTags = document.querySelectorAll('#surgical-filter-tags .filter-tag');
sfilterTags.forEach(tag => {
    tag.addEventListener('click', () => {
        sfilterTags.forEach(t => t.classList.remove('active'));
        tag.classList.add('active');
        surgicalFilter = tag.getAttribute('data-sfilter');
        loadSurgicalLeads();
    });
});

// ==========================================
// 6. PILOTO AUTOMÁTICO & IMPORTADOR
// ==========================================
let automationInterval = null;
let importerInterval = null;

async function loadAutomationTab() {
    loadAutomationSettings();
    checkActiveImporter();
    startPollingAutomation();
}

function updateMasterAutopilotStatusUI(senderEnabled, searchEnabled) {
    const dot = document.getElementById('autopilot-status-dot');
    const title = document.getElementById('autopilot-status-title');
    const startBtn = document.getElementById('start-autopilot-master-btn');
    const stopBtn = document.getElementById('stop-autopilot-master-btn');
    
    if (!dot || !title || !startBtn || !stopBtn) return;
    
    if (senderEnabled === '1' || searchEnabled === '1') {
        dot.className = 'status-dot-active';
        title.innerText = 'Ativo (Em Execução)';
        title.style.color = 'var(--success)';
        startBtn.style.display = 'none';
        stopBtn.style.display = 'flex';
    } else {
        dot.className = 'status-dot-inactive';
        title.innerText = 'Desativado';
        title.style.color = 'var(--text-primary)';
        startBtn.style.display = 'flex';
        stopBtn.style.display = 'none';
    }
}

async function loadAutomationSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        
        document.getElementById('autopilot_sender_enabled').checked = settings.autopilot_sender_enabled === '1';
        document.getElementById('autopilot_search_enabled').checked = settings.autopilot_search_enabled === '1';
        document.getElementById('autopilot_auto_approve').checked = settings.autopilot_auto_approve === '1';
        
        const hoursEnabled = settings.autopilot_sender_hours_enabled !== '0';
        document.getElementById('autopilot_sender_hours_enabled').checked = hoursEnabled;
        
        const hoursRow = document.getElementById('autopilot-hours-inputs-row');
        if (hoursRow) {
            if (hoursEnabled) {
                hoursRow.style.opacity = '1';
                hoursRow.style.pointerEvents = 'auto';
            } else {
                hoursRow.style.opacity = '0.4';
                hoursRow.style.pointerEvents = 'none';
            }
        }
        
        document.getElementById('autopilot_sender_interval_min').value = settings.autopilot_sender_interval_min || '20';
        document.getElementById('autopilot_search_interval_hours').value = settings.autopilot_search_interval_hours || '12';
        
        document.getElementById('autopilot_sender_start_hour').value = settings.autopilot_sender_start_hour || '8';
        document.getElementById('autopilot_sender_end_hour').value = settings.autopilot_sender_end_hour || '18';
        
        const days = (settings.autopilot_sender_days || '1,2,3,4,5').split(',');
        document.querySelectorAll('.autopilot-day').forEach(cb => {
            cb.checked = days.includes(cb.value);
        });
        
        updateMasterAutopilotStatusUI(settings.autopilot_sender_enabled, settings.autopilot_search_enabled);
        
        try {
            const targets = JSON.parse(settings.autopilot_search_targets || '[]');
            autopilotTargets = Array.isArray(targets) ? targets : [];
            if (autopilotTargets.length === 0) {
                // Default target if empty
                autopilotTargets = [
                    { segment: "Advogado", region: "Porto Alegre - RS", type: "maps_only", limit: 10, radius_km: 0 }
                ];
            }
            renderAutopilotTargets();
        } catch (e) {
            autopilotTargets = [];
            renderAutopilotTargets();
        }
    } catch (error) {
        showToast('Erro ao carregar configurações do Autopilot.', 'error');
    }
}

function renderAutopilotTargets() {
    const container = document.getElementById('autopilot-targets-container');
    if (!container) return;
    container.innerHTML = '';
    
    if (autopilotTargets.length === 0) {
        container.innerHTML = `
            <div id="no-targets-msg" style="font-size: 0.8rem; color: var(--text-muted); text-align: center; padding: 12px;">
                Nenhum alvo de busca cadastrado. Adicione um alvo acima.
            </div>
        `;
        document.getElementById('autopilot_search_targets_area').value = '[]';
        return;
    }
    
    autopilotTargets.forEach((target, index) => {
        const item = document.createElement('div');
        item.style = "display: flex; justify-content: space-between; align-items: center; background: rgba(30,41,59,0.7); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); font-size: 0.8rem; margin-bottom: 2px;";
        
        let typeLabel = '🔍 Orgânica (Sites)';
        if (target.type === 'maps_only') {
            typeLabel = '🗺️ Google Maps (Cirúrgica)';
        } else if (target.type === 'kipflow') {
            typeLabel = '📋 KipFlow (Base CNPJ)';
        }
        const radiusLabel = target.radius_km > 0 ? ` (+${target.radius_km}km)` : '';
        
        item.innerHTML = `
            <div>
                <strong style="color: var(--secondary);">${target.segment}</strong> em <em>${target.region}${radiusLabel}</em>
                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">
                    Busca: ${typeLabel} | Limite: ${target.limit} leads
                </div>
            </div>
            <button type="button" class="btn btn-danger btn-sm" style="padding: 4px 8px; font-size: 0.7rem; background: #ef4444; border: none; border-radius: 4px; color: white; cursor: pointer;" onclick="removeAutopilotTarget(${index})">
                🗑️ Excluir
            </button>
        `;
        container.appendChild(item);
    });
    
    document.getElementById('autopilot_search_targets_area').value = JSON.stringify(autopilotTargets);
}

window.removeAutopilotTarget = function(index) {
    autopilotTargets.splice(index, 1);
    renderAutopilotTargets();
};

const addTargetBtn = document.getElementById('add-target-btn');
if (addTargetBtn) {
    addTargetBtn.addEventListener('click', () => {
        const segment = document.getElementById('target_segment').value.trim();
        const region = document.getElementById('target_region').value.trim();
        const type = document.getElementById('target_type').value;
        const limit = parseInt(document.getElementById('target_limit').value) || 10;
        const radius = parseInt(document.getElementById('target_radius').value) || 0;
        
        if (!segment || !region) {
            showToast('Por favor, preencha Segmento e Região!', 'error');
            return;
        }
        
        autopilotTargets.push({
            segment: segment,
            region: region,
            type: type,
            limit: limit,
            radius_km: radius
        });
        
        renderAutopilotTargets();
        
        // Clear inputs
        document.getElementById('target_segment').value = '';
        document.getElementById('target_region').value = '';
        document.getElementById('target_limit').value = '10';
        document.getElementById('target_radius').value = '0';
    });
}

document.getElementById('save-autopilot-btn').addEventListener('click', async () => {
    const enabledSender = document.getElementById('autopilot_sender_enabled').checked ? '1' : '0';
    const enabledSearch = document.getElementById('autopilot_search_enabled').checked ? '1' : '0';
    const autoApprove = document.getElementById('autopilot_auto_approve').checked ? '1' : '0';
    const enabledHours = document.getElementById('autopilot_sender_hours_enabled').checked ? '1' : '0';
    
    const intervalMin = document.getElementById('autopilot_sender_interval_min').value;
    const intervalHours = document.getElementById('autopilot_search_interval_hours').value;
    
    const startHour = document.getElementById('autopilot_sender_start_hour').value;
    const endHour = document.getElementById('autopilot_sender_end_hour').value;
    
    const selectedDays = [];
    document.querySelectorAll('.autopilot-day:checked').forEach(cb => {
        selectedDays.push(cb.value);
    });
    
    const targetsText = document.getElementById('autopilot_search_targets_area').value;
    
    const payload = {
        autopilot_sender_enabled: enabledSender,
        autopilot_search_enabled: enabledSearch,
        autopilot_auto_approve: autoApprove,
        autopilot_sender_hours_enabled: enabledHours,
        autopilot_sender_interval_min: intervalMin,
        autopilot_search_interval_hours: intervalHours,
        autopilot_sender_start_hour: startHour,
        autopilot_sender_end_hour: endHour,
        autopilot_sender_days: selectedDays.join(','),
        autopilot_search_targets: targetsText
    };
    
    try {
        const response = await fetch('/api/autopilot/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const res = await response.json();
        if (res.success) {
            showToast('Configurações do Autopilot salvas com sucesso!');
            updateMasterAutopilotStatusUI(enabledSender, enabledSearch);
        } else {
            showToast(res.message || 'Erro ao salvar.', 'error');
        }
    } catch (error) {
        showToast('Erro de rede ao salvar configurações.', 'error');
    }
});

const hoursCheckbox = document.getElementById('autopilot_sender_hours_enabled');
if (hoursCheckbox) {
    hoursCheckbox.addEventListener('change', (e) => {
        const hoursRow = document.getElementById('autopilot-hours-inputs-row');
        if (hoursRow) {
            if (e.target.checked) {
                hoursRow.style.opacity = '1';
                hoursRow.style.pointerEvents = 'auto';
            } else {
                hoursRow.style.opacity = '0.4';
                hoursRow.style.pointerEvents = 'none';
            }
        }
    });
}

const startMasterBtn = document.getElementById('start-autopilot-master-btn');
const stopMasterBtn = document.getElementById('stop-autopilot-master-btn');

if (startMasterBtn) {
    startMasterBtn.addEventListener('click', () => {
        document.getElementById('autopilot_sender_enabled').checked = true;
        document.getElementById('autopilot_search_enabled').checked = true;
        document.getElementById('save-autopilot-btn').click();
    });
}

if (stopMasterBtn) {
    stopMasterBtn.addEventListener('click', () => {
        document.getElementById('autopilot_sender_enabled').checked = false;
        document.getElementById('autopilot_search_enabled').checked = false;
        document.getElementById('save-autopilot-btn').click();
    });
}

const forceSearchBtn = document.getElementById('force-search-btn');
const forceSendBtn = document.getElementById('force-send-btn');

if (forceSearchBtn) {
    forceSearchBtn.addEventListener('click', async () => {
        forceSearchBtn.disabled = true;
        forceSearchBtn.innerText = '⏳ Iniciando...';
        try {
            const response = await fetch('/api/autopilot/force-search', { method: 'POST' });
            const res = await response.json();
            if (res.success) {
                showToast('Busca em background iniciada com sucesso!');
                updateAutomationStatus();
            } else {
                showToast(res.message || 'Falha ao forçar busca.', 'error');
            }
        } catch (e) {
            showToast('Erro de rede ao iniciar busca.', 'error');
        } finally {
            forceSearchBtn.disabled = false;
            forceSearchBtn.innerText = '🔍 Forçar Busca Agora';
        }
    });
}

if (forceSendBtn) {
    forceSendBtn.addEventListener('click', async () => {
        forceSendBtn.disabled = true;
        forceSendBtn.innerText = '⏳ Iniciando...';
        try {
            const response = await fetch('/api/autopilot/force-send', { method: 'POST' });
            const res = await response.json();
            if (res.success) {
                showToast('Disparo automático forçado!');
                updateAutomationStatus();
            } else {
                showToast(res.message || 'Falha ao forçar disparo.', 'error');
            }
        } catch (e) {
            showToast('Erro de rede ao iniciar disparo.', 'error');
        } finally {
            forceSendBtn.disabled = false;
            forceSendBtn.innerText = '📧 Forçar Disparo Agora';
        }
    });
}

function startPollingAutomation() {
    if (automationInterval) clearInterval(automationInterval);
    
    updateAutomationStatus();
    automationInterval = setInterval(updateAutomationStatus, 5000);
}

async function updateAutomationStatus() {
    try {
        const response = await fetch('/api/autopilot/status');
        const data = await response.json();
        
        const senderBadge = document.getElementById('autopilot-sender-status-badge');
        senderBadge.className = 'badge';
        if (data.sender_status === 'sending') {
            senderBadge.classList.add('badge-success');
            senderBadge.innerText = 'Enviando...';
        } else if (data.sender_status === 'disabled') {
            senderBadge.classList.add('badge-secondary');
            senderBadge.innerText = 'Desativado';
        } else if (data.sender_status === 'outside_hours') {
            senderBadge.classList.add('badge-warning');
            senderBadge.innerText = 'Fora do Horário';
        } else if (data.sender_status === 'waiting_interval') {
            senderBadge.classList.add('badge-pending');
            senderBadge.innerText = 'Aguardando Intervalo';
        } else if (data.sender_status === 'limit_reached') {
            senderBadge.classList.add('badge-danger');
            senderBadge.innerText = 'Limite Atingido';
        } else if (data.sender_status === 'no_leads') {
            senderBadge.classList.add('badge-pending');
            senderBadge.innerText = 'Fila Vazia';
        } else {
            senderBadge.classList.add('badge-pending');
            senderBadge.innerText = 'Inativo';
        }
        
        const searchBadge = document.getElementById('autopilot-search-status-badge');
        searchBadge.className = 'badge';
        if (data.search_status === 'searching') {
            searchBadge.classList.add('badge-success');
            searchBadge.innerText = 'Buscando...';
        } else if (data.search_status === 'disabled') {
            searchBadge.classList.add('badge-secondary');
            searchBadge.innerText = 'Desativado';
        } else if (data.search_status === 'waiting_interval') {
            searchBadge.classList.add('badge-pending');
            searchBadge.innerText = 'Aguardando Intervalo';
        } else if (data.search_status === 'no_targets') {
            searchBadge.classList.add('badge-danger');
            searchBadge.innerText = 'Sem Alvos';
        } else {
            searchBadge.classList.add('badge-pending');
            searchBadge.innerText = 'Inativo';
        }
        
        document.getElementById('autopilot-next-send-time').innerText = data.next_send_time || '-';
        
        const historyContainer = document.getElementById('autopilot-history-container');
        if (historyContainer) {
            if (data.history && data.history.length > 0) {
                historyContainer.innerHTML = data.history.map(item => {
                    const badgeClass = item.status === 'success' ? 'badge-success' : 'badge-danger';
                    const icon = item.type === 'Disparo de E-mail' ? '📧' : '🔍';
                    return `
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; font-size:0.75rem; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:6px 10px; border-radius:6px; line-height:1.4;">
                            <div style="flex:1; padding-right:8px;">
                                <div style="display:flex; align-items:center; gap:6px; font-weight:600; color:#cbd5e1; margin-bottom:2px;">
                                    <span>${icon} ${item.type}</span>
                                    <span class="badge ${badgeClass}" style="font-size:0.6rem; padding:1px 4px; border-radius:3px;">
                                        ${item.status === 'success' ? 'Sucesso' : 'Falha'}
                                    </span>
                                </div>
                                <div style="color:var(--text-secondary); font-size:0.72rem;">${item.detail}</div>
                            </div>
                            <div style="color:var(--text-muted); font-size:0.7rem; white-space:nowrap; text-align:right;">
                                ${item.timestamp}
                            </div>
                        </div>
                    `;
                }).join('');
            } else {
                historyContainer.innerHTML = `
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-align: center; padding: 10px;">
                        Nenhuma atividade registrada no histórico ainda.
                    </div>
                `;
            }
        }
        
        const logsDiv = document.getElementById('autopilot-logs');
        if (data.logs && data.logs.length > 0) {
            logsDiv.innerHTML = data.logs.map(log => `<div>${log}</div>`).join('');
            logsDiv.scrollTop = logsDiv.scrollHeight;
        } else {
            logsDiv.innerHTML = '<div style="color:var(--text-muted);">Aguardando atividade...</div>';
        }
    } catch (e) {
        console.error("Erro no polling do autopilot:", e);
    }
}

document.getElementById('start-import-btn').addEventListener('click', async () => {
    const text = document.getElementById('import-textarea').value.trim();
    if (!text) {
        showToast('Insira pelo menos um domínio ou empresa por linha.', 'error');
        return;
    }
    
    const autoApprove = document.getElementById('import_auto_approve').checked;
    
    try {
        const response = await fetch('/api/leads/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ leads: text, auto_approve: autoApprove })
        });
        const data = await response.json();
        
        showToast('Processamento de importação iniciado!');
        document.getElementById('import-textarea').value = '';
        checkActiveImporter();
    } catch (e) {
        showToast('Erro ao iniciar importação.', 'error');
    }
});

async function checkActiveImporter() {
    try {
        const response = await fetch('/api/leads/import/status');
        const data = await response.json();
        const startBtn = document.getElementById('start-import-btn');
        
        if (data.is_importing) {
            startBtn.disabled = true;
            startBtn.innerText = 'Importando leads...';
            document.getElementById('importer-progress-container').style.display = 'block';
            startPollingImporter();
        } else {
            startBtn.disabled = false;
            startBtn.innerText = 'Processar e Importar Lista';
        }
    } catch (e) {
        console.error("Erro ao verificar importador ativo:", e);
    }
}

function startPollingImporter() {
    if (importerInterval) clearInterval(importerInterval);
    
    pollImporterStatus();
    importerInterval = setInterval(pollImporterStatus, 2000);
}

async function pollImporterStatus() {
    try {
        const response = await fetch('/api/leads/import/status');
        const data = await response.json();
        
        const status = data.status;
        const total = status.total || 0;
        const current = status.current || 0;
        
        let percent = 0;
        if (total > 0) {
            percent = Math.round((current / total) * 100);
        }
        
        document.getElementById('importer-percent').innerText = `${percent}%`;
        document.getElementById('importer-progress-fill').style.width = `${percent}%`;
        
        if (status.status === 'running') {
            document.getElementById('importer-status-text').innerText = `Processando (${current}/${total})...`;
        } else if (status.status === 'completed') {
            document.getElementById('importer-status-text').innerText = 'Concluído!';
            document.getElementById('start-import-btn').disabled = false;
            document.getElementById('start-import-btn').innerText = 'Processar e Importar Lista';
            clearInterval(importerInterval);
        } else if (status.status === 'failed') {
            document.getElementById('importer-status-text').innerText = 'Falhou!';
            document.getElementById('start-import-btn').disabled = false;
            document.getElementById('start-import-btn').innerText = 'Processar e Importar Lista';
            clearInterval(importerInterval);
        }
        
        const logsDiv = document.getElementById('importer-logs');
        if (status.logs && status.logs.length > 0) {
            logsDiv.innerHTML = status.logs.map(log => `<div>${log}</div>`).join('');
            logsDiv.scrollTop = logsDiv.scrollHeight;
        }
    } catch (e) {
        console.error("Erro no polling do importador:", e);
    }
}

// Global background sync to refresh active tab lists periodically
setInterval(async () => {
    if (document.hidden) return;
    try {
        if (currentTab === 'tab-leads') {
            await loadLeads();
        } else if (currentTab === 'tab-surgical') {
            await loadSurgicalLeads();
        } else if (currentTab === 'tab-international') {
            await loadInternationalLeads();
        } else if (currentTab === 'tab-queue') {
            await loadQueueStatus();
            await loadSentHistory();
        } else if (currentTab === 'tab-followup') {
            await loadFollowupList();
        }
    } catch (e) {
        console.error("Erro no sincronizador global:", e);
    }
}, 15000);

// ==========================================
// 12. INTERNATIONAL PROSPECTING
// ==========================================
let intlProspects = [];
let intlSearchInterval = null;
let intlFilter = 'all';

async function loadInternationalTab() {
    loadInternationalLeads();
    checkActiveInternationalSearch();
    setupInternationalListeners();
}

async function checkActiveInternationalSearch() {
    try {
        const response = await fetch('/api/international/status');
        const data = await response.json();
        const runBtn = document.getElementById('start-intl-search-btn');
        if (data.is_searching) {
            runBtn.disabled = true;
            runBtn.innerHTML = `
                <span style="display:inline-block; margin-right:8px; width:10px; height:10px; background-color:#a855f7; border-radius:50%; animation: pulse 1.5s infinite;"></span>
                Buscando no Exterior...
            `;
            startPollingInternationalLogs();
        } else {
            runBtn.disabled = false;
            runBtn.innerHTML = `🚀 Iniciar Busca Internacional`;
        }
    } catch (e) {
        console.error("Erro ao verificar busca internacional ativa:", e);
    }
}

function startPollingInternationalLogs() {
    if (intlSearchInterval) clearInterval(intlSearchInterval);
    
    const consoleLogs = document.getElementById('intl-console-logs');
    const runBtn = document.getElementById('start-intl-search-btn');
    
    intlSearchInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/international/status');
            const data = await response.json();
            
            if (data.logs && data.logs.length > 0) {
                consoleLogs.innerHTML = data.logs.map(log => `<div>${log}</div>`).join('');
                consoleLogs.scrollTop = consoleLogs.scrollHeight;
            }
            
            if (!data.is_searching) {
                clearInterval(intlSearchInterval);
                runBtn.disabled = false;
                runBtn.innerHTML = `🚀 Iniciar Busca Internacional`;
                showToast("Busca Internacional finalizada!");
                loadInternationalLeads();
            }
        } catch (e) {
            console.error("Erro ao ler logs da busca internacional:", e);
        }
    }, 2000);
}

async function loadInternationalLeads() {
    try {
        const statusQuery = intlFilter === 'all' ? '' : `?status=${intlFilter}`;
        const response = await fetch(`/api/international/prospects${statusQuery}`);
        intlProspects = await response.json();
        
        // Load stats
        const statsResponse = await fetch('/api/international/stats');
        const stats = await statsResponse.json();
        
        // Update stats widgets
        document.getElementById('intl-stat-total').innerText = stats.total;
        document.getElementById('intl-stat-pending').innerText = stats.pending;
        document.getElementById('intl-stat-approved').innerText = stats.approved;
        document.getElementById('intl-stat-failed').innerText = stats.failed;
        
        renderInternationalLeads();
    } catch (e) {
        console.error("Erro ao carregar leads internacionais:", e);
    }
}

function renderInternationalLeads() {
    const tbody = document.getElementById('intl-leads-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (intlProspects.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">
                    Nenhum lead internacional encontrado para o filtro selecionado.
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = intlProspects.map(lead => {
        const badgeClass = {
            'pending': 'badge-warning',
            'approved': 'badge-success',
            'sent': 'badge-secondary',
            'failed': 'badge-danger'
        }[lead.status] || 'badge-secondary';
        
        const statusLabel = {
            'pending': 'Pendente',
            'approved': 'Aprovado',
            'sent': 'Contatado',
            'failed': 'Falhou'
        }[lead.status] || lead.status;

        const email = lead.contact_email || '<span class="text-muted">Nenhum</span>';
        const phone = lead.contact_phone || '<span class="text-muted">Nenhum</span>';
        
        let actionsHtml = '';
        if (lead.status === 'pending') {
            actionsHtml = `
                <button onclick="approveInternationalLead(${lead.id})" class="btn btn-secondary btn-sm" style="background-color: var(--secondary); color: var(--text-primary); margin-right: 4px;">Aprovar</button>
                <button onclick="rejectInternationalLead(${lead.id})" class="btn btn-danger btn-sm" style="margin-right: 4px;">Recusar</button>
            `;
        } else if (lead.status === 'approved') {
            const cleanPhone = (lead.contact_phone || '').replace(/\D/g, '');
            const waLink = cleanPhone 
                ? `https://api.whatsapp.com/send?phone=${cleanPhone}&text=${encodeURIComponent(lead.whatsapp_draft || '')}` 
                : '#';
            const waTarget = cleanPhone ? 'target="_blank"' : '';
            const waDisabled = cleanPhone ? '' : 'disabled style="opacity:0.5; pointer-events:none;"';
            
            actionsHtml = `
                <a href="${waLink}" ${waTarget} onclick="markInternationalContacted(${lead.id})" class="btn btn-secondary btn-sm" ${waDisabled} style="background-color: #25d366; color: white; border: none; margin-right: 4px; display:inline-flex; align-items:center; gap:4px;">
                    💬 WhatsApp
                </a>
                <button onclick="editLead(${lead.id})" class="btn btn-secondary btn-sm" style="margin-right: 4px;">Copiar Copy</button>
            `;
        } else if (lead.status === 'sent') {
            actionsHtml = `
                <span style="color:var(--text-muted); font-size:0.75rem;">Contatado em ${lead.sent_at || ''}</span>
            `;
        } else if (lead.status === 'failed') {
            actionsHtml = `
                <button onclick="approveInternationalLead(${lead.id})" class="btn btn-secondary btn-sm" style="background-color: var(--secondary); color: var(--text-primary); margin-right: 4px;">Reabrir</button>
            `;
        }
        
        const isHot = (lead.opportunity_score || 0) >= 80;
        const hotBadge = isHot 
            ? `<div style="margin-top:6px; display:inline-block; font-size:0.65rem; font-weight:700; color:#ef4444; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.2); padding:2px 6px; border-radius:4px; animation: pulse 2s infinite;">🔥 HOT LEAD</div>` 
            : '';
            
        const scoreColor = isHot ? '#ef4444' : (lead.opportunity_score || 0) >= 50 ? '#f59e0b' : '#3b82f6';
        
        return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                <td style="padding: 12px 8px;">
                    <div style="font-weight:600; color:#f1f5f9; display:flex; align-items:center; gap:6px;">
                        <span>${lead.company_name}</span>
                        ${lead.website ? `<a href="${lead.website}" target="_blank" style="color:var(--secondary); font-size:0.7rem;">🔗 Site/Perfil</a>` : ''}
                    </div>
                    <div style="display:flex; align-items:center; gap:6px; margin-top:4px;">
                        <span class="badge ${badgeClass}" style="font-size:0.65rem; padding: 2px 6px;">${statusLabel}</span>
                        <span style="font-size:0.7rem; color:var(--text-secondary);">${lead.segment}</span>
                    </div>
                </td>
                <td style="padding: 12px 8px;">
                    <div style="font-size:0.8rem; color:#e2e8f0;">📍 ${lead.region}</div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">📅 Captado: <strong>${formatDateTime(lead.created_at)}</strong></div>
                </td>
                <td style="padding: 12px 8px; font-size:0.8rem; line-height:1.4;">
                    <div>📧 ${email}</div>
                    <div>📞 ${phone}</div>
                </td>
                <td style="padding: 12px 8px; font-size:0.85rem; font-weight:600; color:#f8fafc;">
                    ⭐ ${lead.rating ? lead.rating.toFixed(1) : '0.0'}
                    <span style="font-weight:400; font-size:0.75rem; color:var(--text-secondary); display:block; margin-top:2px;">
                        (${lead.reviews_count || 0} reviews)
                    </span>
                </td>
                <td style="padding: 12px 8px;">
                    <div style="font-size:1.1rem; font-weight:800; color:${scoreColor};">${lead.opportunity_score || 0}<span style="font-size:0.75rem; font-weight:400; color:var(--text-muted);">/100</span></div>
                    ${hotBadge}
                </td>
                <td style="padding: 12px 8px;">
                    <div style="display:flex; align-items:center; gap:4px;">
                        ${actionsHtml}
                        <button onclick="deleteInternationalLead(${lead.id})" class="btn btn-secondary btn-sm" style="padding: 4px 6px;">🗑️</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function approveInternationalLead(id) {
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'approved' })
        });
        if (response.ok) {
            showToast("Lead aprovado com sucesso!");
            loadInternationalLeads();
        }
    } catch (e) {
        console.error("Erro ao aprovar lead:", e);
    }
}

async function rejectInternationalLead(id) {
    try {
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'rejected' })
        });
        if (response.ok) {
            showToast("Lead recusado.");
            loadInternationalLeads();
        }
    } catch (e) {
        console.error("Erro ao rejeitar lead:", e);
    }
}

async function markInternationalContacted(id) {
    try {
        const nowStr = new Date().toLocaleString('pt-BR');
        const response = await fetch(`/api/prospects/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'sent', sent_at: nowStr })
        });
        if (response.ok) {
            showToast("Lead marcado como contatado!");
            setTimeout(loadInternationalLeads, 1000);
        }
    } catch (e) {
        console.error("Erro ao marcar lead como contatado:", e);
    }
}

async function deleteInternationalLead(id) {
    if (!confirm("Tem certeza que deseja excluir este lead permanentemente?")) return;
    try {
        const response = await fetch(`/api/prospects/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showToast("Lead excluído permanentemente.");
            loadInternationalLeads();
        }
    } catch (e) {
        console.error("Erro ao excluir lead:", e);
    }
}

function setupInternationalListeners() {
    const runBtn = document.getElementById('start-intl-search-btn');
    if (runBtn) {
        runBtn.replaceWith(runBtn.cloneNode(true));
        document.getElementById('start-intl-search-btn').addEventListener('click', async () => {
            const countryCode = document.getElementById('intl_country').value;
            const cityName = document.getElementById('intl_city').value.trim();
            const segment = document.getElementById('intl_segment').value;
            const limit = document.getElementById('intl_limit').value;
            const sourceMode = document.getElementById('intl_source').value;
            
            if (!cityName) {
                showToast("Por favor, digite uma Cidade/Região para focar a busca.", "error");
                return;
            }
            
            try {
                const response = await fetch('/api/international/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        segment,
                        country_code: countryCode,
                        city_name: cityName,
                        limit: parseInt(limit),
                        source_mode: sourceMode
                    })
                });
                const data = await response.json();
                if (response.ok) {
                    showToast("Busca Internacional iniciada em background!");
                    checkActiveInternationalSearch();
                } else {
                    showToast(data.error || "Erro ao iniciar busca.", "error");
                }
            } catch (e) {
                showToast("Erro de conexão ao iniciar busca.", "error");
            }
        });
    }
    
    document.querySelectorAll('.intl-filter-btn').forEach(btn => {
        btn.replaceWith(btn.cloneNode(true));
    });
    
    document.querySelectorAll('.intl-filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.intl-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            intlFilter = btn.getAttribute('data-status');
            loadInternationalLeads();
        });
    });
}

// Bind callbacks to window scope
window.approveInternationalLead = approveInternationalLead;
window.rejectInternationalLead = rejectInternationalLead;
window.markInternationalContacted = markInternationalContacted;
window.deleteInternationalLead = deleteInternationalLead;
window.loadInternationalTab = loadInternationalTab;

// ==========================================
// 8. DATABASE BACKUP & RESTORE
// ==========================================
window.uploadDatabaseBackup = function(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    if (!confirm(`Tem certeza que deseja restaurar o banco com o arquivo "${file.name}"? Todos os dados atuais do servidor serão substituídos pelos do arquivo.`)) {
        input.value = '';
        return;
    }
    
    const statusDiv = document.getElementById('restore-db-status');
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.style.color = 'var(--text-muted)';
        statusDiv.innerHTML = '⏳ Enviando e restaurando banco de dados... Aguarde alguns segundos.';
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/api/backup/restore', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            if (statusDiv) {
                statusDiv.style.color = 'var(--danger)';
                statusDiv.innerHTML = `❌ Erro: ${data.error}`;
            }
            showToast(data.error, 'error');
        } else {
            if (statusDiv) {
                statusDiv.style.color = 'var(--success)';
                statusDiv.innerHTML = `✅ ${data.message} Recarregando aplicação...`;
            }
            showToast(data.message, 'success');
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        }
    })
    .catch(err => {
        if (statusDiv) {
            statusDiv.style.color = 'var(--danger)';
            statusDiv.innerHTML = `❌ Erro de conexão ao enviar: ${err}`;
        }
        showToast('Erro ao enviar arquivo.', 'error');
    })
    .finally(() => {
        input.value = '';
    });
};
