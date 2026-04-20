/**
 * Grid — Modulo autenticazione
 * Gestione login, logout, token storage
 */

const Auth = {
    TOKEN_KEY: 'mubi_token',
    USER_KEY: 'mubi_user',

    getToken() {
        return localStorage.getItem(this.TOKEN_KEY);
    },

    getUser() {
        const data = localStorage.getItem(this.USER_KEY);
        return data ? JSON.parse(data) : null;
    },

    setSession(token, user) {
        localStorage.setItem(this.TOKEN_KEY, token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    },

    clearSession() {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.USER_KEY);
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    isAdmin() {
        const user = this.getUser();
        return user && user.role === 'admin';
    },

    authHeaders() {
        const token = this.getToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    },

    async apiRequest(url, options = {}) {
        const headers = { ...this.authHeaders(), ...options.headers };
        const res = await fetch(url, { ...options, headers });
        if (res.status === 401) {
            this.clearSession();
            window.location.reload();
            return null;
        }
        return res;
    },

    async login(username, password) {
        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Errore di login');
        }
        const data = await response.json();
        this.setSession(data.access_token, {
            username: data.username,
            fullName: data.full_name,
            role: data.role,
            allowedModules: data.allowed_modules
        });
        return data;
    },

    logout() {
        this.clearSession();
        window.location.reload();
    }
};
