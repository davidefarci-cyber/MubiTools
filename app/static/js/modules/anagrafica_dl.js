/**
 * MUBI Tools — Modulo condiviso Anagrafica DL
 * Gestione distributori locali in un modale "stand-alone" (consultazione + CRUD + caricamento massivo).
 * Esposto come `AnagraficaDL.openModal()` per essere richiamato da altri moduli.
 */

const AnagraficaDL = {
    registry: [],
    searchTerm: '',
    currentView: 'table',
    editingDl: null,
    bulkPreviewData: null,
    onCloseCallback: null,

    openModal(onClose) {
        this.registry = [];
        this.searchTerm = '';
        this.currentView = 'table';
        this.editingDl = null;
        this.bulkPreviewData = null;
        this.onCloseCallback = typeof onClose === 'function' ? onClose : null;

        const body = `<div id="anagrafica-dl-body"><div class="spinner" style="margin:20px auto;"></div></div>`;

        const overlay = showModal('Anagrafica Distributori Locali', body, [
            { label: 'Chiudi', class: 'btn-cancel', onClick: () => this.closeAndNotify() },
        ]);

        const modal = overlay.querySelector('.modal');
        if (modal) {
            modal.style.maxWidth = '1000px';
            modal.style.width = '95vw';
            modal.style.maxHeight = '90vh';
            modal.style.display = 'flex';
            modal.style.flexDirection = 'column';
            const modalBody = modal.querySelector('.modal-body');
            if (modalBody) {
                modalBody.style.overflowY = 'auto';
                modalBody.style.flex = '1';
            }
        }

        this.loadRegistry();
    },

    closeAndNotify() {
        closeModal();
        if (this.onCloseCallback) {
            const cb = this.onCloseCallback;
            this.onCloseCallback = null;
            cb();
        }
    },

    getBody() {
        return document.getElementById('anagrafica-dl-body');
    },

    async loadRegistry() {
        const container = this.getBody();
        if (!container) return;
        try {
            const res = await Auth.apiRequest('/api/invio-remi/registry');
            if (!res.ok) throw new Error('Errore caricamento anagrafica');
            this.registry = await res.json();
            this.renderCurrentView();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    renderCurrentView() {
        switch (this.currentView) {
            case 'table': this.renderTableView(); break;
            case 'create': this.renderFormView(null); break;
            case 'edit': this.renderFormView(this.editingDl); break;
            case 'bulk-upload': this.renderBulkUploadView(); break;
            case 'bulk-preview': this.renderBulkPreviewView(); break;
            default: this.renderTableView();
        }
    },

    // --- Vista tabella ---

    renderTableView() {
        const container = this.getBody();
        if (!container) return;

        container.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px;">
                <input type="text" id="adl-search" placeholder="Cerca per ragione sociale, P.IVA o PEC..." value="${App.escapeHtml(this.searchTerm)}" style="flex:1;min-width:220px;padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                <div style="display:flex;gap:8px;">
                    <button class="btn btn-sm" id="adl-btn-bulk" style="background:var(--bg-tertiary);border:1px solid var(--border);color:var(--text-primary);">Caricamento Massivo</button>
                    <button class="btn btn-primary btn-sm" id="adl-btn-new">+ Nuovo Distributore</button>
                </div>
            </div>
            <div id="adl-table-wrap"></div>
        `;

        document.getElementById('adl-btn-new').addEventListener('click', () => {
            this.currentView = 'create';
            this.editingDl = null;
            this.renderCurrentView();
        });
        document.getElementById('adl-btn-bulk').addEventListener('click', () => {
            this.currentView = 'bulk-upload';
            this.renderCurrentView();
        });
        document.getElementById('adl-search').addEventListener('input', (e) => {
            this.searchTerm = e.target.value.trim().toLowerCase();
            this.renderRegistryTable();
        });

        this.renderRegistryTable();
    },

    renderRegistryTable() {
        const container = document.getElementById('adl-table-wrap');
        if (!container) return;

        let filtered = this.registry;
        if (this.searchTerm) {
            filtered = this.registry.filter(dl =>
                dl.company_name.toLowerCase().includes(this.searchTerm) ||
                dl.vat_number.toLowerCase().includes(this.searchTerm) ||
                dl.pec_address.toLowerCase().includes(this.searchTerm)
            );
        }

        if (!filtered.length) {
            container.innerHTML = this.registry.length
                ? '<p style="color:var(--text-muted);padding:16px 0;">Nessun risultato per la ricerca.</p>'
                : '<p style="color:var(--text-muted);padding:16px 0;">Nessun distributore registrato.</p>';
            return;
        }

        const rows = filtered.map(dl => {
            const isActive = dl.is_active;
            const rowStyle = isActive ? '' : 'opacity:0.55;';
            const statusBadge = isActive
                ? '<span class="badge badge-active">Attivo</span>'
                : '<span class="badge badge-disabled">Disattivato</span>';
            const toggleBtn = isActive
                ? `<button class="btn btn-sm btn-warn adl-btn-toggle" data-id="${dl.id}" title="Disattiva">Disattiva</button>`
                : `<button class="btn btn-sm btn-success adl-btn-toggle" data-id="${dl.id}" title="Riattiva">Riattiva</button>`;

            return `
                <tr style="${rowStyle}">
                    <td><strong>${App.escapeHtml(dl.company_name)}</strong></td>
                    <td style="font-family:monospace;">${App.escapeHtml(dl.vat_number)}</td>
                    <td>${App.escapeHtml(dl.pec_address)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <div style="display:flex;gap:6px;">
                            <button class="btn btn-sm btn-edit adl-btn-edit" data-id="${dl.id}" title="Modifica">Modifica</button>
                            ${toggleBtn}
                        </div>
                    </td>
                </tr>`;
        }).join('');

        container.innerHTML = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ragione Sociale</th>
                            <th>P.IVA</th>
                            <th>PEC</th>
                            <th>Stato</th>
                            <th>Azioni</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;

        container.querySelectorAll('.adl-btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const dl = this.registry.find(d => d.id === parseInt(btn.dataset.id));
                if (dl) {
                    this.editingDl = dl;
                    this.currentView = 'edit';
                    this.renderCurrentView();
                }
            });
        });
        container.querySelectorAll('.adl-btn-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const dl = this.registry.find(d => d.id === parseInt(btn.dataset.id));
                if (dl) this.toggleDl(dl);
            });
        });
    },

    // --- Validazione client-side ---

    validateVatNumber(value) {
        if (!value || value.length !== 11 || !/^\d{11}$/.test(value)) return false;
        const digits = value.split('').map(Number);
        let oddSum = 0;
        for (let i = 0; i < 10; i += 2) oddSum += digits[i];
        let evenSum = 0;
        for (let i = 1; i < 10; i += 2) {
            const d = digits[i] * 2;
            evenSum += Math.floor(d / 10) + (d % 10);
        }
        const check = (10 - ((oddSum + evenSum) % 10)) % 10;
        return check === digits[10];
    },

    validateEmail(value) {
        return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value);
    },

    // --- Form creazione / modifica ---

    renderFormView(dl) {
        const container = this.getBody();
        if (!container) return;

        const isEdit = !!dl;
        const title = isEdit ? `Modifica: ${App.escapeHtml(dl.company_name)}` : 'Nuovo Distributore';
        const submitLabel = isEdit ? 'Salva' : 'Crea';

        container.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                <button class="btn btn-sm btn-cancel" id="adl-form-back" title="Torna all'anagrafica">&larr; Anagrafica</button>
                <h3 style="margin:0;font-size:1rem;font-weight:600;color:var(--text-primary);">${title}</h3>
            </div>
            <form id="adl-form" style="max-width:540px;">
                <div class="form-group">
                    <label>Ragione Sociale <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="adl-company-name" required placeholder="Es: Distribuzione Gas S.r.l." value="${isEdit ? App.escapeHtml(dl.company_name) : ''}">
                </div>
                <div class="form-group">
                    <label>Partita IVA <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="adl-vat-number" required maxlength="11" placeholder="11 cifre" style="font-family:monospace;" value="${isEdit ? App.escapeHtml(dl.vat_number) : ''}">
                    <div id="adl-vat-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
                <div class="form-group">
                    <label>PEC <span style="color:var(--accent-red)">*</span></label>
                    <input type="email" id="adl-pec-address" required placeholder="esempio@pec.it" value="${isEdit ? App.escapeHtml(dl.pec_address) : ''}">
                    <div id="adl-pec-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
                <div style="display:flex;gap:8px;margin-top:12px;">
                    <button type="button" class="btn btn-primary" id="adl-form-submit">${submitLabel}</button>
                    <button type="button" class="btn btn-cancel" id="adl-form-cancel">Annulla</button>
                </div>
            </form>`;

        const backBtn = document.getElementById('adl-form-back');
        const cancelBtn = document.getElementById('adl-form-cancel');
        const submitBtn = document.getElementById('adl-form-submit');
        const backToTable = () => {
            this.currentView = 'table';
            this.editingDl = null;
            this.renderCurrentView();
        };
        backBtn.addEventListener('click', backToTable);
        cancelBtn.addEventListener('click', backToTable);
        submitBtn.addEventListener('click', () => {
            if (isEdit) this.saveDl(dl.id);
            else this.createDl();
        });

        this.bindValidationEvents();
    },

    bindValidationEvents() {
        const vatInput = document.getElementById('adl-vat-number');
        const pecInput = document.getElementById('adl-pec-address');

        if (vatInput) {
            vatInput.addEventListener('input', () => {
                const fb = document.getElementById('adl-vat-feedback');
                const v = vatInput.value.trim();
                if (!v) { fb.textContent = ''; return; }
                if (!/^\d*$/.test(v)) {
                    fb.style.color = 'var(--accent-red)';
                    fb.textContent = 'Solo cifre numeriche';
                } else if (v.length < 11) {
                    fb.style.color = 'var(--text-muted)';
                    fb.textContent = `${v.length}/11 cifre`;
                } else if (v.length === 11) {
                    if (this.validateVatNumber(v)) {
                        fb.style.color = 'var(--accent-green)';
                        fb.textContent = 'P.IVA valida';
                    } else {
                        fb.style.color = 'var(--accent-red)';
                        fb.textContent = 'P.IVA non valida (checksum errato)';
                    }
                }
            });
        }

        if (pecInput) {
            pecInput.addEventListener('input', () => {
                const fb = document.getElementById('adl-pec-feedback');
                const v = pecInput.value.trim();
                if (!v) { fb.textContent = ''; return; }
                if (this.validateEmail(v)) {
                    fb.style.color = 'var(--accent-green)';
                    fb.textContent = 'Formato valido';
                } else {
                    fb.style.color = 'var(--accent-red)';
                    fb.textContent = 'Formato email non valido';
                }
            });
        }
    },

    async createDl() {
        const companyName = document.getElementById('adl-company-name').value.trim();
        const vatNumber = document.getElementById('adl-vat-number').value.trim();
        const pecAddress = document.getElementById('adl-pec-address').value.trim();

        if (!companyName) {
            showToast('Inserire la ragione sociale', 'error');
            return;
        }
        if (!this.validateVatNumber(vatNumber)) {
            showToast('Partita IVA non valida (deve essere 11 cifre con checksum corretto)', 'error');
            return;
        }
        if (!this.validateEmail(pecAddress)) {
            showToast('Formato PEC non valido', 'error');
            return;
        }

        try {
            const res = await Auth.apiRequest('/api/invio-remi/registry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_name: companyName,
                    vat_number: vatNumber,
                    pec_address: pecAddress,
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore creazione distributore');
            }
            showToast('Distributore creato con successo', 'success');
            this.currentView = 'table';
            this.editingDl = null;
            this.loadRegistry();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async saveDl(dlId) {
        const companyName = document.getElementById('adl-company-name').value.trim();
        const vatNumber = document.getElementById('adl-vat-number').value.trim();
        const pecAddress = document.getElementById('adl-pec-address').value.trim();

        if (!companyName) {
            showToast('Inserire la ragione sociale', 'error');
            return;
        }
        if (!this.validateVatNumber(vatNumber)) {
            showToast('Partita IVA non valida', 'error');
            return;
        }
        if (!this.validateEmail(pecAddress)) {
            showToast('Formato PEC non valido', 'error');
            return;
        }

        try {
            const res = await Auth.apiRequest(`/api/invio-remi/registry/${dlId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    company_name: companyName,
                    vat_number: vatNumber,
                    pec_address: pecAddress,
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore aggiornamento distributore');
            }
            showToast('Distributore aggiornato con successo', 'success');
            this.currentView = 'table';
            this.editingDl = null;
            this.loadRegistry();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async toggleDl(dl) {
        if (dl.is_active) {
            try {
                const res = await Auth.apiRequest(`/api/invio-remi/registry/${dl.id}`, { method: 'DELETE' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Errore disattivazione');
                }
                showToast(`"${dl.company_name}" disattivato`, 'success');
                this.loadRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        } else {
            try {
                const res = await Auth.apiRequest(`/api/invio-remi/registry/${dl.id}/reactivate`, { method: 'PUT' });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Errore riattivazione');
                }
                showToast(`"${dl.company_name}" riattivato`, 'success');
                this.loadRegistry();
            } catch (err) {
                showToast(err.message, 'error');
            }
        }
    },

    // --- Caricamento massivo ---

    renderBulkUploadView() {
        const container = this.getBody();
        if (!container) return;

        container.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                <button class="btn btn-sm btn-cancel" id="adl-bulk-back">&larr; Anagrafica</button>
                <h3 style="margin:0;font-size:1rem;font-weight:600;color:var(--text-primary);">Caricamento Massivo Distributori</h3>
            </div>
            <div class="form-group">
                <label>Incolla qui i dati da Excel (tre colonne: RAGIONE SOCIALE, P.IVA, INDIRIZZO PEC)</label>
                <textarea id="adl-bulk-paste" rows="12" style="width:100%;padding:12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-family:monospace;font-size:0.9rem;resize:vertical;" placeholder="Distribuzione Gas S.r.l.&#9;01234567890&#9;info@pec-gas.it&#10;Energia Locale S.p.A.&#9;09876543210&#9;pec@energialocale.it"></textarea>
                <p style="color:var(--text-muted);font-size:0.8rem;margin-top:4px;">Una riga per distributore — separatore: tab (copia da Excel). La prima riga viene ignorata se contiene le intestazioni.</p>
            </div>
            <div style="margin-top:12px;">
                <button class="btn btn-primary" id="adl-bulk-parse">Verifica Dati</button>
            </div>`;

        document.getElementById('adl-bulk-back').addEventListener('click', () => {
            this.currentView = 'table';
            this.renderCurrentView();
        });
        document.getElementById('adl-bulk-parse').addEventListener('click', () => this.parseBulkData());
    },

    parseBulkExcelPaste(text) {
        const rows = [];
        const lines = text.split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;
            const cols = trimmed.split('\t');
            if (cols.length < 3) continue;
            const companyName = cols[0].trim();
            const vatNumber = cols[1].trim();
            const pecAddress = cols[2].trim();
            if (companyName.toUpperCase() === 'RAGIONE SOCIALE' || vatNumber.toUpperCase() === 'P. IVA' || vatNumber.toUpperCase() === 'P.IVA') continue;
            if (companyName || vatNumber || pecAddress) {
                rows.push({ company_name: companyName, vat_number: vatNumber, pec_address: pecAddress });
            }
        }
        return rows;
    },

    parseBulkData() {
        const text = document.getElementById('adl-bulk-paste').value;
        const parsed = this.parseBulkExcelPaste(text);

        if (!parsed.length) {
            showToast('Nessuna riga valida trovata. Verificare il formato (3 colonne separate da tab)', 'error');
            return;
        }

        const preview = [];
        const seenVats = new Set();
        for (const row of parsed) {
            let valid = true;
            let error = null;

            if (!row.company_name) {
                valid = false;
                error = 'Ragione sociale mancante';
            } else if (!this.validateVatNumber(row.vat_number)) {
                valid = false;
                error = 'P.IVA non valida';
            } else if (!this.validateEmail(row.pec_address)) {
                valid = false;
                error = 'Formato PEC non valido';
            } else if (seenVats.has(row.vat_number)) {
                valid = false;
                error = 'P.IVA duplicata nel file';
            } else {
                const existingDl = this.registry.find(dl => dl.vat_number === row.vat_number);
                if (existingDl) {
                    valid = false;
                    error = 'P.IVA già presente in anagrafica';
                }
            }

            if (valid) seenVats.add(row.vat_number);
            preview.push({ ...row, valid, error });
        }

        this.bulkPreviewData = preview;
        this.currentView = 'bulk-preview';
        this.renderCurrentView();
    },

    renderBulkPreviewView() {
        const container = this.getBody();
        if (!container) return;

        const preview = this.bulkPreviewData || [];
        const validCount = preview.filter(r => r.valid).length;
        const invalidCount = preview.filter(r => !r.valid).length;

        let warningBanner = '';
        if (invalidCount > 0) {
            warningBanner = `
                <div style="background:rgba(255,193,7,0.15);border:1px solid rgba(255,193,7,0.4);border-radius:8px;padding:12px 16px;margin-bottom:16px;color:var(--text-primary);font-size:0.9rem;">
                    Le righe evidenziate in rosso non verranno caricate. Verificare i dati prima di procedere.
                </div>`;
        }

        const rows = preview.map(r => {
            const rowBg = r.valid ? '' : 'background:rgba(220,53,69,0.08);';
            const badge = r.valid
                ? '<span class="badge badge-active">Valido</span>'
                : `<span class="badge badge-disabled" style="background:rgba(220,53,69,0.15);color:#dc3545;">${App.escapeHtml(r.error)}</span>`;
            return `
                <tr style="${rowBg}">
                    <td>${App.escapeHtml(r.company_name || '—')}</td>
                    <td style="font-family:monospace;">${App.escapeHtml(r.vat_number || '—')}</td>
                    <td>${App.escapeHtml(r.pec_address || '—')}</td>
                    <td>${badge}</td>
                </tr>`;
        }).join('');

        container.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px;">
                <h3 style="margin:0;font-size:1rem;font-weight:600;color:var(--text-primary);">Anteprima Caricamento Massivo</h3>
                <span style="font-size:0.85rem;color:var(--text-muted);">${preview.length} righe totali</span>
            </div>
            <div style="margin-bottom:16px;font-size:0.9rem;">
                <span style="color:var(--accent-green);font-weight:600;">${validCount} valide</span>,
                <span style="color:${invalidCount ? '#dc3545' : 'var(--text-muted)'};font-weight:600;">${invalidCount} con errori</span>
            </div>
            ${warningBanner}
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ragione Sociale</th>
                            <th>P.IVA</th>
                            <th>PEC</th>
                            <th>Stato</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div style="display:flex;gap:12px;margin-top:20px;">
                <button class="btn btn-primary" id="adl-bulk-confirm" ${validCount === 0 ? 'disabled' : ''}>Conferma Inserimento (${validCount})</button>
                <button class="btn btn-cancel" id="adl-bulk-reset">Modifica Dati</button>
            </div>`;

        document.getElementById('adl-bulk-confirm').addEventListener('click', () => this.submitBulkUpload());
        document.getElementById('adl-bulk-reset').addEventListener('click', () => {
            this.currentView = 'bulk-upload';
            this.renderCurrentView();
        });
    },

    async submitBulkUpload() {
        const validRows = (this.bulkPreviewData || []).filter(r => r.valid).map(r => ({
            company_name: r.company_name,
            vat_number: r.vat_number,
            pec_address: r.pec_address,
        }));

        if (!validRows.length) {
            showToast('Nessuna riga valida da caricare', 'error');
            return;
        }

        const confirmBtn = document.getElementById('adl-bulk-confirm');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Inserimento in corso...';
        }

        try {
            const res = await Auth.apiRequest('/api/invio-remi/registry/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(validRows),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore durante il caricamento massivo');
            }
            const result = await res.json();

            let msg = `Caricamento completato: ${result.created} distributori creati`;
            if (result.skipped > 0) msg += `, ${result.skipped} saltati`;
            showToast(msg, 'success');

            if (result.errors && result.errors.length > 0) {
                this.renderBulkServerErrors(result);
            } else {
                this.currentView = 'table';
                this.bulkPreviewData = null;
                this.loadRegistry();
            }
        } catch (err) {
            showToast(err.message, 'error');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = 'Conferma Inserimento';
            }
        }
    },

    renderBulkServerErrors(result) {
        const container = this.getBody();
        if (!container) return;

        const errorRows = result.errors.map(r => `
            <tr style="background:rgba(220,53,69,0.08);">
                <td>${App.escapeHtml(r.company_name || '—')}</td>
                <td style="font-family:monospace;">${App.escapeHtml(r.vat_number || '—')}</td>
                <td>${App.escapeHtml(r.pec_address || '—')}</td>
                <td><span class="badge badge-disabled" style="background:rgba(220,53,69,0.15);color:#dc3545;">${App.escapeHtml(r.error || 'Errore')}</span></td>
            </tr>`).join('');

        container.innerHTML = `
            <h3 style="margin:0 0 16px;font-size:1rem;font-weight:600;color:var(--text-primary);">Risultato Caricamento Massivo</h3>
            <div style="margin-bottom:16px;font-size:0.9rem;">
                <span style="color:var(--accent-green);font-weight:600;">${result.created} creati</span>,
                <span style="color:#dc3545;font-weight:600;">${result.skipped} scartati</span>
            </div>
            <div style="margin-bottom:12px;font-size:0.9rem;color:var(--text-muted);">Righe scartate dal server:</div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ragione Sociale</th>
                            <th>P.IVA</th>
                            <th>PEC</th>
                            <th>Motivo</th>
                        </tr>
                    </thead>
                    <tbody>${errorRows}</tbody>
                </table>
            </div>
            <div style="margin-top:20px;">
                <button class="btn btn-primary" id="adl-bulk-results-back">Torna all'Anagrafica</button>
            </div>`;

        document.getElementById('adl-bulk-results-back').addEventListener('click', () => {
            this.currentView = 'table';
            this.bulkPreviewData = null;
            this.loadRegistry();
        });
    },
};
