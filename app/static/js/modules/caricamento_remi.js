/**
 * MUBI Tools — Modulo Caricamento REMI
 * Tab: Caricamento REMI (placeholder), Anagrafica DL (implementato), Dashboard (placeholder)
 */

const CaricamentoRemi = {
    currentTab: 'anagrafica',
    registry: [],
    searchTerm: '',

    render(container) {
        this.registry = [];
        this.searchTerm = '';

        container.innerHTML = `
            <div class="module-tabs" style="display:flex;gap:0;margin-bottom:24px;border-bottom:2px solid var(--border);">
                <button class="module-tab" data-tab="caricamento" style="padding:12px 24px;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:0.95rem;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.2s;">Caricamento REMI</button>
                <button class="module-tab active" data-tab="anagrafica" style="padding:12px 24px;background:none;border:none;color:var(--accent);cursor:pointer;font-size:0.95rem;font-weight:600;border-bottom:2px solid var(--accent);margin-bottom:-2px;transition:all 0.2s;">Anagrafica DL</button>
                <button class="module-tab" data-tab="dashboard" style="padding:12px 24px;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:0.95rem;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.2s;">Dashboard</button>
            </div>
            <div id="remi-tab-content"></div>
        `;

        container.querySelectorAll('.module-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                container.querySelectorAll('.module-tab').forEach(t => {
                    t.classList.remove('active');
                    t.style.color = 'var(--text-muted)';
                    t.style.fontWeight = 'normal';
                    t.style.borderBottomColor = 'transparent';
                });
                tab.classList.add('active');
                tab.style.color = 'var(--accent)';
                tab.style.fontWeight = '600';
                tab.style.borderBottomColor = 'var(--accent)';
                this.currentTab = tab.dataset.tab;
                this.renderTab();
            });
        });

        this.renderTab();
    },

    renderTab() {
        const content = document.getElementById('remi-tab-content');
        switch (this.currentTab) {
            case 'caricamento':
                content.innerHTML = `
                    <div class="card" style="text-align:center;padding:60px 20px;">
                        <p style="color:var(--text-muted);font-size:1.1rem;">Caricamento REMI</p>
                        <p style="color:var(--text-muted);font-size:0.9rem;margin-top:8px;">In arrivo</p>
                    </div>`;
                break;
            case 'anagrafica':
                this.renderAnagrafica(content);
                break;
            case 'dashboard':
                content.innerHTML = `
                    <div class="card" style="text-align:center;padding:60px 20px;">
                        <p style="color:var(--text-muted);font-size:1.1rem;">Dashboard</p>
                        <p style="color:var(--text-muted);font-size:0.9rem;margin-top:8px;">In arrivo</p>
                    </div>`;
                break;
        }
    },

    // --- Anagrafica DL ---

    renderAnagrafica(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                    <span>Anagrafica Distributori Locali</span>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <input type="text" id="remi-search" placeholder="Cerca per ragione sociale, P.IVA o PEC..." style="width:300px;padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                        <button class="btn btn-primary btn-sm" id="btn-new-dl">+ Nuovo Distributore</button>
                    </div>
                </div>
                <div id="remi-registry-table">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
        `;

        document.getElementById('btn-new-dl').addEventListener('click', () => this.showCreateModal());
        document.getElementById('remi-search').addEventListener('input', (e) => {
            this.searchTerm = e.target.value.trim().toLowerCase();
            this.renderRegistryTable();
        });

        this.loadRegistry();
    },

    async loadRegistry() {
        const container = document.getElementById('remi-registry-table');
        try {
            const res = await Auth.apiRequest('/api/caricamento-remi/registry');
            if (!res.ok) throw new Error('Errore caricamento anagrafica');
            this.registry = await res.json();
            this.renderRegistryTable();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    renderRegistryTable() {
        const container = document.getElementById('remi-registry-table');
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
                ? `<button class="btn btn-sm btn-warn btn-dl-toggle" data-id="${dl.id}" title="Disattiva">Disattiva</button>`
                : `<button class="btn btn-sm btn-success btn-dl-toggle" data-id="${dl.id}" title="Riattiva">Riattiva</button>`;

            return `
                <tr style="${rowStyle}">
                    <td><strong>${App.escapeHtml(dl.company_name)}</strong></td>
                    <td style="font-family:monospace;">${App.escapeHtml(dl.vat_number)}</td>
                    <td>${App.escapeHtml(dl.pec_address)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <div style="display:flex;gap:6px;">
                            <button class="btn btn-sm btn-edit btn-dl-edit" data-id="${dl.id}" title="Modifica">Modifica</button>
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

        this.bindTableActions();
    },

    bindTableActions() {
        document.querySelectorAll('.btn-dl-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const dl = this.registry.find(d => d.id === parseInt(btn.dataset.id));
                if (dl) this.showEditModal(dl);
            });
        });
        document.querySelectorAll('.btn-dl-toggle').forEach(btn => {
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

    // --- Modale creazione ---

    showCreateModal() {
        const body = `
            <form id="dl-create-form">
                <div class="form-group">
                    <label>Ragione Sociale <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="dl-company-name" required placeholder="Es: Distribuzione Gas S.r.l.">
                </div>
                <div class="form-group">
                    <label>Partita IVA <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="dl-vat-number" required maxlength="11" placeholder="11 cifre" style="font-family:monospace;">
                    <div id="dl-vat-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
                <div class="form-group">
                    <label>PEC <span style="color:var(--accent-red)">*</span></label>
                    <input type="email" id="dl-pec-address" required placeholder="esempio@pec.it">
                    <div id="dl-pec-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
            </form>`;

        showModal('Nuovo Distributore', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Crea', class: 'btn-primary', onClick: () => this.createDl() },
        ]);

        this.bindValidationEvents();
    },

    bindValidationEvents() {
        const vatInput = document.getElementById('dl-vat-number');
        const pecInput = document.getElementById('dl-pec-address');

        if (vatInput) {
            vatInput.addEventListener('input', () => {
                const fb = document.getElementById('dl-vat-feedback');
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
                const fb = document.getElementById('dl-pec-feedback');
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
        const companyName = document.getElementById('dl-company-name').value.trim();
        const vatNumber = document.getElementById('dl-vat-number').value.trim();
        const pecAddress = document.getElementById('dl-pec-address').value.trim();

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
            const res = await Auth.apiRequest('/api/caricamento-remi/registry', {
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
            closeModal();
            showToast('Distributore creato con successo', 'success');
            this.loadRegistry();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    // --- Modale modifica ---

    showEditModal(dl) {
        const body = `
            <form id="dl-edit-form">
                <div class="form-group">
                    <label>Ragione Sociale <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="dl-company-name" required value="${App.escapeHtml(dl.company_name)}">
                </div>
                <div class="form-group">
                    <label>Partita IVA <span style="color:var(--accent-red)">*</span></label>
                    <input type="text" id="dl-vat-number" required maxlength="11" value="${App.escapeHtml(dl.vat_number)}" style="font-family:monospace;">
                    <div id="dl-vat-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
                <div class="form-group">
                    <label>PEC <span style="color:var(--accent-red)">*</span></label>
                    <input type="email" id="dl-pec-address" required value="${App.escapeHtml(dl.pec_address)}">
                    <div id="dl-pec-feedback" style="font-size:0.8rem;margin-top:4px;min-height:18px;"></div>
                </div>
            </form>`;

        showModal(`Modifica: ${App.escapeHtml(dl.company_name)}`, body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Salva', class: 'btn-primary', onClick: () => this.saveDl(dl.id) },
        ]);

        this.bindValidationEvents();
    },

    async saveDl(dlId) {
        const companyName = document.getElementById('dl-company-name').value.trim();
        const vatNumber = document.getElementById('dl-vat-number').value.trim();
        const pecAddress = document.getElementById('dl-pec-address').value.trim();

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
            const res = await Auth.apiRequest(`/api/caricamento-remi/registry/${dlId}`, {
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
            closeModal();
            showToast('Distributore aggiornato con successo', 'success');
            this.loadRegistry();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    // --- Toggle attivo/disattivo ---

    async toggleDl(dl) {
        if (dl.is_active) {
            // Disattiva via DELETE
            try {
                const res = await Auth.apiRequest(`/api/caricamento-remi/registry/${dl.id}`, {
                    method: 'DELETE',
                });
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
            // Riattiva via PUT reactivate
            try {
                const res = await Auth.apiRequest(`/api/caricamento-remi/registry/${dl.id}/reactivate`, {
                    method: 'PUT',
                });
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
};
