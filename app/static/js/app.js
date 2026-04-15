/**
 * MUBI Tools — App principale
 * Router SPA, auth guard, navigazione
 */

const App = {
    currentView: null,
    healthData: null,

    async init() {
        if (Auth.isLoggedIn()) {
            this.showApp();
        } else {
            // Controlla primo avvio prima di mostrare il login
            await this.checkFirstBoot();
            this.showLogin();
        }
    },

    firstBootData: null,

    async checkFirstBoot() {
        try {
            const res = await fetch('/auth/first-boot');
            if (res.ok) {
                this.firstBootData = await res.json();
            }
        } catch {
            // Ignora errori, procedi normalmente
        }
    },

    showLogin() {
        document.getElementById('login-page').style.display = 'flex';
        document.getElementById('app-layout').style.display = 'none';
        this.bindLoginForm();
    },

    async showApp() {
        document.getElementById('login-page').style.display = 'none';
        document.getElementById('app-layout').style.display = 'flex';
        this.setupSidebar();
        this.setupLogout();
        this.loadVersion();

        // Controlla se e' il primo avvio (password admin di default)
        if (Auth.isAdmin()) {
            try {
                const res = await Auth.apiRequest('/auth/first-boot');
                if (res && res.ok) {
                    this.firstBootData = await res.json();
                }
            } catch { /* ignore */ }
        }

        if (this.firstBootData && this.firstBootData.is_first_boot && Auth.isAdmin()) {
            this.showFirstBootWizard();
        } else {
            this.navigate('dashboard');
        }
    },

    showFirstBootWizard() {
        const content = document.getElementById('main-content');
        const breadcrumb = document.getElementById('breadcrumb');
        breadcrumb.textContent = 'Primo Avvio';

        let restoreSection = '';
        if (this.firstBootData && this.firstBootData.has_backups) {
            restoreSection = `
                <div class="card" style="margin-top:20px;border:1px solid var(--accent-amber);">
                    <div class="card-title" style="color:var(--accent-amber);">Ripristina da backup precedente</div>
                    <p style="color:var(--text-muted);margin-bottom:16px;">
                        Sono stati trovati backup precedenti nella cartella di sistema.
                        Puoi ripristinare un backup per recuperare dati da un'installazione precedente.
                    </p>
                    <button class="btn btn-sm btn-warn" id="btn-wizard-restore">Vai a Ripristina Backup</button>
                </div>`;
        }

        content.innerHTML = `
            <div class="card" style="max-width:700px;margin:40px auto;">
                <div style="text-align:center;margin-bottom:24px;">
                    <h2 style="color:var(--text-primary);margin-bottom:8px;">Installazione completata</h2>
                    <p style="color:var(--accent-amber);font-weight:600;font-size:1.05rem;">
                        Stai usando le credenziali di default: cambia la password admin prima di procedere.
                    </p>
                </div>
                <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:20px;margin-bottom:20px;">
                    <p style="color:var(--text-muted);margin-bottom:12px;">Per la sicurezza del sistema, cambia subito la password dell'account amministratore.</p>
                    <button class="btn btn-primary" id="btn-wizard-change-pw">Cambia Password Admin</button>
                </div>
                <div style="text-align:center;">
                    <button class="btn btn-sm" id="btn-wizard-skip" style="background:var(--bg-tertiary);color:var(--text-muted);">Continua senza cambiare (sconsigliato)</button>
                </div>
                ${restoreSection}
            </div>`;

        document.getElementById('btn-wizard-change-pw').addEventListener('click', () => {
            this.showChangePasswordModal();
        });
        document.getElementById('btn-wizard-skip').addEventListener('click', () => {
            this.firstBootData = null;
            this.navigate('dashboard');
        });
        const restoreBtn = document.getElementById('btn-wizard-restore');
        if (restoreBtn) {
            restoreBtn.addEventListener('click', () => {
                this.firstBootData = null;
                this.navigate('admin');
                // Apri la modale di restore dopo un breve delay per dare tempo al render
                setTimeout(() => Admin.showRestoreModal(), 500);
            });
        }
    },

    showChangePasswordModal() {
        const user = Auth.getUser();
        const body = `
            <form id="wizard-pw-form">
                <div class="form-group">
                    <label>Nuova Password (min. 8 caratteri)</label>
                    <input type="password" id="wizard-new-pw" required minlength="8" autocomplete="new-password" placeholder="Inserisci la nuova password">
                </div>
                <div class="form-group">
                    <label>Conferma Password</label>
                    <input type="password" id="wizard-confirm-pw" required minlength="8" autocomplete="new-password" placeholder="Ripeti la nuova password">
                </div>
            </form>`;

        showModal('Cambia Password Admin', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Salva Password', class: 'btn-primary', onClick: () => this.executePasswordChange() },
        ]);
    },

    async executePasswordChange() {
        const newPw = document.getElementById('wizard-new-pw').value;
        const confirmPw = document.getElementById('wizard-confirm-pw').value;

        if (newPw.length < 8) {
            showToast('La password deve avere almeno 8 caratteri', 'error');
            return;
        }
        if (newPw !== confirmPw) {
            showToast('Le password non coincidono', 'error');
            return;
        }

        try {
            // Trova l'ID dell'admin corrente
            const usersRes = await Auth.apiRequest('/admin/users');
            if (!usersRes.ok) throw new Error('Errore caricamento utenti');
            const users = await usersRes.json();
            const currentUser = Auth.getUser();
            const admin = users.find(u => u.username === currentUser.username);
            if (!admin) throw new Error('Utente admin non trovato');

            const res = await Auth.apiRequest(`/admin/users/${admin.id}/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPw }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore cambio password');
            }

            closeModal();
            showToast('Password cambiata con successo! Effettua nuovamente il login.', 'success');
            this.firstBootData = null;
            // Forza re-login con la nuova password
            setTimeout(() => Auth.logout(), 2000);
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    bindLoginForm() {
        const form = document.getElementById('login-form');
        const handler = async (e) => {
            e.preventDefault();
            const btn = form.querySelector('button[type="submit"]');
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;
            const errorEl = document.getElementById('login-error');
            errorEl.style.display = 'none';
            btn.disabled = true;
            btn.textContent = 'Accesso in corso...';

            try {
                await Auth.login(username, password);
                this.showApp();
            } catch (err) {
                errorEl.textContent = err.message;
                errorEl.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Accedi';
            }
        };
        form.removeEventListener('submit', form._handler);
        form._handler = handler;
        form.addEventListener('submit', handler);
    },

    setupSidebar() {
        const user = Auth.getUser();
        if (!user) return;

        document.getElementById('user-display-name').textContent = user.fullName;
        document.getElementById('user-role').textContent =
            user.role === 'admin' ? 'Amministratore' : 'Utente';

        const nav = document.getElementById('sidebar-nav');
        nav.innerHTML = '';

        const items = [
            { view: 'dashboard', label: 'Dashboard', icon: 'home', always: true },
            { view: 'incassi', label: 'Incassi Mubi', icon: 'file', module: 'incassi_mubi' },
            { view: 'connessione', label: 'Connessione', icon: 'link', module: 'connessione' },
            { view: 'caricamento_remi', label: 'Caricamento REMI', icon: 'upload', module: 'caricamento_remi' },
            { view: 'admin', label: 'Admin Panel', icon: 'settings', adminOnly: true },
        ];

        items.forEach(item => {
            if (item.adminOnly && user.role !== 'admin') return;
            if (item.module && (!user.allowedModules || !user.allowedModules.includes(item.module))) return;

            const el = document.createElement('div');
            el.className = 'nav-item';
            el.dataset.view = item.view;
            el.innerHTML = `<span class="nav-icon">${this.getIcon(item.icon)}</span><span>${item.label}</span>`;
            el.addEventListener('click', () => {
                nav.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                el.classList.add('active');
                this.navigate(item.view);
            });
            nav.appendChild(el);
        });

        // Attiva primo elemento
        const first = nav.querySelector('.nav-item');
        if (first) first.classList.add('active');
    },

    getIcon(name) {
        const icons = {
            home: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
            file: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
            link: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
            upload: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
            settings: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        };
        return icons[name] || '';
    },

    setupLogout() {
        const btn = document.getElementById('btn-logout');
        const handler = () => Auth.logout();
        btn.removeEventListener('click', btn._handler);
        btn._handler = handler;
        btn.addEventListener('click', handler);
    },

    async loadVersion() {
        try {
            const res = await fetch('/health');
            this.healthData = await res.json();
            document.getElementById('app-version').textContent = `v${this.healthData.version}`;
            document.getElementById('version-badge').textContent = `v${this.healthData.version}`;
        } catch {
            // Ignore
        }
    },

    navigate(view) {
        this.currentView = view;
        const content = document.getElementById('main-content');
        const breadcrumb = document.getElementById('breadcrumb');

        switch (view) {
            case 'dashboard':
                breadcrumb.textContent = 'Dashboard';
                this.renderDashboard(content);
                break;
            case 'incassi':
                breadcrumb.textContent = 'Incassi Mubi';
                Incassi.render(content);
                break;
            case 'connessione':
                breadcrumb.textContent = 'Connessione';
                Connessione.render(content);
                break;
            case 'caricamento_remi':
                breadcrumb.textContent = 'Caricamento REMI';
                CaricamentoRemi.render(content);
                break;
            case 'admin':
                breadcrumb.textContent = 'Admin Panel';
                Admin.render(content);
                break;
            default:
                content.innerHTML = '<div class="card">Vista non trovata.</div>';
        }
    },

    renderDashboard(container) {
        const user = Auth.getUser();
        const version = this.healthData ? this.healthData.version : '...';
        const uptime = this.healthData ? this.formatUptime(this.healthData.uptime_seconds) : '...';

        container.innerHTML = `
            <div class="card">
                <div class="card-title">Benvenuto, ${this.escapeHtml(user.fullName)}</div>
                <p style="color:var(--text-muted);margin-bottom:20px;">
                    Seleziona un modulo dalla barra laterale per iniziare.
                </p>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
                    <div class="stat-card">
                        <div class="stat-label">Versione</div>
                        <div class="stat-value">${version}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Uptime</div>
                        <div class="stat-value">${uptime}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Ruolo</div>
                        <div class="stat-value">${user.role === 'admin' ? 'Amministratore' : 'Utente'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Moduli attivi</div>
                        <div class="stat-value">${user.allowedModules ? user.allowedModules.length : 0}</div>
                    </div>
                </div>
            </div>
        `;
    },

    formatUptime(seconds) {
        if (!seconds) return '0s';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}h ${m}m`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    },

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};

// Toast utility
function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Modal utility
function showModal(title, bodyHtml, actions = []) {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <div class="modal-title">${title}</div>
            <div class="modal-body">${bodyHtml}</div>
            <div class="modal-actions" id="modal-actions"></div>
        </div>
    `;

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    const actionsContainer = overlay.querySelector('#modal-actions');
    actions.forEach(action => {
        const btn = document.createElement('button');
        btn.className = `btn ${action.class || ''}`;
        btn.textContent = action.label;
        btn.addEventListener('click', () => {
            if (action.onClick) action.onClick(overlay);
        });
        actionsContainer.appendChild(btn);
    });

    document.body.appendChild(overlay);
    return overlay;
}

function closeModal() {
    const overlay = document.querySelector('.modal-overlay');
    if (overlay) overlay.remove();
}

// Init
document.addEventListener('DOMContentLoaded', () => App.init());
