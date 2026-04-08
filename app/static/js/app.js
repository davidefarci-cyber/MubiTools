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
            this.showLogin();
        }
    },

    showLogin() {
        document.getElementById('login-page').style.display = 'flex';
        document.getElementById('app-layout').style.display = 'none';
        this.bindLoginForm();
    },

    showApp() {
        document.getElementById('login-page').style.display = 'none';
        document.getElementById('app-layout').style.display = 'flex';
        this.setupSidebar();
        this.setupLogout();
        this.loadVersion();
        this.navigate('dashboard');
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
function showToast(message, type = 'info') {
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
    }, 3500);
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
