/**
 * MUBI Tools — Pannello Admin
 * Gestione utenti, aggiornamenti, audit log
 */

const Admin = {
    render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title">Gestione Utenti</div>
                <div id="admin-users-list">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
            <div class="card">
                <div class="card-title">Audit Log</div>
                <div id="admin-audit-log">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
        `;
        this.loadUsers();
        this.loadAuditLog();
    },

    async loadUsers() {
        const container = document.getElementById('admin-users-list');
        try {
            const res = await fetch('/admin/users', { headers: Auth.authHeaders() });
            if (!res.ok) throw new Error('Errore caricamento utenti');
            const users = await res.json();
            container.innerHTML = this.renderUsersTable(users);
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${err.message}</p>`;
        }
    },

    renderUsersTable(users) {
        if (!users.length) return '<p style="color:var(--text-muted)">Nessun utente trovato.</p>';
        return `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Nome</th>
                            <th>Ruolo</th>
                            <th>Stato</th>
                            <th>Ultimo accesso</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${users.map(u => `
                            <tr>
                                <td>${u.username}</td>
                                <td>${u.full_name}</td>
                                <td><span class="badge badge-admin">${u.role}</span></td>
                                <td><span class="badge ${u.is_active ? 'badge-active' : 'badge-disabled'}">${u.is_active ? 'Attivo' : 'Disabilitato'}</span></td>
                                <td style="color:var(--text-muted)">${u.last_login || 'Mai'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },

    async loadAuditLog() {
        const container = document.getElementById('admin-audit-log');
        try {
            const res = await fetch('/admin/audit-log?per_page=20', { headers: Auth.authHeaders() });
            if (!res.ok) throw new Error('Errore caricamento audit log');
            const data = await res.json();
            if (!data.items.length) {
                container.innerHTML = '<p style="color:var(--text-muted)">Nessuna voce nel log.</p>';
                return;
            }
            container.innerHTML = `
                <div class="table-container">
                    <table>
                        <thead><tr><th>Azione</th><th>Dettaglio</th><th>Data</th></tr></thead>
                        <tbody>
                            ${data.items.map(log => `
                                <tr>
                                    <td>${log.action}</td>
                                    <td style="color:var(--text-muted);max-width:300px;overflow:hidden;text-overflow:ellipsis;">${log.detail || '-'}</td>
                                    <td style="color:var(--text-muted)">${log.timestamp || '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${err.message}</p>`;
        }
    }
};
