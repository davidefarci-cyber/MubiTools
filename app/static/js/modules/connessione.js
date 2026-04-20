/**
 * Grid — Modulo Connessione
 * UI con sottosezioni per gestione attivita' connessione gas
 */

const Connessione = {
    currentSubTab: 'crea-riga',
    fileId: null,
    fileName: null,
    xmlFileId: null,
    xmlFileName: null,

    subTabs: [
        { key: 'crea-riga', label: 'Crea riga per CONNESSIONI' },
        { key: 'estrai-pod', label: 'Estrai POD XML' },
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
        this.xmlFileId = null;
        this.xmlFileName = null;
    },

    renderSubTab() {
        const content = document.getElementById('conn-subtab-content');
        switch (this.currentSubTab) {
            case 'crea-riga':
                this.renderCreaRiga(content);
                break;
            case 'estrai-pod':
                this.renderEstraiPod(content);
                break;
            default:
                content.innerHTML = '<p style="color:var(--text-muted);padding:20px;">Sottosezione non trovata.</p>';
        }
    },

    // -----------------------------------------------------------------------
    // Tab: Crea riga per CONNESSIONI
    // -----------------------------------------------------------------------

    renderCreaRiga(container) {
        this.fileId = null;
        this.fileName = null;

        container.innerHTML = `
            <div id="cr-upload-section">
                <p style="color:var(--text-muted);margin-bottom:16px;">
                    Trascina o seleziona il file Excel per generare le righe connessione.
                </p>

                <div class="upload-box">
                    <div class="dropzone" id="cr-dropzone">
                        <div class="dropzone-icon">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                            </svg>
                        </div>
                        <p class="dropzone-title">File Excel</p>
                        <p class="dropzone-hint">.xlsx, .xls — trascina o clicca per selezionare</p>
                        <p class="dropzone-filename" id="cr-filename"></p>
                    </div>
                    <input type="file" id="cr-fileinput" accept=".xlsx,.xls" style="display:none;">
                </div>
            </div>

            <div id="cr-processing" style="display:none;margin-top:20px;">
                <div class="spinner" style="margin:0 auto;"></div>
                <p style="text-align:center;color:var(--text-muted);margin-top:12px;">Elaborazione in corso...</p>
            </div>

            <div id="cr-results" style="display:none;min-width:0;overflow:hidden;"></div>
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

            fnameEl.textContent = `${data.original_filename} — elaborazione...`;
            fnameEl.style.color = 'var(--accent-amber)';

            // Avvia automaticamente l'elaborazione
            await this.processFile();

        } catch (err) {
            fnameEl.textContent = `Errore: ${err.message}`;
            fnameEl.style.color = 'var(--accent-red)';
            dropzone.style.borderColor = 'var(--accent-red)';
            this.fileId = null;
            this.fileName = null;
        }
    },

    async processFile() {
        if (!this.fileId) return;

        document.getElementById('cr-upload-section').style.display = 'none';
        document.getElementById('cr-processing').style.display = 'block';
        document.getElementById('cr-results').style.display = 'none';

        try {
            const res = await Auth.apiRequest('/api/connessione/crea-riga', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_id: this.fileId }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore elaborazione');
            }

            const data = await res.json();
            this.showResults(data);
            showToast(`${data.rows_created} riga/e generata/e`, 'success');

        } catch (err) {
            showToast(err.message, 'error');
            document.getElementById('cr-upload-section').style.display = 'block';
            document.getElementById('cr-results').style.display = 'block';
            document.getElementById('cr-results').innerHTML = `
                <div style="background:rgba(231,76,60,0.1);border:1px solid var(--accent-red);border-radius:8px;padding:16px;margin-top:16px;">
                    <div style="font-weight:600;color:var(--accent-red);margin-bottom:8px;">Errore</div>
                    <p style="color:var(--text-muted);margin:0;">${App.escapeHtml(err.message)}</p>
                </div>
            `;
        } finally {
            document.getElementById('cr-processing').style.display = 'none';
        }
    },

    showResults(data) {
        const resultsEl = document.getElementById('cr-results');
        resultsEl.style.display = 'block';

        const columns = data.columns || [];
        const rows = data.rows || [];

        // Costruisci intestazioni tabella
        const thHtml = columns.map(c => `<th>${App.escapeHtml(c)}</th>`).join('');

        // Costruisci righe tabella
        const tbodyHtml = rows.map(row => {
            const cells = row.map(v => `<td>${App.escapeHtml(v)}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');

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
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px;">
                <div class="stat-card">
                    <div class="stat-label">Righe generate</div>
                    <div class="stat-value" style="color:var(--accent-green)">${data.rows_created}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avvisi</div>
                    <div class="stat-value" style="color:${data.warnings.length > 0 ? 'var(--accent-amber)' : 'var(--text-primary)'}">${data.warnings.length}</div>
                </div>
            </div>

            <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;min-width:0;max-width:100%;">
                <div style="overflow:auto;max-height:260px;">
                    <table id="cr-table" style="border-collapse:collapse;font-size:0.78rem;white-space:nowrap;">
                        <thead>
                            <tr style="position:sticky;top:0;background:var(--bg-secondary);z-index:1;">
                                ${thHtml}
                            </tr>
                        </thead>
                        <tbody>${tbodyHtml}</tbody>
                    </table>
                </div>
            </div>

            <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">
                <button class="btn btn-primary" id="cr-btn-copy">Copia righe</button>
                <button class="btn btn-cancel" id="cr-btn-new">Nuova Elaborazione</button>
            </div>

            ${warningsHtml}
        `;

        // Stili inline per celle tabella
        resultsEl.querySelectorAll('th').forEach(th => {
            Object.assign(th.style, {
                padding: '8px 10px',
                textAlign: 'left',
                fontWeight: '600',
                color: 'var(--text-primary)',
                borderBottom: '2px solid var(--border)',
                fontSize: '0.72rem',
            });
        });
        resultsEl.querySelectorAll('td').forEach(td => {
            Object.assign(td.style, {
                padding: '6px 10px',
                color: 'var(--text-muted)',
                borderBottom: '1px solid var(--border)',
            });
        });

        // Copia righe (senza intestazione) in formato TSV per incolla su Excel
        document.getElementById('cr-btn-copy').addEventListener('click', () => {
            this.copyRowsToClipboard(columns, rows);
        });
        document.getElementById('cr-btn-new').addEventListener('click', () => {
            this.renderCreaRiga(document.getElementById('conn-subtab-content'));
        });
    },

    copyRowsToClipboard(columns, rows) {
        const btn = document.getElementById('cr-btn-copy');

        // TSV: solo dati (senza intestazioni) — pronto per incolla su Excel
        const tsv = rows.map(row => row.join('\t')).join('\r\n');

        // Usa textarea nascosta + execCommand (funziona anche su HTTP)
        const textarea = document.createElement('textarea');
        textarea.value = tsv;
        textarea.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0;';
        document.body.appendChild(textarea);
        textarea.select();

        try {
            document.execCommand('copy');
            btn.textContent = 'Copiato!';
            btn.style.background = 'var(--accent-green)';
            setTimeout(() => {
                btn.textContent = 'Copia righe';
                btn.style.background = '';
            }, 2000);
        } catch {
            showToast('Impossibile copiare negli appunti', 'error');
        } finally {
            document.body.removeChild(textarea);
        }
    },

    // -----------------------------------------------------------------------
    // Tab: Estrai POD XML
    // -----------------------------------------------------------------------

    renderEstraiPod(container) {
        this.xmlFileId = null;
        this.xmlFileName = null;

        container.innerHTML = `
            <div id="ep-upload-section">
                <p style="color:var(--text-muted);margin-bottom:16px;">
                    Carica un file XML e inserisci i codici POD da estrarre. Ogni POD trovato verrà esportato in un file XML separato, scaricabile come archivio ZIP.
                </p>

                <div class="upload-box">
                    <div class="dropzone" id="ep-dropzone">
                        <div class="dropzone-icon">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                            </svg>
                        </div>
                        <p class="dropzone-title">File XML</p>
                        <p class="dropzone-hint">.xml</p>
                        <p class="dropzone-filename" id="ep-filename"></p>
                    </div>
                    <input type="file" id="ep-fileinput" accept=".xml" style="display:none;">
                </div>

                <div class="form-group" style="margin-top:16px;">
                    <label for="ep-pods">Codici POD (uno per riga o separati da virgola)</label>
                    <textarea id="ep-pods" rows="5" placeholder="IT001E00000000&#10;IT001E00000001&#10;IT001E00000002" style="width:100%;max-width:480px;resize:vertical;"></textarea>
                </div>

                <div style="margin-top:16px;display:flex;gap:12px;align-items:center;">
                    <button class="btn btn-primary" id="ep-btn-process" disabled>Estrai POD</button>
                    <button class="btn btn-cancel" id="ep-btn-clear" style="display:none;">Cancella file</button>
                </div>
            </div>

            <div id="ep-processing" style="display:none;margin-top:20px;">
                <div class="spinner" style="margin:0 auto;"></div>
                <p style="text-align:center;color:var(--text-muted);margin-top:12px;">Elaborazione in corso...</p>
            </div>

            <div id="ep-results" style="display:none;margin-top:24px;"></div>
        `;

        this.bindEstraiPodEvents();
    },

    bindEstraiPodEvents() {
        const dropzone = document.getElementById('ep-dropzone');
        const input = document.getElementById('ep-fileinput');
        const textarea = document.getElementById('ep-pods');

        dropzone.addEventListener('click', () => input.click());

        input.addEventListener('change', () => {
            if (input.files.length > 0) this.handleXmlFile(input.files[0]);
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
            if (e.dataTransfer.files.length > 0) this.handleXmlFile(e.dataTransfer.files[0]);
        });

        textarea.addEventListener('input', () => this.updateXmlButtons());

        document.getElementById('ep-btn-process').addEventListener('click', () => this.processEstraiPod());
        document.getElementById('ep-btn-clear').addEventListener('click', () => this.clearXmlFile());
    },

    async handleXmlFile(file) {
        const fnameEl = document.getElementById('ep-filename');
        const dropzone = document.getElementById('ep-dropzone');

        fnameEl.textContent = `Caricamento ${file.name}...`;
        fnameEl.style.color = 'var(--accent-amber)';
        dropzone.style.borderColor = 'var(--accent-amber)';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await Auth.apiRequest('/api/connessione/xml/upload', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore upload');
            }

            const data = await res.json();
            this.xmlFileId = data.file_id;
            this.xmlFileName = data.original_filename;

            const size = (data.size_bytes / 1024).toFixed(1);
            fnameEl.textContent = `${data.original_filename} (${size} KB)`;
            fnameEl.style.color = 'var(--accent-green)';
            dropzone.style.borderColor = 'var(--accent-green)';

        } catch (err) {
            fnameEl.textContent = `Errore: ${err.message}`;
            fnameEl.style.color = 'var(--accent-red)';
            dropzone.style.borderColor = 'var(--accent-red)';
            this.xmlFileId = null;
            this.xmlFileName = null;
        }

        this.updateXmlButtons();
    },

    getPodList() {
        const raw = document.getElementById('ep-pods').value;
        const pods = new Set();
        for (const line of raw.split('\n')) {
            for (const p of line.split(',')) {
                const trimmed = p.trim();
                if (trimmed) pods.add(trimmed);
            }
        }
        return [...pods];
    },

    updateXmlButtons() {
        const hasPods = this.getPodList().length > 0;
        document.getElementById('ep-btn-process').disabled = !this.xmlFileId || !hasPods;
        document.getElementById('ep-btn-clear').style.display = this.xmlFileId ? 'inline-flex' : 'none';
    },

    clearXmlFile() {
        this.xmlFileId = null;
        this.xmlFileName = null;
        document.getElementById('ep-filename').textContent = '';
        document.getElementById('ep-dropzone').style.borderColor = '';
        document.getElementById('ep-fileinput').value = '';
        document.getElementById('ep-results').style.display = 'none';
        this.updateXmlButtons();
    },

    async processEstraiPod() {
        if (!this.xmlFileId) return;

        const pods = this.getPodList();
        if (pods.length === 0) return;

        const btn = document.getElementById('ep-btn-process');
        btn.disabled = true;
        btn.textContent = 'Elaborazione...';

        document.getElementById('ep-processing').style.display = 'block';
        document.getElementById('ep-results').style.display = 'none';

        try {
            const res = await Auth.apiRequest('/api/connessione/xml/estrai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_id: this.xmlFileId, pods }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore elaborazione');
            }

            const data = await res.json();
            this.showEstraiResults(data);
            showToast(`${data.found.length} POD estratti su ${data.total_requested}`, 'success');

        } catch (err) {
            showToast(err.message, 'error');
            const resultsEl = document.getElementById('ep-results');
            resultsEl.style.display = 'block';
            resultsEl.innerHTML = `
                <div style="background:rgba(231,76,60,0.1);border:1px solid var(--accent-red);border-radius:8px;padding:16px;">
                    <div style="font-weight:600;color:var(--accent-red);margin-bottom:8px;">Errore</div>
                    <p style="color:var(--text-muted);margin:0;">${App.escapeHtml(err.message)}</p>
                </div>
            `;
        } finally {
            document.getElementById('ep-processing').style.display = 'none';
            btn.textContent = 'Estrai POD';
            btn.disabled = false;
        }
    },

    showEstraiResults(data) {
        const resultsEl = document.getElementById('ep-results');
        resultsEl.style.display = 'block';

        let notFoundHtml = '';
        if (data.not_found && data.not_found.length > 0) {
            notFoundHtml = `
                <div style="background:rgba(243,156,18,0.1);border:1px solid var(--accent-amber);border-radius:8px;padding:16px;margin-top:16px;">
                    <div style="font-weight:600;color:var(--accent-amber);margin-bottom:8px;">
                        POD non trovati (${data.not_found.length})
                    </div>
                    <ul style="margin:0;padding-left:20px;color:var(--text-muted);font-size:0.85rem;">
                        ${data.not_found.map(p => `<li>${App.escapeHtml(p)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        resultsEl.innerHTML = `
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px;">
                <div class="stat-card">
                    <div class="stat-label">Richiesti</div>
                    <div class="stat-value">${data.total_requested}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Trovati</div>
                    <div class="stat-value" style="color:var(--accent-green)">${data.found.length}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Non trovati</div>
                    <div class="stat-value" style="color:${data.not_found.length > 0 ? 'var(--accent-amber)' : 'var(--text-primary)'}">${data.not_found.length}</div>
                </div>
            </div>

            <div style="display:flex;gap:12px;flex-wrap:wrap;">
                <button class="btn btn-primary" id="ep-btn-download">Scarica ZIP</button>
                <button class="btn btn-cancel" id="ep-btn-new">Nuova Elaborazione</button>
            </div>

            ${notFoundHtml}
        `;

        document.getElementById('ep-btn-download').addEventListener('click', () => {
            this.downloadXmlResult(data.job_id);
        });
        document.getElementById('ep-btn-new').addEventListener('click', () => {
            this.renderEstraiPod(document.getElementById('conn-subtab-content'));
        });
    },

    async downloadXmlResult(jobId) {
        try {
            const res = await fetch(`/api/connessione/xml/download/${jobId}`, {
                headers: Auth.authHeaders(),
            });
            if (!res.ok) throw new Error('Download fallito');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `pod_extract_${jobId}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            showToast('Errore durante il download', 'error');
        }
    },
};
