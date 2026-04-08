/**
 * MUBI Tools — Modulo Connessione
 * UI con sottosezioni per gestione attivita' connessione gas
 */

const Connessione = {
    currentSubTab: 'crea-riga',
    fileId: null,
    fileName: null,

    subTabs: [
        { key: 'crea-riga', label: 'Crea Riga FILE A' },
    ],

    render(container) {
        this.reset();

        const tabsHtml = this.subTabs.map(tab =>
            `<div class="module-tab${tab.key === this.currentSubTab ? ' active' : ''}" data-tab="${tab.key}">${tab.label}</div>`
        ).join('');

        container.innerHTML = `
            <div class="card">
                <div class="card-title">Connessione</div>
                <div class="module-tabs" id="conn-tabs">${tabsHtml}</div>
                <div id="conn-subtab-content"></div>
            </div>
        `;

        // Bind tab clicks
        document.querySelectorAll('#conn-tabs .module-tab').forEach(el => {
            el.addEventListener('click', () => {
                document.querySelectorAll('#conn-tabs .module-tab').forEach(t => t.classList.remove('active'));
                el.classList.add('active');
                this.currentSubTab = el.dataset.tab;
                this.renderSubTab();
            });
        });

        this.renderSubTab();
    },

    reset() {
        this.fileId = null;
        this.fileName = null;
    },

    renderSubTab() {
        const content = document.getElementById('conn-subtab-content');
        switch (this.currentSubTab) {
            case 'crea-riga':
                this.renderCreaRiga(content);
                break;
            default:
                content.innerHTML = '<p style="color:var(--text-muted);padding:20px;">Sottosezione non trovata.</p>';
        }
    },

    renderCreaRiga(container) {
        container.innerHTML = `
            <div id="cr-upload-section">
                <p style="color:var(--text-muted);margin-bottom:16px;">
                    Carica il FILE B per generare automaticamente le righe nel formato FILE A.
                </p>

                <div class="upload-box">
                    <div class="dropzone" id="cr-dropzone">
                        <div class="dropzone-icon">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                            </svg>
                        </div>
                        <p class="dropzone-title">FILE B</p>
                        <p class="dropzone-hint">.xlsx, .xls</p>
                        <p class="dropzone-filename" id="cr-filename"></p>
                    </div>
                    <input type="file" id="cr-fileinput" accept=".xlsx,.xls" style="display:none;">
                </div>

                <div class="form-group" style="margin-top:16px;max-width:300px;">
                    <label for="cr-sheet-name">Nome foglio da creare</label>
                    <input type="text" id="cr-sheet-name" value="Riga FILE A" placeholder="Riga FILE A">
                </div>

                <div style="margin-top:16px;display:flex;gap:12px;align-items:center;">
                    <button class="btn btn-primary" id="cr-btn-process" disabled>Crea Riga</button>
                    <button class="btn btn-cancel" id="cr-btn-clear" style="display:none;">Cancella file</button>
                </div>
            </div>

            <div id="cr-processing" style="display:none;margin-top:20px;">
                <div class="spinner" style="margin:0 auto;"></div>
                <p style="text-align:center;color:var(--text-muted);margin-top:12px;">Elaborazione in corso...</p>
            </div>

            <div id="cr-results" style="display:none;margin-top:24px;"></div>
        `;

        this.bindCreaRigaEvents();
    },

    bindCreaRigaEvents() {
        const dropzone = document.getElementById('cr-dropzone');
        const input = document.getElementById('cr-fileinput');

        dropzone.addEventListener('click', () => input.click());

        input.addEventListener('change', () => {
            if (input.files.length > 0) this.handleFile(input.files[0]);
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
            if (e.dataTransfer.files.length > 0) this.handleFile(e.dataTransfer.files[0]);
        });

        document.getElementById('cr-btn-process').addEventListener('click', () => this.processFile());
        document.getElementById('cr-btn-clear').addEventListener('click', () => this.clearFile());
    },

    async handleFile(file) {
        const fnameEl = document.getElementById('cr-filename');
        const dropzone = document.getElementById('cr-dropzone');

        fnameEl.textContent = `Caricamento ${file.name}...`;
        fnameEl.style.color = 'var(--accent-amber)';
        dropzone.style.borderColor = 'var(--accent-amber)';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await Auth.apiRequest('/api/connessione/upload', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore upload');
            }

            const data = await res.json();
            this.fileId = data.file_id;
            this.fileName = data.original_filename;

            const size = (data.size_bytes / 1024).toFixed(1);
            fnameEl.textContent = `${data.original_filename} (${size} KB)`;
            fnameEl.style.color = 'var(--accent-green)';
            dropzone.style.borderColor = 'var(--accent-green)';

        } catch (err) {
            fnameEl.textContent = `Errore: ${err.message}`;
            fnameEl.style.color = 'var(--accent-red)';
            dropzone.style.borderColor = 'var(--accent-red)';
            this.fileId = null;
            this.fileName = null;
        }

        this.updateButtons();
    },

    updateButtons() {
        document.getElementById('cr-btn-process').disabled = !this.fileId;
        document.getElementById('cr-btn-clear').style.display = this.fileId ? 'inline-flex' : 'none';
    },

    clearFile() {
        this.fileId = null;
        this.fileName = null;
        document.getElementById('cr-filename').textContent = '';
        document.getElementById('cr-dropzone').style.borderColor = '';
        document.getElementById('cr-fileinput').value = '';
        document.getElementById('cr-results').style.display = 'none';
        this.updateButtons();
    },

    async processFile() {
        if (!this.fileId) return;

        const btn = document.getElementById('cr-btn-process');
        btn.disabled = true;
        btn.textContent = 'Elaborazione...';

        document.getElementById('cr-processing').style.display = 'block';
        document.getElementById('cr-results').style.display = 'none';

        const sheetName = document.getElementById('cr-sheet-name').value.trim() || 'Riga FILE A';

        try {
            const res = await Auth.apiRequest('/api/connessione/crea-riga', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_id: this.fileId,
                    sheet_name: sheetName,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore elaborazione');
            }

            const data = await res.json();
            this.showResults(data, sheetName);
            showToast(`${data.rows_created} riga/e creata/e con successo`, 'success');

        } catch (err) {
            showToast(err.message, 'error');
            document.getElementById('cr-results').style.display = 'block';
            document.getElementById('cr-results').innerHTML = `
                <div style="background:rgba(231,76,60,0.1);border:1px solid var(--accent-red);border-radius:8px;padding:16px;">
                    <div style="font-weight:600;color:var(--accent-red);margin-bottom:8px;">Errore</div>
                    <p style="color:var(--text-muted);margin:0;">${App.escapeHtml(err.message)}</p>
                </div>
            `;
        } finally {
            document.getElementById('cr-processing').style.display = 'none';
            btn.textContent = 'Crea Riga';
            btn.disabled = false;
        }
    },

    showResults(data, sheetName) {
        const resultsEl = document.getElementById('cr-results');
        resultsEl.style.display = 'block';

        let warningsHtml = '';
        if (data.warnings && data.warnings.length > 0) {
            warningsHtml = `
                <div style="background:rgba(243,156,18,0.1);border:1px solid var(--accent-amber);border-radius:8px;padding:16px;margin-top:16px;">
                    <div style="font-weight:600;color:var(--accent-amber);margin-bottom:8px;">
                        Attenzione (${data.warnings.length})
                    </div>
                    <ul style="margin:0;padding-left:20px;color:var(--text-muted);font-size:0.85rem;">
                        ${data.warnings.map(w => `<li>${App.escapeHtml(w)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        resultsEl.innerHTML = `
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px;">
                <div class="stat-card">
                    <div class="stat-label">Righe create</div>
                    <div class="stat-value" style="color:var(--accent-green)">${data.rows_created}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Foglio</div>
                    <div class="stat-value" style="font-size:1rem;">${App.escapeHtml(sheetName)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avvisi</div>
                    <div class="stat-value" style="color:${data.warnings.length > 0 ? 'var(--accent-amber)' : 'var(--text-primary)'}">${data.warnings.length}</div>
                </div>
            </div>

            <div style="display:flex;gap:12px;flex-wrap:wrap;">
                <button class="btn btn-primary" id="cr-btn-download">Scarica Risultato</button>
                <button class="btn btn-cancel" id="cr-btn-new">Nuova Elaborazione</button>
            </div>

            ${warningsHtml}
        `;

        document.getElementById('cr-btn-download').addEventListener('click', () => {
            this.downloadResult(data.job_id);
        });
        document.getElementById('cr-btn-new').addEventListener('click', () => {
            this.renderCreaRiga(document.getElementById('conn-subtab-content'));
        });
    },

    async downloadResult(jobId) {
        try {
            const res = await fetch(`/api/connessione/download/${jobId}`, {
                headers: Auth.authHeaders(),
            });
            if (!res.ok) throw new Error('Download fallito');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = this.fileName || 'risultato.xlsx';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            showToast('Errore durante il download', 'error');
        }
    },
};
