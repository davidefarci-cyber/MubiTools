/**
 * Grid — Modulo Caricamento REMI
 * Tab: Caricamento REMI (match + conferma) e Dashboard (storico pratiche).
 * L'Anagrafica DL è gestita dal modulo Invio REMI (vedi anagrafica_dl.js).
 */

const CaricamentoRemi = {
    currentTab: 'caricamento',
    matchResults: null,
    matchEffectiveDate: '',
    // Dashboard state
    dashboardStats: null,
    dashboardItems: [],
    dashboardTotal: 0,
    dashboardPage: 1,
    dashboardPageSize: 50,
    dashboardFilters: { status: '', search: '', date_from: '', date_to: '' },
    dashboardAutoRefreshTimer: null,
    dashboardExpandedRows: new Set(),

    render(container) {
        container.innerHTML = `
            <div class="module-tabs" style="display:flex;gap:0;margin-bottom:24px;border-bottom:2px solid var(--border);">
                <button class="module-tab active" data-tab="caricamento" style="padding:12px 24px;background:none;border:none;color:var(--accent);cursor:pointer;font-size:0.95rem;font-weight:600;border-bottom:2px solid var(--accent);margin-bottom:-2px;transition:all 0.2s;">Caricamento REMI</button>
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
                this.stopDashboardAutoRefresh();
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
                this.renderCaricamento(content);
                break;
            case 'dashboard':
                this.renderDashboard(content);
                break;
        }
    },

    // --- Caricamento REMI ---

    renderCaricamento(container) {
        this.matchResults = null;
        this.matchEffectiveDate = '';
        this.renderCaricamentoForm(container);
    },

    renderCaricamentoForm(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title">Caricamento Pratiche REMI</div>
                <div class="form-group">
                    <label>Incolla qui i dati da Excel (due colonne: P.IVA e Codice REMI)</label>
                    <textarea id="remi-paste-area" rows="12" style="width:100%;padding:12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-family:monospace;font-size:0.9rem;resize:vertical;" placeholder="01234567890, IT001E00123456&#10;09876543210, IT001E00654321"></textarea>
                    <p style="color:var(--text-muted);font-size:0.8rem;margin-top:4px;">Una riga per coppia — separatori accettati: tab (da Excel), virgola o spazio</p>
                </div>
                <div class="form-group">
                    <label>Data decorrenza <span style="color:var(--accent-red)">*</span></label>
                    <input type="date" id="remi-effective-date" required style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;max-width:220px;">
                </div>
                <div style="margin-top:16px;">
                    <button class="btn btn-primary" id="btn-remi-match">Esegui Match</button>
                </div>
            </div>`;

        document.getElementById('btn-remi-match').addEventListener('click', () => this.executeMatch());
    },

    parseExcelPaste(text) {
        const rows = [];
        const lines = text.split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;
            // Accetta tab, virgola, punto e virgola o spazi come separatore
            const cols = trimmed.split(/[\t,;]+|\s+/);
            if (cols.length < 2) continue;
            const vatNumber = cols[0].trim();
            const remiCode = cols[1].trim();
            if (vatNumber && remiCode) {
                rows.push({ vat_number: vatNumber, remi_code: remiCode });
            }
        }
        return rows;
    },

    async executeMatch() {
        const text = document.getElementById('remi-paste-area').value;
        const effectiveDate = document.getElementById('remi-effective-date').value;

        if (!effectiveDate) {
            showToast('Inserire la data decorrenza', 'error');
            return;
        }

        const parsed = this.parseExcelPaste(text);
        if (!parsed.length) {
            showToast('Nessuna riga valida trovata. Verificare il formato (P.IVA e Codice REMI separati da tab, virgola o spazio)', 'error');
            return;
        }

        this.matchEffectiveDate = effectiveDate;

        const content = document.getElementById('remi-tab-content');
        content.innerHTML = `
            <div class="card" style="text-align:center;padding:40px;">
                <div class="spinner" style="margin:0 auto 16px;"></div>
                <p style="color:var(--text-muted);">Esecuzione match in corso...</p>
            </div>`;

        try {
            const res = await Auth.apiRequest('/api/caricamento-remi/match', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(parsed),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore durante il match');
            }
            this.matchResults = await res.json();
            this.renderMatchResults(content);
        } catch (err) {
            content.innerHTML = `
                <div class="card">
                    <p style="color:var(--accent-red);">${App.escapeHtml(err.message)}</p>
                    <button class="btn btn-primary" id="btn-remi-retry" style="margin-top:16px;">Riprova</button>
                </div>`;
            document.getElementById('btn-remi-retry').addEventListener('click', () => this.renderCaricamento(content));
        }
    },

    renderMatchResults(container) {
        const results = this.matchResults;
        const matched = results.filter(r => r.matched);
        const notMatched = results.filter(r => !r.matched);

        let warningBanner = '';
        if (notMatched.length > 0) {
            warningBanner = `
                <div style="background:rgba(255,193,7,0.15);border:1px solid rgba(255,193,7,0.4);border-radius:8px;padding:12px 16px;margin-bottom:16px;color:var(--text-primary);font-size:0.9rem;">
                    ⚠ Le righe evidenziate non verranno caricate. Verificare l'anagrafica prima di procedere.
                </div>`;
        }

        const rows = results.map(r => {
            const rowBg = r.matched ? '' : 'background:rgba(220,53,69,0.08);';
            const badge = r.matched
                ? '<span class="badge badge-active">Trovato</span>'
                : '<span class="badge badge-disabled" style="background:rgba(220,53,69,0.15);color:#dc3545;">Non trovato</span>';
            const companyName = r.company_name
                ? App.escapeHtml(r.company_name)
                : '<span style="color:var(--text-muted);font-style:italic;">Verificare in anagrafica</span>';
            const pecAddress = r.pec_address ? App.escapeHtml(r.pec_address) : '—';

            return `
                <tr style="${rowBg}">
                    <td style="font-family:monospace;">${App.escapeHtml(r.vat_number)}</td>
                    <td style="font-family:monospace;">${App.escapeHtml(r.remi_code)}</td>
                    <td>${companyName}</td>
                    <td>${pecAddress}</td>
                    <td>${badge}</td>
                </tr>`;
        }).join('');

        container.innerHTML = `
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                    <span>Risultato Match</span>
                    <span style="font-size:0.85rem;font-weight:normal;color:var(--text-muted);">Data decorrenza: ${App.escapeHtml(this.matchEffectiveDate)}</span>
                </div>
                <div style="margin-bottom:16px;font-size:0.9rem;">
                    <span style="color:var(--accent-green);font-weight:600;">${matched.length} righe trovate</span>,
                    <span style="color:${notMatched.length ? '#dc3545' : 'var(--text-muted)'};font-weight:600;">${notMatched.length} non trovate</span>
                </div>
                ${warningBanner}
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>P.IVA</th>
                                <th>Codice REMI</th>
                                <th>Ragione Sociale</th>
                                <th>PEC</th>
                                <th>Stato</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="display:flex;gap:12px;margin-top:20px;">
                    <button class="btn btn-primary" id="btn-remi-confirm">Conferma Inserimento</button>
                    <button class="btn btn-cancel" id="btn-remi-reset">Nuovo Inserimento</button>
                </div>
            </div>`;

        document.getElementById('btn-remi-confirm').addEventListener('click', () => this.handleConfirm());
        document.getElementById('btn-remi-reset').addEventListener('click', () => {
            this.renderCaricamento(document.getElementById('remi-tab-content'));
        });
    },

    handleConfirm() {
        const results = this.matchResults;
        const matched = results.filter(r => r.matched);
        const notMatched = results.filter(r => !r.matched);

        if (matched.length === 0) {
            showToast('Nessuna riga valida da caricare', 'error');
            return;
        }

        if (notMatched.length > 0) {
            // Mostra modale di conferma
            const body = `
                <p style="margin-bottom:16px;line-height:1.5;">
                    <strong>${notMatched.length} righe non riconosciute</strong> non verranno caricate.<br>
                    Confermi di voler procedere con le <strong>${matched.length} righe valide</strong>?
                </p>`;

            showModal('Conferma inserimento', body, [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                { label: 'Conferma', class: 'btn-primary', onClick: () => {
                    closeModal();
                    this.submitConfirm();
                }},
            ]);
        } else {
            // Tutte matched: conferma diretta
            this.submitConfirm();
        }
    },

    async submitConfirm() {
        const matched = this.matchResults.filter(r => r.matched);
        const rows = matched.map(r => ({
            vat_number: r.vat_number,
            remi_code: r.remi_code,
            company_name: r.company_name,
            pec_address: r.pec_address,
        }));

        const content = document.getElementById('remi-tab-content');
        const confirmBtn = document.getElementById('btn-remi-confirm');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Inserimento in corso...';
        }

        try {
            const res = await Auth.apiRequest('/api/caricamento-remi/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    effective_date: this.matchEffectiveDate,
                    rows: rows,
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore durante l\'inserimento');
            }
            const result = await res.json();
            showToast(`Inserimento completato: ${result.inserted} pratiche caricate con successo`, 'success');

            setTimeout(() => {
                this.renderCaricamento(document.getElementById('remi-tab-content'));
            }, 2000);
        } catch (err) {
            showToast(err.message, 'error');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = 'Conferma Inserimento';
            }
        }
    },

    // --- Dashboard ---

    renderDashboard(container) {
        this.dashboardExpandedRows = new Set();
        container.innerHTML = `
            <div id="dashboard-stats-section">
                <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap;">
                    <div class="card" style="flex:1;min-width:180px;text-align:center;padding:20px;">
                        <div style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Totale Pratiche</div>
                        <div id="stat-total" style="font-size:2rem;font-weight:700;color:var(--text-primary);margin-top:6px;">—</div>
                    </div>
                    <div class="card" style="flex:1;min-width:180px;text-align:center;padding:20px;">
                        <div style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">In Attesa</div>
                        <div id="stat-pending" style="font-size:2rem;font-weight:700;color:#ffc107;margin-top:6px;">—</div>
                    </div>
                    <div class="card" style="flex:1;min-width:180px;text-align:center;padding:20px;">
                        <div style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Inviate</div>
                        <div id="stat-sent" style="font-size:2rem;font-weight:700;color:var(--accent-green);margin-top:6px;">—</div>
                    </div>
                    <div class="card" style="flex:1;min-width:180px;text-align:center;padding:20px;">
                        <div style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Annullate</div>
                        <div id="stat-cancelled" style="font-size:2rem;font-weight:700;color:#e67e22;margin-top:6px;">—</div>
                    </div>
                    <div class="card" style="flex:1;min-width:180px;text-align:center;padding:20px;">
                        <div style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Errori</div>
                        <div id="stat-errors" style="font-size:2rem;font-weight:700;color:#dc3545;margin-top:6px;">—</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                    <span>Storico Pratiche</span>
                    <span id="dashboard-last-send" style="font-size:0.8rem;font-weight:normal;color:var(--text-muted);"></span>
                </div>
                <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:flex-end;">
                    <div style="display:flex;flex-direction:column;gap:4px;">
                        <label style="font-size:0.8rem;color:var(--text-muted);">Stato</label>
                        <select id="dash-filter-status" style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                            <option value="">Tutti</option>
                            <option value="pending">In attesa</option>
                            <option value="sent">Inviati</option>
                            <option value="cancelled">Annullati</option>
                            <option value="error">Errori</option>
                        </select>
                    </div>
                    <div style="display:flex;flex-direction:column;gap:4px;flex:1;min-width:200px;">
                        <label style="font-size:0.8rem;color:var(--text-muted);">Ragione Sociale / P.IVA</label>
                        <input type="text" id="dash-filter-search" placeholder="Cerca..." style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                    </div>
                    <div style="display:flex;flex-direction:column;gap:4px;">
                        <label style="font-size:0.8rem;color:var(--text-muted);">Data decorrenza da</label>
                        <input type="date" id="dash-filter-date-from" style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                    </div>
                    <div style="display:flex;flex-direction:column;gap:4px;">
                        <label style="font-size:0.8rem;color:var(--text-muted);">Data decorrenza a</label>
                        <input type="date" id="dash-filter-date-to" style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-tertiary);color:var(--text-primary);font-size:0.9rem;">
                    </div>
                    <button class="btn btn-sm btn-cancel" id="dash-filter-reset" style="height:38px;">Reimposta filtri</button>
                </div>
                <div id="dashboard-table-container">
                    <div class="spinner" style="margin:30px auto;"></div>
                </div>
                <div id="dashboard-pagination" style="margin-top:16px;"></div>
            </div>`;

        this.bindDashboardFilters();
        this.loadDashboardData();
    },

    bindDashboardFilters() {
        const statusEl = document.getElementById('dash-filter-status');
        const searchEl = document.getElementById('dash-filter-search');
        const dateFromEl = document.getElementById('dash-filter-date-from');
        const dateToEl = document.getElementById('dash-filter-date-to');
        const resetBtn = document.getElementById('dash-filter-reset');

        // Restore current filter values
        if (statusEl) statusEl.value = this.dashboardFilters.status;
        if (searchEl) searchEl.value = this.dashboardFilters.search;
        if (dateFromEl) dateFromEl.value = this.dashboardFilters.date_from;
        if (dateToEl) dateToEl.value = this.dashboardFilters.date_to;

        let searchTimeout = null;

        if (statusEl) statusEl.addEventListener('change', () => {
            this.dashboardFilters.status = statusEl.value;
            this.dashboardPage = 1;
            this.loadDashboardHistory();
        });

        if (searchEl) searchEl.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.dashboardFilters.search = searchEl.value.trim();
                this.dashboardPage = 1;
                this.loadDashboardHistory();
            }, 400);
        });

        if (dateFromEl) dateFromEl.addEventListener('change', () => {
            this.dashboardFilters.date_from = dateFromEl.value;
            this.dashboardPage = 1;
            this.loadDashboardHistory();
        });

        if (dateToEl) dateToEl.addEventListener('change', () => {
            this.dashboardFilters.date_to = dateToEl.value;
            this.dashboardPage = 1;
            this.loadDashboardHistory();
        });

        if (resetBtn) resetBtn.addEventListener('click', () => {
            this.dashboardFilters = { status: '', search: '', date_from: '', date_to: '' };
            if (statusEl) statusEl.value = '';
            if (searchEl) searchEl.value = '';
            if (dateFromEl) dateFromEl.value = '';
            if (dateToEl) dateToEl.value = '';
            this.dashboardPage = 1;
            this.loadDashboardHistory();
        });
    },

    async loadDashboardData() {
        await Promise.all([
            this.loadDashboardStats(),
            this.loadDashboardHistory(),
        ]);
        this.startDashboardAutoRefresh();
    },

    async loadDashboardStats() {
        try {
            const res = await Auth.apiRequest('/api/caricamento-remi/history/stats');
            if (!res.ok) throw new Error('Errore caricamento statistiche');
            this.dashboardStats = await res.json();
            this.renderDashboardStats();
        } catch (err) {
            console.error('Dashboard stats error:', err);
        }
    },

    renderDashboardStats() {
        const s = this.dashboardStats;
        if (!s) return;

        const totalEl = document.getElementById('stat-total');
        const pendingEl = document.getElementById('stat-pending');
        const sentEl = document.getElementById('stat-sent');
        const cancelledEl = document.getElementById('stat-cancelled');
        const errorsEl = document.getElementById('stat-errors');
        const lastSendEl = document.getElementById('dashboard-last-send');

        if (totalEl) totalEl.textContent = s.total_practices;
        if (pendingEl) pendingEl.textContent = s.pending;
        if (sentEl) sentEl.textContent = s.sent;
        if (cancelledEl) cancelledEl.textContent = s.cancelled;
        if (errorsEl) errorsEl.textContent = s.errors;
        if (lastSendEl) {
            lastSendEl.textContent = s.last_send_date
                ? `Ultimo invio: ${this.formatDateTime(s.last_send_date)}`
                : '';
        }
    },

    async loadDashboardHistory() {
        const container = document.getElementById('dashboard-table-container');
        if (!container) return;

        const params = new URLSearchParams();
        params.set('page', this.dashboardPage);
        params.set('page_size', this.dashboardPageSize);
        if (this.dashboardFilters.status) params.set('status', this.dashboardFilters.status);
        if (this.dashboardFilters.search) params.set('search', this.dashboardFilters.search);
        if (this.dashboardFilters.date_from) params.set('date_from', this.dashboardFilters.date_from);
        if (this.dashboardFilters.date_to) params.set('date_to', this.dashboardFilters.date_to);

        try {
            const res = await Auth.apiRequest(`/api/caricamento-remi/history?${params.toString()}`);
            if (!res.ok) throw new Error('Errore caricamento storico');
            const data = await res.json();
            this.dashboardItems = data.items;
            this.dashboardTotal = data.total;
            this.renderDashboardTable();
            this.renderDashboardPagination();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red);">${App.escapeHtml(err.message)}</p>`;
        }
    },

    renderDashboardTable() {
        const container = document.getElementById('dashboard-table-container');
        if (!container) return;

        if (!this.dashboardItems.length) {
            container.innerHTML = '<p style="color:var(--text-muted);padding:20px 0;">Nessuna pratica trovata.</p>';
            return;
        }

        const rows = this.dashboardItems.map((item, idx) => {
            const isExpanded = this.dashboardExpandedRows.has(idx);
            const statusBadge = this.getStatusBadge(item.status);
            const sentAt = item.sent_at ? this.formatDateTime(item.sent_at) : '—';
            const effectiveDate = item.effective_date || '—';
            const remiCount = item.remi_codes.length;

            // Pulsanti azione in base allo stato
            let actionBtns = '';
            const btnStyle = 'width:28px;height:28px;padding:0;border:none;border-radius:4px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:0.85rem;font-weight:700;line-height:1;';
            if (item.status === 'pending') {
                actionBtns = `<button class="btn-status-change" data-idx="${idx}" data-new-status="cancelled" style="${btnStyle}background:rgba(220,53,69,0.15);color:#dc3545;" title="Annulla">&#10005;</button>`;
            } else if (item.status === 'cancelled') {
                actionBtns = `<button class="btn-status-change" data-idx="${idx}" data-new-status="pending" style="${btnStyle}background:rgba(255,193,7,0.2);color:#d4a017;" title="Rimetti in attesa">&#8634;</button>`;
            } else if (item.status === 'sent') {
                actionBtns = `<button class="btn-status-change" data-idx="${idx}" data-new-status="pending" style="${btnStyle}background:rgba(255,193,7,0.2);color:#d4a017;" title="Rimetti in attesa">&#8634;</button>`;
            } else if (item.status === 'error') {
                actionBtns = `<button class="btn btn-sm btn-primary btn-dash-resend" data-idx="${idx}" style="font-size:0.8rem;">Reinvia</button>`;
            }

            const expandIcon = isExpanded ? '&#9660;' : '&#9654;';
            const rowBg = item.status === 'error' ? 'background:rgba(220,53,69,0.06);' : (item.status === 'cancelled' ? 'background:rgba(230,126,34,0.06);' : '');

            let expandedContent = '';
            if (isExpanded) {
                const remiList = item.remi_codes.map(c => `<span style="display:inline-block;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:4px;padding:2px 8px;margin:2px 4px 2px 0;font-family:monospace;font-size:0.85rem;">${App.escapeHtml(c)}</span>`).join('');
                let errorSection = '';
                if (item.status === 'error' && item.error_detail) {
                    errorSection = `
                        <div style="margin-top:10px;padding:10px 14px;background:rgba(220,53,69,0.08);border:1px solid rgba(220,53,69,0.25);border-radius:6px;">
                            <strong style="color:#dc3545;font-size:0.85rem;">Dettaglio errore:</strong>
                            <p style="margin-top:4px;font-size:0.85rem;color:var(--text-primary);">${App.escapeHtml(item.error_detail)}</p>
                        </div>`;
                }
                expandedContent = `
                    <tr class="dash-expanded-row" style="${rowBg}">
                        <td colspan="8" style="padding:12px 20px;border-top:none;">
                            <div style="margin-bottom:6px;font-size:0.85rem;color:var(--text-muted);">Codici REMI:</div>
                            <div style="display:flex;flex-wrap:wrap;">${remiList}</div>
                            ${errorSection}
                        </td>
                    </tr>`;
            }

            return `
                <tr style="${rowBg}cursor:pointer;" class="dash-row-toggle" data-idx="${idx}">
                    <td style="width:24px;color:var(--text-muted);font-size:0.75rem;">${expandIcon}</td>
                    <td><strong>${App.escapeHtml(item.company_name)}</strong></td>
                    <td style="font-family:monospace;">${App.escapeHtml(item.vat_number)}</td>
                    <td>${effectiveDate}</td>
                    <td>${remiCount}</td>
                    <td>${statusBadge}</td>
                    <td>${sentAt}</td>
                    <td style="text-align:right;">${actionBtns}</td>
                </tr>
                ${expandedContent}`;
        }).join('');

        container.innerHTML = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th style="width:24px;"></th>
                            <th>Ragione Sociale</th>
                            <th>P.IVA</th>
                            <th>Data Decorrenza</th>
                            <th>N° REMI</th>
                            <th>Stato</th>
                            <th>Data Invio</th>
                            <th style="text-align:right;">Azioni</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;

        this.bindDashboardTableActions();
    },

    bindDashboardTableActions() {
        document.querySelectorAll('.dash-row-toggle').forEach(row => {
            row.addEventListener('click', (e) => {
                // Don't toggle if clicking a button
                if (e.target.closest('button')) return;
                const idx = parseInt(row.dataset.idx);
                if (this.dashboardExpandedRows.has(idx)) {
                    this.dashboardExpandedRows.delete(idx);
                } else {
                    this.dashboardExpandedRows.add(idx);
                }
                this.renderDashboardTable();
            });
        });

        document.querySelectorAll('.btn-dash-resend').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.dataset.idx);
                const item = this.dashboardItems[idx];
                if (item) this.resendPractices(item);
            });
        });

        document.querySelectorAll('.btn-status-change').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.dataset.idx);
                const newStatus = btn.dataset.newStatus;
                const item = this.dashboardItems[idx];
                if (item) this.changeStatus(item, newStatus);
            });
        });
    },

    async resendPractices(item) {
        const body = `
            <p style="line-height:1.5;">
                Reimpostare <strong>${item.remi_codes.length} pratiche</strong> di
                <strong>${App.escapeHtml(item.company_name)}</strong> in stato
                <strong>In attesa</strong> per il reinvio?
            </p>`;

        showModal('Conferma reinvio', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Reinvia', class: 'btn-primary', onClick: async () => {
                closeModal();
                try {
                    const res = await Auth.apiRequest('/api/caricamento-remi/history/resend', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ practice_ids: item.practice_ids }),
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Errore reinvio');
                    }
                    const result = await res.json();
                    showToast(`${result.updated} pratiche reimpostate per il reinvio`, 'success');
                    this.loadDashboardData();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            }},
        ]);
    },

    async changeStatus(item, newStatus) {
        const statusLabels = { pending: 'In attesa', cancelled: 'Annullata', sent: 'Inviata' };
        const targetLabel = statusLabels[newStatus] || newStatus;

        const body = `
            <p style="line-height:1.5;">
                Cambiare lo stato di <strong>${item.remi_codes.length} pratiche</strong> di
                <strong>${App.escapeHtml(item.company_name)}</strong> a
                <strong>${targetLabel}</strong>?
            </p>`;

        showModal('Conferma cambio stato', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Conferma', class: 'btn-primary', onClick: async () => {
                closeModal();
                try {
                    const res = await Auth.apiRequest('/api/caricamento-remi/history/change-status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ practice_ids: item.practice_ids, new_status: newStatus }),
                    });
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Errore cambio stato');
                    }
                    const result = await res.json();
                    showToast(`${result.updated} pratiche aggiornate a "${targetLabel}"`, 'success');
                    this.loadDashboardData();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            }},
        ]);
    },

    renderDashboardPagination() {
        const container = document.getElementById('dashboard-pagination');
        if (!container) return;

        const totalPages = Math.ceil(this.dashboardTotal / this.dashboardPageSize);
        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        const pages = [];
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.dashboardPage - 2 && i <= this.dashboardPage + 2)) {
                pages.push(i);
            } else if (pages[pages.length - 1] !== '...') {
                pages.push('...');
            }
        }

        const buttons = pages.map(p => {
            if (p === '...') {
                return `<span style="padding:6px 4px;color:var(--text-muted);">...</span>`;
            }
            const isActive = p === this.dashboardPage;
            const style = isActive
                ? 'background:var(--accent);color:#fff;border:1px solid var(--accent);'
                : 'background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);cursor:pointer;';
            return `<button class="dash-page-btn" data-page="${p}" style="${style}padding:6px 12px;border-radius:4px;font-size:0.85rem;" ${isActive ? 'disabled' : ''}>${p}</button>`;
        }).join('');

        const showing = Math.min(this.dashboardPage * this.dashboardPageSize, this.dashboardTotal);
        const from = (this.dashboardPage - 1) * this.dashboardPageSize + 1;

        container.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                <span style="font-size:0.85rem;color:var(--text-muted);">
                    ${from}–${showing} di ${this.dashboardTotal} gruppi
                </span>
                <div style="display:flex;gap:4px;align-items:center;">${buttons}</div>
            </div>`;

        container.querySelectorAll('.dash-page-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.dashboardPage = parseInt(btn.dataset.page);
                this.dashboardExpandedRows = new Set();
                this.loadDashboardHistory();
            });
        });
    },

    getStatusBadge(status) {
        switch (status) {
            case 'pending':
                return '<span class="badge" style="background:rgba(255,193,7,0.15);color:#d4a017;padding:4px 10px;border-radius:12px;font-size:0.8rem;font-weight:600;">In attesa</span>';
            case 'sent':
                return '<span class="badge badge-active" style="padding:4px 10px;border-radius:12px;font-size:0.8rem;font-weight:600;">Inviata</span>';
            case 'cancelled':
                return '<span class="badge" style="background:rgba(230,126,34,0.15);color:#e67e22;padding:4px 10px;border-radius:12px;font-size:0.8rem;font-weight:600;">Annullata</span>';
            case 'error':
                return '<span class="badge" style="background:rgba(220,53,69,0.15);color:#dc3545;padding:4px 10px;border-radius:12px;font-size:0.8rem;font-weight:600;">Errore</span>';
            default:
                return `<span class="badge" style="padding:4px 10px;border-radius:12px;font-size:0.8rem;">${App.escapeHtml(status)}</span>`;
        }
    },

    formatDateTime(isoString) {
        if (!isoString) return '—';
        const d = new Date(isoString);
        return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' })
            + ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    },

    startDashboardAutoRefresh() {
        this.stopDashboardAutoRefresh();
        if (this.dashboardStats && this.dashboardStats.pending > 0) {
            this.dashboardAutoRefreshTimer = setInterval(() => {
                if (this.currentTab === 'dashboard') {
                    this.loadDashboardStats();
                    this.loadDashboardHistory();
                } else {
                    this.stopDashboardAutoRefresh();
                }
            }, 30000);
        }
    },

    stopDashboardAutoRefresh() {
        if (this.dashboardAutoRefreshTimer) {
            clearInterval(this.dashboardAutoRefreshTimer);
            this.dashboardAutoRefreshTimer = null;
        }
    },
};
