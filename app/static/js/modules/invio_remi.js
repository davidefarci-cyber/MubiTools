/**
 * Grid — Modulo Invio REMI
 * Tabella pratiche pending, impostazioni, invio massivo PEC con SSE
 */

const InvioRemi = {
    pendingGroups: [],
    settings: null,
    pecAccounts: [],
    isSending: false,
    expandedRows: {},

    async render(container) {
        this.pendingGroups = [];
        this.settings = null;
        this.pecAccounts = [];
        this.isSending = false;
        this.expandedRows = {};

        container.innerHTML = `
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                    <span>Invio REMI</span>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <button class="btn btn-sm" id="btn-anagrafica-dl" style="background:var(--bg-tertiary);color:var(--text-muted);" title="Anagrafica Distributori Locali">
                            <span style="display:flex;align-items:center;gap:6px;">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                Anagrafica DL
                            </span>
                        </button>
                        <button class="btn btn-sm" id="btn-invio-settings" style="background:var(--bg-tertiary);color:var(--text-muted);" title="Impostazioni">
                            <span style="display:flex;align-items:center;gap:6px;">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                                Impostazioni
                            </span>
                        </button>
                        <button class="btn btn-primary btn-sm" id="btn-send-all" disabled>Avvia Invio Massivo</button>
                    </div>
                </div>
                <div id="invio-settings-warning"></div>
                <div id="invio-remi-table">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
                <div id="invio-sent-today" style="margin-top:24px;"></div>
            </div>
        `;

        document.getElementById('btn-anagrafica-dl').addEventListener('click', () => {
            AnagraficaDL.openModal(() => this.loadPending());
        });
        document.getElementById('btn-invio-settings').addEventListener('click', () => this.showSettingsModal());
        document.getElementById('btn-send-all').addEventListener('click', () => this.confirmSendAll());

        await Promise.all([this.loadSettings(), this.loadPending()]);
        this.updateSendButton();
    },

    // --- Caricamento dati ---

    async loadSettings() {
        try {
            const res = await Auth.apiRequest('/api/invio-remi/settings');
            if (res.ok) this.settings = await res.json();
        } catch { /* ignore */ }
    },

    async loadPending() {
        const container = document.getElementById('invio-remi-table');
        try {
            const res = await Auth.apiRequest('/api/invio-remi/pending');
            if (!res.ok) throw new Error('Errore caricamento pratiche');
            this.pendingGroups = await res.json();
            this.renderTable();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    async loadPecAccounts() {
        try {
            const res = await Auth.apiRequest('/admin/pec');
            if (res.ok) this.pecAccounts = await res.json();
        } catch { /* ignore */ }
    },

    // --- Tabella pending ---

    renderTable() {
        const container = document.getElementById('invio-remi-table');
        if (!container) return;

        if (!this.pendingGroups.length) {
            container.innerHTML = `
                <div style="text-align:center;padding:40px 20px;">
                    <p style="color:var(--text-muted);font-size:1rem;">Nessuna pratica in attesa di invio</p>
                    <p style="color:var(--text-muted);font-size:0.85rem;margin-top:8px;">Le pratiche caricate dal modulo "Caricamento REMI" appariranno qui.</p>
                </div>`;
            return;
        }

        const rows = this.pendingGroups.map((group, idx) => {
            const isExpanded = this.expandedRows[group.vat_number];
            const statusHtml = this._renderStatusBadge(group._liveStatus || 'pending', group._liveError);
            const expandIcon = isExpanded
                ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>'
                : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>';

            const effectiveDate = group.effective_date
                ? this._formatDate(group.effective_date)
                : '—';

            let expandedContent = '';
            if (isExpanded) {
                const codesList = group.remi_codes.map(code =>
                    `<div style="padding:4px 12px;font-family:monospace;font-size:0.85rem;color:var(--text-primary);">${App.escapeHtml(code)}</div>`
                ).join('');
                expandedContent = `
                    <tr class="remi-expanded-row" data-vat="${App.escapeHtml(group.vat_number)}">
                        <td colspan="6" style="padding:0;">
                            <div style="background:var(--bg-tertiary);padding:12px 16px;border-top:1px solid var(--border);">
                                <div style="color:var(--text-muted);font-size:0.8rem;margin-bottom:6px;font-weight:600;">Codici REMI:</div>
                                ${codesList}
                            </div>
                        </td>
                    </tr>`;
            }

            return `
                <tr class="remi-row" data-vat="${App.escapeHtml(group.vat_number)}" style="cursor:pointer;" title="Clicca per espandere">
                    <td style="width:30px;text-align:center;color:var(--text-muted);">${expandIcon}</td>
                    <td><strong>${App.escapeHtml(group.company_name)}</strong></td>
                    <td style="font-family:monospace;">${App.escapeHtml(group.vat_number)}</td>
                    <td>${App.escapeHtml(group.pec_address)}</td>
                    <td>${effectiveDate}</td>
                    <td style="text-align:center;">${group.practice_count}</td>
                    <td>${statusHtml}</td>
                </tr>
                ${expandedContent}`;
        }).join('');

        container.innerHTML = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:30px;"></th>
                            <th>Ragione Sociale</th>
                            <th>P.IVA</th>
                            <th>PEC</th>
                            <th>Data Decorrenza</th>
                            <th style="text-align:center;">N\u00B0 REMI</th>
                            <th>Stato</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;

        // Bind expand/collapse
        container.querySelectorAll('.remi-row').forEach(row => {
            row.addEventListener('click', () => {
                const vat = row.dataset.vat;
                this.expandedRows[vat] = !this.expandedRows[vat];
                this.renderTable();
            });
        });
    },

    _renderStatusBadge(status, errorDetail) {
        switch (status) {
            case 'pending':
                return '<span class="badge badge-disabled">In attesa</span>';
            case 'generating_pdf':
                return `<span class="badge" style="background:rgba(59,130,246,0.15);color:#3b82f6;animation:pulse 1.5s infinite;">Generazione PDF...</span>`;
            case 'sending':
                return `<span class="badge" style="background:rgba(59,130,246,0.15);color:#3b82f6;animation:pulse 1.5s infinite;">Invio in corso...</span>`;
            case 'sent':
                return '<span class="badge badge-active">Inviato &#10003;</span>';
            case 'error': {
                const tooltip = errorDetail ? ` title="${App.escapeHtml(errorDetail)}"` : '';
                return `<span class="badge" style="background:rgba(220,53,69,0.15);color:#dc3545;cursor:help;"${tooltip}>Errore</span>`;
            }
            default:
                return `<span class="badge badge-disabled">${App.escapeHtml(status)}</span>`;
        }
    },

    _formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            const parts = dateStr.split('-');
            if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
        } catch { /* fallback */ }
        return dateStr;
    },

    // --- Pulsante invio ---

    updateSendButton() {
        const btn = document.getElementById('btn-send-all');
        if (!btn) return;

        const warningContainer = document.getElementById('invio-settings-warning');

        const hasGroups = this.pendingGroups.length > 0;
        const settingsOk = this.settings
            && this.settings.pec_account_id
            && this.settings.subject
            && this.settings.body_template
            && this.settings.docx_template_present;

        btn.disabled = !hasGroups || !settingsOk || this.isSending;

        if (warningContainer) {
            if (!settingsOk && hasGroups) {
                const missing = [];
                if (!this.settings || !this.settings.pec_account_id) missing.push('Account PEC');
                if (!this.settings || !this.settings.subject) missing.push('Oggetto PEC');
                if (!this.settings || !this.settings.body_template) missing.push('Testo PEC');
                if (!this.settings || !this.settings.docx_template_present) missing.push('Template DOCX');

                warningContainer.innerHTML = `
                    <div style="background:rgba(255,193,7,0.15);border:1px solid rgba(255,193,7,0.4);border-radius:8px;padding:10px 16px;margin-bottom:16px;font-size:0.85rem;color:var(--text-primary);">
                        Impostazioni incomplete: <strong>${missing.join(', ')}</strong>. Configura le impostazioni per abilitare l'invio.
                    </div>`;
            } else {
                warningContainer.innerHTML = '';
            }
        }
    },

    // --- Impostazioni (modale) ---

    async showSettingsModal() {
        await Promise.all([this.loadSettings(), this.loadPecAccounts()]);

        const s = this.settings || {};
        const pecOptions = this.pecAccounts
            .filter(p => p.is_active)
            .map(p => {
                const selected = s.pec_account_id == p.id ? 'selected' : '';
                return `<option value="${p.id}" ${selected}>${App.escapeHtml(p.label)} (${App.escapeHtml(p.email)})</option>`;
            }).join('');

        const hasTemplate = s.docx_template_present;

        const templateSection = hasTemplate
            ? `<div style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--bg-tertiary);border-radius:6px;">
                    <span style="color:var(--accent-green);font-weight:600;">&#10003;</span>
                    <span style="color:var(--text-primary);flex:1;">${App.escapeHtml(s.docx_template_filename || 'remi_template.docx')}</span>
                    <button class="btn btn-sm" id="btn-download-template" style="background:var(--bg-secondary);color:var(--text-primary);">Scarica per verifica</button>
                    <button class="btn btn-sm" id="btn-replace-template" style="background:var(--bg-secondary);color:var(--accent-amber);">Sostituisci</button>
               </div>
               <div id="template-upload-zone" style="display:none;margin-top:12px;"></div>`
            : `<div id="template-upload-zone"></div>`;

        const body = `
            <form id="invio-settings-form">
                <div class="form-group">
                    <label>Invia da PEC</label>
                    <select id="setting-pec-account" style="width:100%;">
                        <option value="">— Seleziona account PEC —</option>
                        ${pecOptions}
                    </select>
                </div>
                <div class="form-group">
                    <label>Oggetto PEC</label>
                    <input type="text" id="setting-subject" value="${App.escapeHtml(s.subject || '')}" placeholder="Oggetto della PEC">
                </div>
                <div class="form-group">
                    <label>Testo PEC</label>
                    <textarea id="setting-body-template" rows="6" style="width:100%;resize:vertical;" placeholder="Corpo della PEC...">${App.escapeHtml(s.body_template || '')}</textarea>
                    <details style="margin-top:8px;">
                        <summary style="color:var(--text-muted);font-size:0.8rem;cursor:pointer;user-select:none;">Tag disponibili per le sostituzioni</summary>
                        <div style="margin-top:8px;overflow-x:auto;">
                            <table style="width:100%;font-size:0.8rem;border-collapse:collapse;">
                                <thead>
                                    <tr style="border-bottom:1px solid var(--border);">
                                        <th style="text-align:left;padding:6px 8px;color:var(--text-muted);">Tag</th>
                                        <th style="text-align:left;padding:6px 8px;color:var(--text-muted);">Descrizione</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style="border-bottom:1px solid var(--border);">
                                        <td style="padding:6px 8px;"><code>&lt;REMI&gt;</code></td>
                                        <td style="padding:6px 8px;color:var(--text-primary);">Codici REMI (PEC: virgola; DOCX: tabella)</td>
                                    </tr>
                                    <tr style="border-bottom:1px solid var(--border);">
                                        <td style="padding:6px 8px;"><code>&lt;NOME_DL&gt;</code></td>
                                        <td style="padding:6px 8px;color:var(--text-primary);">Ragione sociale del distributore</td>
                                    </tr>
                                    <tr style="border-bottom:1px solid var(--border);">
                                        <td style="padding:6px 8px;"><code>&lt;PEC_DL&gt;</code></td>
                                        <td style="padding:6px 8px;color:var(--text-primary);">Indirizzo PEC del distributore</td>
                                    </tr>
                                    <tr style="border-bottom:1px solid var(--border);">
                                        <td style="padding:6px 8px;"><code>&lt;DATA_DECORRENZA&gt;</code></td>
                                        <td style="padding:6px 8px;color:var(--text-primary);">Data decorrenza (DD/MM/YYYY)</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:6px 8px;"><code>&lt;DATA&gt;</code></td>
                                        <td style="padding:6px 8px;color:var(--text-primary);">Data di oggi (DD/MM/YYYY)</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </details>
                </div>
                <div class="form-group">
                    <label>Template DOCX</label>
                    ${templateSection}
                </div>
                <hr style="border:none;border-top:1px solid var(--border);margin:20px 0 16px;">
                <div class="form-group">
                    <label>Aggiorna indirizzi PEC</label>
                    <p style="color:var(--text-muted);font-size:0.8rem;margin-bottom:8px;">Se hai corretto un indirizzo PEC in anagrafica, usa questo tasto per aggiornare tutte le pratiche in attesa di invio con i dati aggiornati.</p>
                    <button class="btn btn-sm" id="btn-sync-registry" style="background:var(--bg-tertiary);color:var(--text-primary);">
                        <span style="display:flex;align-items:center;gap:6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                            Sincronizza da Anagrafica
                        </span>
                    </button>
                    <div id="sync-registry-result" style="margin-top:8px;min-height:18px;"></div>
                </div>
            </form>`;

        showModal('Impostazioni Invio REMI', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Salva Impostazioni', class: 'btn-primary', onClick: () => this.saveSettings() },
        ]);

        // Upload zone
        if (!hasTemplate) {
            this._renderUploadZone('template-upload-zone');
        }

        // Scarica template
        const downloadBtn = document.getElementById('btn-download-template');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                try {
                    const res = await Auth.apiRequest('/api/invio-remi/settings/template');
                    if (!res.ok) throw new Error('Errore download template');
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = s.docx_template_filename || 'remi_template.docx';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        }

        // Sostituisci template
        const replaceBtn = document.getElementById('btn-replace-template');
        if (replaceBtn) {
            replaceBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const zone = document.getElementById('template-upload-zone');
                zone.style.display = 'block';
                this._renderUploadZone('template-upload-zone');
            });
        }

        // Sincronizza PEC da anagrafica
        const syncBtn = document.getElementById('btn-sync-registry');
        if (syncBtn) {
            syncBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                const resultDiv = document.getElementById('sync-registry-result');
                syncBtn.disabled = true;
                syncBtn.style.opacity = '0.6';
                resultDiv.innerHTML = '<span style="color:var(--text-muted);font-size:0.85rem;">Sincronizzazione in corso...</span>';
                try {
                    const res = await Auth.apiRequest('/api/invio-remi/sync-registry', { method: 'POST' });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Errore sincronizzazione');
                    }
                    const data = await res.json();
                    if (data.updated > 0) {
                        resultDiv.innerHTML = `<span style="color:var(--accent-green);font-size:0.85rem;font-weight:600;">${data.updated} pratiche aggiornate su ${data.total_pending} in attesa</span>`;
                    } else {
                        resultDiv.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem;">Nessun aggiornamento necessario (${data.total_pending} pratiche in attesa gi\u00E0 allineate)</span>`;
                    }
                } catch (err) {
                    resultDiv.innerHTML = `<span style="color:var(--accent-red);font-size:0.85rem;">${App.escapeHtml(err.message)}</span>`;
                } finally {
                    syncBtn.disabled = false;
                    syncBtn.style.opacity = '1';
                }
            });
        }
    },

    _renderUploadZone(containerId) {
        const zone = document.getElementById(containerId);
        if (!zone) return;

        zone.innerHTML = `
            <div id="docx-drop-zone" style="border:2px dashed var(--border);border-radius:var(--radius);padding:30px 20px;text-align:center;cursor:pointer;transition:border-color 0.2s,background 0.2s;">
                <p style="color:var(--text-muted);margin-bottom:4px;">Trascina qui il file .docx oppure clicca per selezionarlo</p>
                <input type="file" id="docx-file-input" accept=".docx" style="display:none;">
                <p id="docx-file-name" style="color:var(--text-primary);font-weight:600;margin-top:8px;display:none;"></p>
            </div>`;

        const dropZone = document.getElementById('docx-drop-zone');
        const fileInput = document.getElementById('docx-file-input');
        const fileName = document.getElementById('docx-file-name');

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--accent)';
            dropZone.style.background = 'var(--bg-tertiary)';
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = 'transparent';
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = 'transparent';
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                fileName.textContent = e.dataTransfer.files[0].name;
                fileName.style.display = 'block';
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                fileName.textContent = fileInput.files[0].name;
                fileName.style.display = 'block';
            }
        });
    },

    async saveSettings() {
        const pecAccountId = document.getElementById('setting-pec-account').value;
        const subject = document.getElementById('setting-subject').value.trim();
        const bodyTemplate = document.getElementById('setting-body-template').value;
        const fileInput = document.getElementById('docx-file-input');

        const formData = new FormData();
        if (pecAccountId) formData.append('pec_account_id', pecAccountId);
        formData.append('subject', subject);
        formData.append('body_template', bodyTemplate);

        if (fileInput && fileInput.files.length > 0) {
            formData.append('docx_template', fileInput.files[0]);
        }

        try {
            const res = await Auth.apiRequest('/api/invio-remi/settings', {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore salvataggio impostazioni');
            }
            closeModal();
            showToast('Impostazioni salvate con successo', 'success');
            await this.loadSettings();
            this.updateSendButton();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    // --- Invio massivo ---

    confirmSendAll() {
        if (this.isSending) return;

        const count = this.pendingGroups.length;
        const totalPractices = this.pendingGroups.reduce((sum, g) => sum + g.practice_count, 0);

        showModal('Conferma Invio Massivo', `
            <p style="margin-bottom:16px;line-height:1.5;">
                Stai per inviare <strong>${totalPractices} pratiche REMI</strong> a <strong>${count} distributori</strong> via PEC.
            </p>
            <p style="color:var(--text-muted);font-size:0.85rem;">
                Per ogni distributore verr\u00E0 generato un PDF dal template e inviato via PEC con i codici REMI.
                L'operazione non pu\u00F2 essere annullata.
            </p>`, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Conferma Invio', class: 'btn-primary', onClick: () => { closeModal(); this.executeSendAll(); } },
        ]);
    },

    async executeSendAll() {
        if (this.isSending) return;
        this.isSending = true;

        const btn = document.getElementById('btn-send-all');
        const total = this.pendingGroups.length;
        let processed = 0;

        btn.disabled = true;
        btn.textContent = `Invio in corso... (0/${total})`;

        // Reset live statuses
        this.pendingGroups.forEach(g => {
            g._liveStatus = 'pending';
            g._liveError = null;
        });
        this.renderTable();

        try {
            const token = Auth.getToken();
            const response = await fetch('/api/invio-remi/send-all', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
            });

            if (!response.ok) {
                if (response.status === 401) {
                    Auth.clearSession();
                    window.location.reload();
                    return;
                }
                const err = await response.json();
                throw new Error(err.detail || 'Errore avvio invio massivo');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.substring(6));
                        this._handleSSEEvent(event);

                        if (event.type === 'complete') {
                            // Final event
                            const msg = `Invio completato: ${event.sent} inviati, ${event.errors} errori`;
                            showToast(msg, event.errors > 0 ? 'warning' : 'success', 5000);
                        } else if (event.status === 'sent' || event.status === 'error') {
                            processed++;
                            btn.textContent = `Invio in corso... (${processed}/${total})`;
                        }
                    } catch { /* skip malformed events */ }
                }
            }
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            this.isSending = false;
            btn.textContent = 'Avvia Invio Massivo';

            // Refresh the table to show final state and move sent items
            await this._finalizeAfterSend();
        }
    },

    _handleSSEEvent(event) {
        if (event.type === 'complete') return;

        const group = this.pendingGroups.find(g => g.vat_number === event.vat_number);
        if (!group) return;

        group._liveStatus = event.status;
        if (event.error) group._liveError = event.error;

        // Update just the status badge in the row without full re-render
        const row = document.querySelector(`.remi-row[data-vat="${CSS.escape(event.vat_number)}"]`);
        if (row) {
            const cells = row.querySelectorAll('td');
            const statusCell = cells[cells.length - 1]; // Last cell is status
            if (statusCell) {
                statusCell.innerHTML = this._renderStatusBadge(event.status, event.error);
            }
        }
    },

    async _finalizeAfterSend() {
        // Separate sent groups for "Inviati oggi" section
        const sentGroups = this.pendingGroups.filter(g => g._liveStatus === 'sent');
        const errorGroups = this.pendingGroups.filter(g => g._liveStatus === 'error');

        // Reload pending (will only show remaining pending + error ones)
        await this.loadPending();
        this.updateSendButton();

        // Show "sent today" collapsible section
        if (sentGroups.length > 0) {
            const sentContainer = document.getElementById('invio-sent-today');
            if (sentContainer) {
                const sentRows = sentGroups.map(g => `
                    <tr>
                        <td><strong>${App.escapeHtml(g.company_name)}</strong></td>
                        <td style="font-family:monospace;">${App.escapeHtml(g.vat_number)}</td>
                        <td>${App.escapeHtml(g.pec_address)}</td>
                        <td style="text-align:center;">${g.practice_count}</td>
                        <td><span class="badge badge-active">Inviato &#10003;</span></td>
                    </tr>`).join('');

                sentContainer.innerHTML = `
                    <div style="border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;">
                        <div id="sent-today-header" style="padding:12px 16px;background:var(--bg-tertiary);cursor:pointer;display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-weight:600;color:var(--text-primary);">Inviati oggi (${sentGroups.length})</span>
                            <svg id="sent-today-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transition:transform 0.2s;"><polyline points="6 9 12 15 18 9"/></svg>
                        </div>
                        <div id="sent-today-content" style="display:none;">
                            <div class="table-container">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Ragione Sociale</th>
                                            <th>P.IVA</th>
                                            <th>PEC</th>
                                            <th style="text-align:center;">N\u00B0 REMI</th>
                                            <th>Stato</th>
                                        </tr>
                                    </thead>
                                    <tbody>${sentRows}</tbody>
                                </table>
                            </div>
                        </div>
                    </div>`;

                document.getElementById('sent-today-header').addEventListener('click', () => {
                    const content = document.getElementById('sent-today-content');
                    const chevron = document.getElementById('sent-today-chevron');
                    if (content.style.display === 'none') {
                        content.style.display = 'block';
                        chevron.style.transform = 'rotate(180deg)';
                    } else {
                        content.style.display = 'none';
                        chevron.style.transform = 'rotate(0deg)';
                    }
                });
            }
        }
    },
};
