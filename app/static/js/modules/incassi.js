/**
 * MUBI Tools — Modulo Incassi Mubi
 * UI stepper per upload e elaborazione file Excel
 */

const Incassi = {
    render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title">Elaborazione Incassi</div>

                <!-- Stepper -->
                <div class="stepper">
                    <div class="stepper-step active">1. Conversione</div>
                    <div class="stepper-step">2. Importo Aperto</div>
                    <div class="stepper-step">3. Piani Rientro</div>
                    <div class="stepper-step">4. Conferimento</div>
                    <div class="stepper-step">5. Identico</div>
                    <div class="stepper-step">6. Controllo</div>
                    <div class="stepper-step">7. Pivot</div>
                </div>

                <!-- Upload section -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
                    <div class="dropzone" id="drop-incassi">
                        <p>File Incassi/Insoluti (.txt)</p>
                        <p style="font-size:0.8rem;color:var(--text-muted)">Trascina o clicca per caricare</p>
                    </div>
                    <div class="dropzone" id="drop-massivo">
                        <p>Estrazione Massiva (.xlsx)</p>
                        <p style="font-size:0.8rem;color:var(--text-muted)">Trascina o clicca per caricare</p>
                    </div>
                    <div class="dropzone" id="drop-conferimento">
                        <p>File Conferimento (.xlsx)</p>
                        <p style="font-size:0.8rem;color:var(--text-muted)">Trascina o clicca per caricare</p>
                    </div>
                    <div class="dropzone" id="drop-piani">
                        <p>Piani di Rientro (.xlsx)</p>
                        <p style="font-size:0.8rem;color:var(--text-muted)">Trascina o clicca per caricare (opzionale)</p>
                    </div>
                </div>

                <!-- Actions -->
                <button class="btn btn-primary" id="btn-process" disabled>Avvia Elaborazione</button>

                <!-- Progress -->
                <div id="incassi-progress" style="margin-top:16px;display:none;">
                    <div class="progress-bar"><div class="progress-bar-fill" style="width:0%"></div></div>
                    <p style="margin-top:8px;color:var(--text-muted);font-size:0.85rem;" id="progress-text"></p>
                </div>

                <!-- Results -->
                <div id="incassi-results" style="margin-top:24px;display:none;"></div>
            </div>
        `;

        // TODO: Bind upload drag & drop e logica elaborazione (Step 6)
    }
};
