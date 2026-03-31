/**
 * MUBI Tools — Modulo Incassi Mubi
 * UI stepper per upload e elaborazione file Excel
 */

const Incassi = {
    files: {
        incassi: null,
        massivo: null,
        conferimento: null,
        piani: null,
    },

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
        '5. Identico',
        '6. Controllo',
        '7. Pivot',
    ],

    render(container) {
        this.files = { incassi: null, massivo: null, conferimento: null, piani: null };

        const stepperHtml = this.steps.map((s, i) =>
            `<div class="stepper-step${i === 0 ? ' active' : ''}" data-step="${i}">${s}</div>`
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
                <div class="stepper">${stepperHtml}</div>

                <div class="uploads-grid">${uploadsHtml}</div>

                <div style="margin-top:24px;display:flex;gap:12px;align-items:center;">
                    <button class="btn btn-primary" id="btn-process" disabled>Avvia Elaborazione</button>
                    <button class="btn btn-cancel" id="btn-clear" style="display:none;">Cancella file</button>
                </div>

                <div id="incassi-progress" style="margin-top:16px;display:none;">
                    <div class="progress-bar"><div class="progress-bar-fill" id="progress-fill" style="width:0%"></div></div>
                    <p style="margin-top:8px;color:var(--text-muted);font-size:0.85rem;" id="progress-text"></p>
                </div>

                <div id="incassi-results" style="margin-top:24px;display:none;"></div>
            </div>
        `;

        this.bindUploadEvents();
        document.getElementById('btn-process').addEventListener('click', () => this.startProcessing());
        document.getElementById('btn-clear').addEventListener('click', () => this.clearFiles());
    },

    bindUploadEvents() {
        this.fileConfigs.forEach(cfg => {
            const dropzone = document.getElementById(`drop-${cfg.key}`);
            const input = document.getElementById(`finput-${cfg.key}`);

            // Click to upload
            dropzone.addEventListener('click', () => input.click());

            // File input change
            input.addEventListener('change', () => {
                if (input.files.length > 0) {
                    this.setFile(cfg.key, input.files[0]);
                }
            });

            // Drag & drop
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
                if (e.dataTransfer.files.length > 0) {
                    this.setFile(cfg.key, e.dataTransfer.files[0]);
                }
            });
        });
    },

    setFile(key, file) {
        this.files[key] = file;
        const fnameEl = document.getElementById(`fname-${key}`);
        const dropzone = document.getElementById(`drop-${key}`);

        if (file) {
            const size = (file.size / 1024).toFixed(1);
            fnameEl.textContent = `${file.name} (${size} KB)`;
            fnameEl.style.color = 'var(--accent-green)';
            dropzone.style.borderColor = 'var(--accent-green)';
        } else {
            fnameEl.textContent = '';
            dropzone.style.borderColor = '';
        }

        this.updateProcessButton();
    },

    updateProcessButton() {
        const allRequired = this.fileConfigs
            .filter(c => c.required)
            .every(c => this.files[c.key] !== null);

        document.getElementById('btn-process').disabled = !allRequired;

        const anyFile = Object.values(this.files).some(f => f !== null);
        document.getElementById('btn-clear').style.display = anyFile ? 'inline-flex' : 'none';
    },

    clearFiles() {
        this.fileConfigs.forEach(cfg => {
            this.files[cfg.key] = null;
            document.getElementById(`fname-${cfg.key}`).textContent = '';
            document.getElementById(`drop-${cfg.key}`).style.borderColor = '';
            document.getElementById(`finput-${cfg.key}`).value = '';
        });
        this.updateProcessButton();
    },

    async startProcessing() {
        // TODO: Implementare chiamata API backend (Step 6)
        showToast('Elaborazione non ancora implementata (Step 6)', 'warning');
    }
};
