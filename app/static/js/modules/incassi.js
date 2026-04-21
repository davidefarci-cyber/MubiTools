/**
 * Grid — Modulo Incassi Mubi
 * UI stepper per upload e elaborazione file Excel
 */

const Incassi = {
    files: {
        incassi: null,
        massivo: null,
        conferimento: null,
        piani: null,
    },
    fileIds: {
        incassi: null,
        massivo: null,
        conferimento: null,
        piani: null,
    },
    jobId: null,
    pollTimer: null,

    fileConfigs: [
        { key: 'incassi', label: 'File Incassi/Insoluti', accept: '.txt,.csv', required: true },
        { key: 'massivo', label: 'Estrazione Massiva', accept: '.xlsx,.xls', required: true },
        { key: 'conferimento', label: 'File Conferimento', accept: '.xlsx,.xls', required: true },
        { key: 'piani', label: 'Piani di Rientro', accept: '.xlsx,.xls', required: false },
    ],

    steps: [
        '1. Conversione',
        '2. Importo Aperto',
        '3. Piani Rientro',
        '4. Conferimento',
        '5. Calcolo Incassato',
        '6. Controllo',
    ],

    render(container) {
        this.reset();

        const stepperHtml = this.steps.map((s, i) =>
            `<div class="stepper-step" data-step="${i}">${s}</div>`
        ).join('');

        const uploadsHtml = this.fileConfigs.map(cfg => `
            <div class="upload-box" id="upload-${cfg.key}">
                <div class="dropzone" id="drop-${cfg.key}">
                    <div class="dropzone-icon">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                        </svg>
                    </div>
                    <p class="dropzone-title">${cfg.label}</p>
                    <p class="dropzone-hint">${cfg.accept} ${cfg.required ? '' : '(opzionale)'}</p>
                    <p class="dropzone-filename" id="fname-${cfg.key}"></p>
                </div>
                <input type="file" id="finput-${cfg.key}" accept="${cfg.accept}" style="display:none;">
            </div>
        `).join('');

        container.innerHTML = `
            <div class="card">
                <div class="card-title">Elaborazione Incassi</div>
                <div class="stepper" id="incassi-stepper">${stepperHtml}</div>

                <div class="uploads-grid" id="uploads-section">${uploadsHtml}</div>

                <div style="margin-top:24px;display:flex;gap:12px;align-items:center;" id="action-buttons">
                    <button class="btn btn-primary" id="btn-process" disabled>Avvia Elaborazione</button>
                    <button class="btn btn-cancel" id="btn-clear" style="display:none;">Cancella file</button>
                </div>

                <div id="incassi-progress" style="margin-top:20px;display:none;">
                    <div class="progress-bar"><div class="progress-bar-fill" id="progress-fill" style="width:0%"></div></div>
                    <p style="margin-top:8px;color:var(--text-muted);font-size:0.85rem;" id="progress-text">Preparazione...</p>
                </div>

                <div id="incassi-results" style="margin-top:24px;display:none;"></div>
            </div>
        `;

        this.bindUploadEvents();
        document.getElementById('btn-process').addEventListener('click', () => this.startProcessing());
        document.getElementById('btn-clear').addEventListener('click', () => this.clearFiles());
    },

    reset() {
        this.files = { incassi: null, massivo: null, conferimento: null, piani: null };
        this.fileIds = { incassi: null, massivo: null, conferimento: null, piani: null };
        this.jobId = null;
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = null;
    },

    bindUploadEvents() {
        this.fileConfigs.forEach(cfg => {
            const dropzone = document.getElementById(`drop-${cfg.key}`);
            const input = document.getElementById(`finput-${cfg.key}`);

            dropzone.addEventListener('click', () => input.click());

            input.addEventListener('change', () => {
                if (input.files.length > 0) this.handleFile(cfg.key, input.files[0]);
            });

            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('dragover');
            });
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) this.handleFile(cfg.key, e.dataTransfer.files[0]);
            });
        });
    },

    async handleFile(key, file) {
        const fnameEl = document.getElementById(`fname-${key}`);
        const dropzone = document.getElementById(`drop-${key}`);

        // Show uploading state
        fnameEl.textContent = `Caricamento ${file.name}...`;
        fnameEl.style.color = 'var(--accent-amber)';
        dropzone.style.borderColor = 'var(--accent-amber)';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await Auth.apiRequest('/api/incassi/upload', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore upload');
            }

            const data = await res.json();
            this.files[key] = file;
            this.fileIds[key] = data.file_id;

            const size = (data.size_bytes / 1024).toFixed(1);
            fnameEl.textContent = `${data.original_filename} (${size} KB)`;
            fnameEl.style.color = 'var(--accent-green)';
            dropzone.style.borderColor = 'var(--accent-green)';

        } catch (err) {
            fnameEl.textContent = `Errore: ${err.message}`;
            fnameEl.style.color = 'var(--accent-red)';
            dropzone.style.borderColor = 'var(--accent-red)';
            this.files[key] = null;
            this.fileIds[key] = null;
        }

        this.updateProcessButton();
    },

    updateProcessButton() {
        const allRequired = this.fileConfigs
            .filter(c => c.required)
            .every(c => this.fileIds[c.key] !== null);

        document.getElementById('btn-process').disabled = !allRequired;

        const anyFile = Object.values(this.files).some(f => f !== null);
        document.getElementById('btn-clear').style.display = anyFile ? 'inline-flex' : 'none';
    },

    clearFiles() {
        this.fileConfigs.forEach(cfg => {
            this.files[cfg.key] = null;
            this.fileIds[cfg.key] = null;
            document.getElementById(`fname-${cfg.key}`).textContent = '';
            document.getElementById(`drop-${cfg.key}`).style.borderColor = '';
            document.getElementById(`finput-${cfg.key}`).value = '';
        });
        this.updateProcessButton();
    },

    async startProcessing() {
        const btn = document.getElementById('btn-process');
        btn.disabled = true;
        btn.textContent = 'Avvio in corso...';

        document.getElementById('incassi-progress').style.display = 'block';
        document.getElementById('incassi-results').style.display = 'none';

        try {
            const body = {
                file_incassi_id: this.fileIds.incassi,
                file_massivo_id: this.fileIds.massivo,
                file_conferimento_id: this.fileIds.conferimento,
                file_piani_rientro_id: this.fileIds.piani || null,
            };

            const res = await Auth.apiRequest('/api/incassi/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore avvio elaborazione');
            }

            const data = await res.json();
            this.jobId = data.job_id;

            // Nascondi upload area
            document.getElementById('uploads-section').style.display = 'none';
            document.getElementById('action-buttons').style.display = 'none';

            // Inizia polling
            this.pollStatus();
            this.pollTimer = setInterval(() => this.pollStatus(), 1500);

        } catch (err) {
            showToast(err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Avvia Elaborazione';
            document.getElementById('incassi-progress').style.display = 'none';
        }
    },

    async pollStatus() {
        if (!this.jobId) return;

        try {
            const res = await Auth.apiRequest(`/api/incassi/result/${this.jobId}`);
            if (!res.ok) return;

            const data = await res.json();
            this.updateStepper(data.phases);
            this.updateProgress(data);

            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(this.pollTimer);
                this.pollTimer = null;

                if (data.status === 'completed') {
                    this.showResults(data);
                    showToast('Elaborazione completata con successo', 'success');
                } else {
                    showToast(`Errore: ${data.message}`, 'error');
                    document.getElementById('progress-text').textContent = `Errore: ${data.message}`;
                    document.getElementById('progress-text').style.color = 'var(--accent-red)';
                    // Mostra pannello debug in caso di errore
                    this.showErrorDebug(data);
                }
            }
        } catch {
            // Ignore polling errors
        }
    },

    updateStepper(phases) {
        const stepEls = document.querySelectorAll('#incassi-stepper .stepper-step');
        phases.forEach((phase, i) => {
            if (i < stepEls.length) {
                stepEls[i].className = 'stepper-step';
                if (phase.status === 'completed') stepEls[i].classList.add('completed');
                else if (phase.status === 'running') stepEls[i].classList.add('active');
                else if (phase.status === 'error') stepEls[i].classList.add('error');
            }
        });
    },

    updateProgress(data) {
        const completed = data.phases.filter(p => p.status === 'completed').length;
        const pct = Math.round((completed / 6) * 100);
        document.getElementById('progress-fill').style.width = `${pct}%`;

        const running = data.phases.find(p => p.status === 'running');
        if (running) {
            document.getElementById('progress-text').textContent =
                `Fase ${running.phase}/6: ${running.name} — ${running.message}`;
        } else if (data.status === 'completed') {
            document.getElementById('progress-text').textContent = 'Elaborazione completata';
            document.getElementById('progress-fill').style.width = '100%';
            document.getElementById('progress-fill').style.backgroundColor = 'var(--accent-green)';
        }
    },

    async downloadFile(jobId, fileType) {
        try {
            const res = await fetch(`/api/incassi/download/${jobId}/${fileType}`, {
                headers: Auth.authHeaders()
            });
            if (!res.ok) throw new Error('Download fallito');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            App.showToast('Errore durante il download', 'error');
        }
    },

    showResults(data) {
        const resultsEl = document.getElementById('incassi-results');
        resultsEl.style.display = 'block';

        resultsEl.innerHTML = `
            <div class="card-title">Riepilogo Elaborazione</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;">
                <div class="stat-card">
                    <div class="stat-label">Fatture totali</div>
                    <div class="stat-value">${data.total_fatture}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Incassate</div>
                    <div class="stat-value" style="color:var(--accent-green)">${data.fatture_incassate}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Anomalie</div>
                    <div class="stat-value" style="color:${data.anomalie > 0 ? 'var(--accent-red)' : 'var(--text-primary)'}">${data.anomalie}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Piani rientro</div>
                    <div class="stat-value">${data.piani_rientro}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Nuove righe</div>
                    <div class="stat-value">${data.nuove_righe}</div>
                </div>
            </div>

            ${data.message ? `<p style="color:var(--accent-amber);margin-bottom:16px;font-size:0.9rem;">${App.escapeHtml(data.message)}</p>` : ''}

            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;">
                <button class="btn btn-primary" onclick="Incassi.downloadFile('${data.job_id}', 'conferimento')">
                    Scarica Conferimento Aggiornato
                </button>
                ${data.anomalie > 0 ? `
                    <button class="btn btn-warn" onclick="Incassi.downloadFile('${data.job_id}', 'anomalie')">
                        Scarica Report Anomalie
                    </button>` : ''}
                ${data.nuove_righe > 0 ? `
                    <button class="btn btn-edit" onclick="Incassi.downloadFile('${data.job_id}', 'nuove_righe')">
                        Scarica Nuove Righe
                    </button>` : ''}
            </div>

            <div id="anomalie-table"></div>
            <div id="debug-panel"></div>

            <div style="margin-top:20px;">
                <button class="btn btn-cancel" id="btn-new-elaboration">Nuova Elaborazione</button>
            </div>
        `;

        document.getElementById('btn-new-elaboration').addEventListener('click', () => {
            App.navigate('incassi');
        });

        // Carica dettaglio anomalie
        if (data.anomalie > 0) {
            this.loadAnomalieTable(data.job_id);
        }
        // Carica pannello debug
        this.loadDebugPanel(data.job_id);
    },

    async loadAnomalieTable(jobId) {
        const container = document.getElementById('anomalie-table');
        try {
            const res = await Auth.apiRequest(`/api/incassi/result/${jobId}/anomalie`);
            if (!res.ok) return;
            const data = await res.json();

            if (!data.anomalie.length) return;

            const html = `
                <div class="card-title" style="margin-top:16px;">Anomalie (${data.anomalie.length})</div>
                <div class="table-container">
                    <table>
                        <thead><tr><th>Nr. Fattura</th><th>Tipo</th><th>Dettaglio</th></tr></thead>
                        <tbody>
                            ${data.anomalie.map(a => `
                                <tr>
                                    <td>${App.escapeHtml(a.numero_bolletta)}</td>
                                    <td><span class="badge badge-disabled">${App.escapeHtml(a.tipo)}</span></td>
                                    <td style="color:var(--text-muted)">${App.escapeHtml(a.dettaglio)}</td>
                                </tr>`).join('')}
                        </tbody>
                    </table>
                </div>`;

            container.innerHTML = html;
        } catch {
            // Ignore
        }
    },

    showErrorDebug(data) {
        const resultsEl = document.getElementById('incassi-results');
        resultsEl.style.display = 'block';
        resultsEl.innerHTML = `
            <div style="background:rgba(231,76,60,0.1);border:1px solid var(--accent-red);border-radius:8px;padding:16px;margin-bottom:16px;">
                <div style="font-weight:600;color:var(--accent-red);margin-bottom:8px;">Errore nell'elaborazione</div>
                <pre style="white-space:pre-wrap;word-break:break-word;font-size:0.8rem;color:var(--text-muted);margin:0;">${App.escapeHtml(data.message || 'Errore sconosciuto')}</pre>
            </div>
            <div id="debug-panel"></div>
            <div style="margin-top:20px;">
                <button class="btn btn-cancel" id="btn-new-elaboration">Nuova Elaborazione</button>
            </div>
        `;
        document.getElementById('btn-new-elaboration').addEventListener('click', () => {
            App.navigate('incassi');
        });
        this.loadDebugPanel(data.job_id);
    },

    async loadDebugPanel(jobId) {
        const container = document.getElementById('debug-panel');
        if (!container) return;
        try {
            const res = await Auth.apiRequest(`/api/incassi/result/${jobId}/debug`);
            if (!res.ok) {
                container.innerHTML = '<p style="color:var(--text-muted)">Debug info non disponibile</p>';
                return;
            }
            const data = await res.json();
            container.innerHTML = this.renderDebugHtml(data);
        } catch {
            container.innerHTML = '<p style="color:var(--text-muted)">Impossibile caricare debug info</p>';
        }
    },

    renderDebugHtml(data) {
        const debugInfo = data.debug_info || [];
        if (!debugInfo.length && !data.error_message) {
            return '<p style="color:var(--text-muted)">Nessuna info debug disponibile</p>';
        }

        let html = `
            <details style="margin-top:16px;" open>
                <summary style="cursor:pointer;font-weight:600;color:var(--accent-amber);margin-bottom:12px;font-size:0.95rem;">
                    Debug — Dettagli file e colonne
                </summary>
                <div style="background:var(--bg-secondary);border-radius:8px;padding:16px;font-family:monospace;font-size:0.8rem;">`;

        for (const info of debugInfo) {
            const matchedKeys = Object.keys(info.columns_matched || {});
            const missingKeys = Object.keys(info.columns_missing || {});
            const hasMissing = missingKeys.length > 0;
            const borderColor = hasMissing ? 'var(--accent-red)' : 'var(--accent-green)';

            html += `
                <div style="border-left:3px solid ${borderColor};padding:8px 12px;margin-bottom:12px;">
                    <div style="font-weight:600;color:var(--text-primary);margin-bottom:4px;">
                        ${App.escapeHtml(info.file)}
                    </div>
                    <div style="color:var(--text-muted);margin-bottom:4px;">
                        Foglio usato: <strong>${App.escapeHtml(info.sheet_used || '—')}</strong>
                        &nbsp;|&nbsp; Fogli disponibili: ${(info.sheets_available || []).map(s => App.escapeHtml(s)).join(', ')}
                    </div>`;

            if (matchedKeys.length > 0) {
                html += `<div style="color:var(--accent-green);margin-bottom:2px;">Colonne trovate: ${
                    matchedKeys.map(k => `${App.escapeHtml(k)} → "${App.escapeHtml(info.columns_matched[k])}"`).join(', ')
                }</div>`;
            }

            if (hasMissing) {
                html += `<div style="color:var(--accent-red);margin-bottom:2px;">Colonne MANCANTI: ${
                    missingKeys.map(k => `<strong>${App.escapeHtml(k)}</strong>`).join(', ')
                }</div>`;
            }

            html += `
                    <details style="margin-top:4px;">
                        <summary style="cursor:pointer;color:var(--text-muted);font-size:0.75rem;">
                            Tutte le colonne nel foglio (${(info.columns || []).length})
                        </summary>
                        <div style="margin-top:4px;color:var(--text-muted);word-break:break-all;">
                            ${(info.columns || []).map(c => App.escapeHtml(c)).join(' | ')}
                        </div>
                    </details>
                </div>`;
        }

        html += '</div></details>';
        return html;
    }
};
