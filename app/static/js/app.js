/**
 * MUBI Tools — App principale
 * Router SPA, auth guard, navigazione
 */

const App = {
    currentView: null,

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
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorEl = document.getElementById('login-error');
            errorEl.style.display = 'none';

            try {
                await Auth.login(username, password);
                this.showApp();
            } catch (err) {
                errorEl.textContent = err.message;
                errorEl.style.display = 'block';
            }
        });
    },

    setupSidebar() {
        const user = Auth.getUser();
        if (!user) return;

        document.getElementById('user-display-name').textContent = user.fullName;
        document.getElementById('user-role').textContent = user.role === 'admin' ? 'Amministratore' : 'Utente';

        const nav = document.getElementById('sidebar-nav');
        nav.innerHTML = '';

        // Dashboard sempre visibile
        nav.innerHTML += '<div class="nav-item active" data-view="dashboard">Dashboard</div>';

        // Moduli abilitati
        if (user.allowedModules && user.allowedModules.includes('incassi_mubi')) {
            nav.innerHTML += '<div class="nav-item" data-view="incassi">Incassi Mubi</div>';
        }

        // Admin panel
        if (user.role === 'admin') {
            nav.innerHTML += '<div class="nav-item" data-view="admin">Admin Panel</div>';
        }

        // Bind click
        nav.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                nav.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                this.navigate(item.dataset.view);
            });
        });
    },

    setupLogout() {
        document.getElementById('btn-logout').addEventListener('click', () => {
            Auth.logout();
        });
    },

    async loadVersion() {
        try {
            const res = await fetch('/health');
            const data = await res.json();
            document.getElementById('app-version').textContent = `v${data.version}`;
            document.getElementById('version-badge').textContent = `v${data.version}`;
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
                content.innerHTML = '<div class="card"><div class="card-title">Benvenuto in MUBI Tools</div><p style="color:var(--text-muted)">Seleziona un modulo dalla barra laterale per iniziare.</p></div>';
                break;
            case 'incassi':
                breadcrumb.textContent = 'Incassi Mubi';
                Incassi.render(content);
                break;
            case 'admin':
                breadcrumb.textContent = 'Admin Panel';
                Admin.render(content);
                break;
            default:
                content.innerHTML = '<div class="card">Vista non trovata.</div>';
        }
    }
};

// Toast utility
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// Init
document.addEventListener('DOMContentLoaded', () => App.init());
