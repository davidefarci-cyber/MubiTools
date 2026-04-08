/**
 * MUBI Tools — Modulo Connessione
 * UI con sottosezioni per gestione attivita' connessione gas
 */

const Connessione = {
    currentSubTab: 'crea-riga',
    fileId: null,
    fileName: null,
    fileHandle: null,       // FileSystemFileHandle per salvataggio in-place (Chrome/Edge)
    xmlFileId: null,
    xmlFileName: null,

    subTabs: [
        { key: 'crea-riga', label: 'Crea Riga FILE A' },
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
        this.fileHandle = null;
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
                        <p class="dropzone-hint" id="cr-save-hint" style="font-size:0.75rem;margin-top:2px;"></p>
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

        // Mostra hint salvataggio in-place se il browser lo supporta
        const hint = document.getElementById('cr-save-hint');
        if (hint) {
            hint.textContent = this._fsaSupported()
                ? 'Clic per aprire — il file verrà salvato automaticamente in-place'
                : 'Trascina o clicca — il risultato verrà scaricato come file';
        }

        this.bindCreaRigaEvents();
    },

    _fsaSupported() {
        return typeof window.showOpenFilePicker === 'function';
    },

    bindCreaRigaEvents() {
        const dropzone = document.getElementById('cr-dropzone');
        const input = document.getElementById('cr-fileinput');

        dropzone.addEventListener('click', () => {
            if (this._fsaSupported()) {
                this._openWithFilePicker();
            } else {
                input.click();
            }
        });

        // Fallback <input> — usato su Firefox e da drag & drop
        input.addEventListener('change', () => {
            if (input.files.length > 0) this.handleFile(input.files[0], null);
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
            // Drag & drop non fornisce un FileHandle → salvataggio classico
            if (e.dataTransfer.files.length > 0) this.handleFile(e.dataTransfer.files[0], null);
        });

        document.getElementById('cr-btn-process').addEventListener('click', () => this.processFile());
        document.getElementById('cr-btn-clear').addEventListener('click', () => this.clearFile());
    },

    async _openWithFilePicker() {
        try {
            const [handle] = await window.showOpenFilePicker({
                types: [{
                    description: 'File Excel',
                    accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx', '.xls'] },
                }],
                multiple: false,
            });
            const file = await handle.getFile();
            this.handleFile(file, handle);
        } catch (err) {
            // L'utente ha annullato il picker — nessuna azione
            if (err.name !== 'AbortError') {
                showToast('Errore apertura file: ' + err.message, 'error');
            }
        }
    },

    async handleFile(file, handle) {
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
            this.fileHandle = handle || null;

            const size = (data.size_bytes / 1024).toFixed(1);
            const inPlaceNote = this.fileHandle ? ' · salvataggio in-place attivo' : '';
            fnameEl.textContent = `${data.original_filename} (${size} KB)${inPlaceNote}`;
            fnameEl.style.color = 'var(--accent-green)';
            dropzone.style.borderColor = 'var(--accent-green)';

        } catch (err) {
            fnameEl.textContent = `Errore: ${err.message}`;
            fnameEl.style.color = 'var(--accent-red)';
            dropzone.style.borderColor = 'var(--accent-red)';
            this.fileId = null;
            this.fileName = null;
            this.fileHandle = null;
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
        this.fileHandle = null;
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
                ${this.fileHandle
                    ? `<button class="btn btn-primary" id="cr-btn-save">Salva in-place</button>`
                    : `<button class="btn btn-primary" id="cr-btn-download">Scarica Risultato</button>`
                }
                <button class="btn btn-cancel" id="cr-btn-new">Nuova Elaborazione</button>
            </div>

            ${warningsHtml}
        `;

        if (this.fileHandle) {
            document.getElementById('cr-btn-save').addEventListener('click', () => {
                this.saveInPlace(data.job_id);
            });
        } else {
            document.getElementById('cr-btn-download').addEventListener('click', () => {
                this.downloadResult(data.job_id);
            });
        }
        document.getElementById('cr-btn-new').addEventListener('click', () => {
            this.renderCreaRiga(document.getElementById('conn-subtab-content'));
        });
    },

    async _fetchResultBlob(jobId) {
        const res = await fetch(`/api/connessione/download/${jobId}`, {
            headers: Auth.authHeaders(),
        });
        if (!res.ok) throw new Error('Download fallito');
        return res.blob();
    },

    async saveInPlace(jobId) {
        const btn = document.getElementById('cr-btn-save');
        if (btn) { btn.disabled = true; btn.textContent = 'Salvataggio...'; }
        try {
            const blob = await this._fetchResultBlob(jobId);
            const writable = await this.fileHandle.createWritable();
            await writable.write(blob);
            await writable.close();
            showToast('File salvato in-place con successo', 'success');
        } catch (e) {
            showToast('Errore durante il salvataggio: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Salva in-place'; }
        }
    },

    async downloadResult(jobId) {
        try {
            const blob = await this._fetchResultBlob(jobId);
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
