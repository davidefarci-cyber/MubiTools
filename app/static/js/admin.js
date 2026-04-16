/**
 * MUBI Tools — Pannello Admin
 * Gestione utenti, aggiornamenti, audit log
 */

const Admin = {
    users: [],
    pecAccounts: [],
    auditPage: 1,

    render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
                    <span>Gestione Utenti</span>
                    <button class="btn btn-primary btn-sm" id="btn-add-user">+ Nuovo Utente</button>
                </div>
                <div id="admin-users-list">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
                    <span>Connessioni PEC</span>
                    <button class="btn btn-primary btn-sm" id="btn-add-pec">+ Nuova PEC</button>
                </div>
                <div id="admin-pec-list">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
            <div class="card">
                <div class="card-title">Gestione Database</div>
                <div id="admin-db-management">
                    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
                        <button class="btn btn-primary btn-sm" id="btn-db-backup">Scarica Backup</button>
                        <button class="btn btn-sm btn-warn" id="btn-db-restore">Ripristina Backup</button>
                        <button class="btn btn-sm btn-danger" id="btn-db-reinit">Reinizializza DB</button>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-title">Aggiornamenti Software</div>
                <div id="admin-updates">
                    <div class="spinner" style="margin:20px auto;"></div>
                </div>
            </div>
            <div class="card">
                <div class="card-title">Informazioni Sistema</div>
                <div id="admin-system-info">
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
        document.getElementById('btn-add-user').addEventListener('click', () => this.showCreateUserModal());
        document.getElementById('btn-add-pec').addEventListener('click', () => this.showCreatePecModal());
        document.getElementById('btn-db-backup').addEventListener('click', () => this.downloadBackup());
        document.getElementById('btn-db-restore').addEventListener('click', () => this.showRestoreModal());
        document.getElementById('btn-db-reinit').addEventListener('click', () => this.confirmReinitDb());
        this.loadUsers();
        this.loadPecAccounts();
        this.loadSystemInfo();
        this.loadUpdates();
        this.loadAuditLog();
    },

    // --- Users ---

    async loadUsers() {
        const container = document.getElementById('admin-users-list');
        try {
            const res = await Auth.apiRequest('/admin/users');
            if (!res.ok) throw new Error('Errore caricamento utenti');
            this.users = await res.json();
            container.innerHTML = this.renderUsersTable(this.users);
            this.bindUserActions();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    renderUsersTable(users) {
        if (!users.length) return '<p style="color:var(--text-muted)">Nessun utente trovato.</p>';

        const rows = users.map(u => {
            const modules = Array.isArray(u.allowed_modules) ? u.allowed_modules.join(', ') : u.allowed_modules;
            const lastLogin = u.last_login ? new Date(u.last_login).toLocaleString('it-IT') : 'Mai';
            const roleBadge = u.role === 'admin'
                ? '<span class="badge badge-admin">admin</span>'
                : '<span class="badge" style="background:var(--bg-tertiary);color:var(--text-muted)">user</span>';
            const statusBadge = u.is_active
                ? '<span class="badge badge-active">Attivo</span>'
                : '<span class="badge badge-disabled">Disabilitato</span>';

            return `
                <tr>
                    <td><strong>${App.escapeHtml(u.username)}</strong></td>
                    <td>${App.escapeHtml(u.full_name)}</td>
                    <td>${roleBadge}</td>
                    <td>${App.escapeHtml(modules)}</td>
                    <td>${statusBadge}</td>
                    <td style="color:var(--text-muted);font-size:0.85rem">${lastLogin}</td>
                    <td>
                        <div style="display:flex;gap:6px;">
                            <button class="btn btn-sm btn-edit" data-id="${u.id}" title="Modifica">Modifica</button>
                            <button class="btn btn-sm btn-toggle ${u.is_active ? 'btn-warn' : 'btn-success'}" data-id="${u.id}" title="${u.is_active ? 'Disabilita' : 'Abilita'}">
                                ${u.is_active ? 'Disabilita' : 'Abilita'}
                            </button>
                        </div>
                    </td>
                </tr>`;
        }).join('');

        return `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Nome</th>
                            <th>Ruolo</th>
                            <th>Moduli</th>
                            <th>Stato</th>
                            <th>Ultimo accesso</th>
                            <th>Azioni</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
    },

    bindUserActions() {
        const usersContainer = document.getElementById('admin-users-list');
        if (!usersContainer) return;
        usersContainer.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const user = this.users.find(u => u.id === parseInt(btn.dataset.id));
                if (user) this.showEditUserModal(user);
            });
        });
        usersContainer.querySelectorAll('.btn-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const user = this.users.find(u => u.id === parseInt(btn.dataset.id));
                if (user) this.confirmToggleUser(user);
            });
        });
    },

    showCreateUserModal() {
        const body = `
            <form id="create-user-form">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" id="new-username" required minlength="3" maxlength="50">
                </div>
                <div class="form-group">
                    <label>Nome completo</label>
                    <input type="text" id="new-fullname" required>
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" id="new-password" required minlength="8" autocomplete="new-password">
                </div>
                <div class="form-group">
                    <label>Ruolo</label>
                    <select id="new-role">
                        <option value="user">Utente</option>
                        <option value="admin">Amministratore</option>
                    </select>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="new-mod-incassi" checked style="width:auto;margin-right:8px;">Incassi Mubi</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="new-mod-connessione" checked style="width:auto;margin-right:8px;">Connessione</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="new-mod-caricamento-remi" style="width:auto;margin-right:8px;">Caricamento REMI</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="new-mod-invio-remi" style="width:auto;margin-right:8px;">Invio REMI</label>
                </div>
            </form>`;

        showModal('Nuovo Utente', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Crea Utente', class: 'btn-primary', onClick: () => this.createUser() },
        ]);
    },

    async createUser() {
        const username = document.getElementById('new-username').value.trim();
        const fullName = document.getElementById('new-fullname').value.trim();
        const password = document.getElementById('new-password').value;
        const role = document.getElementById('new-role').value;
        const modules = [];
        if (document.getElementById('new-mod-incassi').checked) modules.push('incassi_mubi');
        if (document.getElementById('new-mod-connessione').checked) modules.push('connessione');
        if (document.getElementById('new-mod-caricamento-remi').checked) modules.push('caricamento_remi');
        if (document.getElementById('new-mod-invio-remi').checked) modules.push('invio_remi');

        if (!username || !fullName || password.length < 8) {
            showToast('Compilare tutti i campi (password min. 8 caratteri)', 'error');
            return;
        }

        try {
            const res = await Auth.apiRequest('/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username, full_name: fullName, password, role, allowed_modules: modules
                })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore creazione utente');
            }
            closeModal();
            showToast(`Utente "${username}" creato con successo`, 'success');
            this.loadUsers();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    showEditUserModal(user) {
        const modules = Array.isArray(user.allowed_modules) ? user.allowed_modules : [];
        const body = `
            <form id="edit-user-form">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" value="${App.escapeHtml(user.username)}" disabled style="opacity:0.6;">
                </div>
                <div class="form-group">
                    <label>Nome completo</label>
                    <input type="text" id="edit-fullname" value="${App.escapeHtml(user.full_name)}">
                </div>
                <div class="form-group">
                    <label>Ruolo</label>
                    <select id="edit-role">
                        <option value="user" ${user.role === 'user' ? 'selected' : ''}>Utente</option>
                        <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Amministratore</option>
                    </select>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="edit-mod-incassi" ${modules.includes('incassi_mubi') ? 'checked' : ''} style="width:auto;margin-right:8px;">Incassi Mubi</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="edit-mod-connessione" ${modules.includes('connessione') ? 'checked' : ''} style="width:auto;margin-right:8px;">Connessione</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="edit-mod-caricamento-remi" ${modules.includes('caricamento_remi') ? 'checked' : ''} style="width:auto;margin-right:8px;">Caricamento REMI</label>
                </div>
                <div class="form-group">
                    <label><input type="checkbox" id="edit-mod-invio-remi" ${modules.includes('invio_remi') ? 'checked' : ''} style="width:auto;margin-right:8px;">Invio REMI</label>
                </div>
                <hr style="border-color:var(--border);margin:16px 0;">
                <div class="form-group">
                    <label>Nuova Password (lasciare vuoto per non cambiare)</label>
                    <input type="password" id="edit-password" minlength="8" autocomplete="new-password" placeholder="Min. 8 caratteri">
                </div>
            </form>`;

        showModal(`Modifica: ${user.username}`, body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Salva', class: 'btn-primary', onClick: () => this.saveUser(user.id) },
        ]);
    },

    async saveUser(userId) {
        const fullName = document.getElementById('edit-fullname').value.trim();
        const role = document.getElementById('edit-role').value;
        const password = document.getElementById('edit-password').value;
        const modules = [];
        if (document.getElementById('edit-mod-incassi').checked) modules.push('incassi_mubi');
        if (document.getElementById('edit-mod-connessione').checked) modules.push('connessione');
        if (document.getElementById('edit-mod-caricamento-remi').checked) modules.push('caricamento_remi');
        if (document.getElementById('edit-mod-invio-remi').checked) modules.push('invio_remi');

        try {
            const res = await Auth.apiRequest(`/admin/users/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    full_name: fullName, role, allowed_modules: modules
                })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore aggiornamento');
            }

            if (password && password.length >= 8) {
                const pwRes = await Auth.apiRequest(`/admin/users/${userId}/reset-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_password: password })
                });
                if (!pwRes.ok) {
                    showToast('Utente aggiornato ma errore nel reset password', 'warning');
                }
            }

            closeModal();
            showToast('Utente aggiornato con successo', 'success');
            this.loadUsers();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    confirmToggleUser(user) {
        const action = user.is_active ? 'disabilitare' : 'abilitare';
        showModal(
            'Conferma',
            `<p>Vuoi ${action} l'utente <strong>${App.escapeHtml(user.username)}</strong>?</p>`,
            [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                {
                    label: user.is_active ? 'Disabilita' : 'Abilita',
                    class: user.is_active ? 'btn-danger' : 'btn-success',
                    onClick: () => this.toggleUser(user)
                },
            ]
        );
    },

    async toggleUser(user) {
        try {
            const res = await Auth.apiRequest(`/admin/users/${user.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: !user.is_active })
            });
            if (!res.ok) throw new Error('Errore aggiornamento stato');
            closeModal();
            const state = user.is_active ? 'disabilitato' : 'abilitato';
            showToast(`Utente "${user.username}" ${state}`, 'success');
            this.loadUsers();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    // --- PEC Accounts ---

    async loadPecAccounts() {
        const container = document.getElementById('admin-pec-list');
        try {
            const res = await Auth.apiRequest('/admin/pec');
            if (!res.ok) throw new Error('Errore caricamento PEC');
            this.pecAccounts = await res.json();
            container.innerHTML = this.renderPecTable(this.pecAccounts);
            this.bindPecActions();
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    renderPecTable(accounts) {
        if (!accounts.length) return '<p style="color:var(--text-muted)">Nessuna connessione PEC configurata.</p>';

        const rows = accounts.map(p => {
            const statusBadge = p.is_active
                ? '<span class="badge badge-active">Attiva</span>'
                : '<span class="badge badge-disabled">Disattiva</span>';

            return `
                <tr>
                    <td><strong>${App.escapeHtml(p.label)}</strong></td>
                    <td>${App.escapeHtml(p.email)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <span id="pec-test-result-${p.id}" style="font-size:0.85rem;"></span>
                    </td>
                    <td>
                        <div style="display:flex;gap:6px;">
                            <button class="btn btn-sm btn-pec-test" data-id="${p.id}" title="Testa Connessione">Testa</button>
                            <button class="btn btn-sm btn-pec-edit" data-id="${p.id}" title="Modifica">Modifica</button>
                            <button class="btn btn-sm btn-warn btn-pec-delete" data-id="${p.id}" title="Elimina">Elimina</button>
                        </div>
                    </td>
                </tr>`;
        }).join('');

        return `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Etichetta</th>
                            <th>Email</th>
                            <th>Stato</th>
                            <th>Test</th>
                            <th>Azioni</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
    },

    bindPecActions() {
        document.querySelectorAll('.btn-pec-test').forEach(btn => {
            btn.addEventListener('click', () => this.testPec(parseInt(btn.dataset.id)));
        });
        document.querySelectorAll('.btn-pec-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const pec = this.pecAccounts.find(p => p.id === parseInt(btn.dataset.id));
                if (pec) this.showEditPecModal(pec);
            });
        });
        document.querySelectorAll('.btn-pec-delete').forEach(btn => {
            btn.addEventListener('click', () => {
                const pec = this.pecAccounts.find(p => p.id === parseInt(btn.dataset.id));
                if (pec) this.confirmDeletePec(pec);
            });
        });
    },

    showCreatePecModal() {
        const body = `
            <form id="create-pec-form">
                <div class="form-group">
                    <label>Etichetta</label>
                    <input type="text" id="pec-label" required placeholder="Es: PEC Principale">
                </div>
                <div class="form-group">
                    <label>Email PEC</label>
                    <input type="email" id="pec-email" required placeholder="esempio@pec.it">
                </div>
                <div class="form-group">
                    <label>Username SMTP</label>
                    <input type="text" id="pec-username" required placeholder="username@pec.it">
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" id="pec-password" required autocomplete="new-password">
                </div>
                <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:12px;margin-top:12px;">
                    <p style="color:var(--text-muted);font-size:0.85rem;margin:0;">
                        <strong>Parametri SMTP (fissi):</strong> smtps.pec.aruba.it : 465 (SSL)
                    </p>
                </div>
            </form>`;

        showModal('Nuova Connessione PEC', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Crea PEC', class: 'btn-primary', onClick: () => this.createPec() },
        ]);
    },

    async createPec() {
        const label = document.getElementById('pec-label').value.trim();
        const email = document.getElementById('pec-email').value.trim();
        const username = document.getElementById('pec-username').value.trim();
        const password = document.getElementById('pec-password').value;

        if (!label || !email || !username || !password) {
            showToast('Compilare tutti i campi', 'error');
            return;
        }

        try {
            const res = await Auth.apiRequest('/admin/pec', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, email, username, password })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore creazione PEC');
            }
            closeModal();
            showToast('Connessione PEC creata con successo', 'success');
            this.loadPecAccounts();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    showEditPecModal(pec) {
        const body = `
            <form id="edit-pec-form">
                <div class="form-group">
                    <label>Etichetta</label>
                    <input type="text" id="edit-pec-label" value="${App.escapeHtml(pec.label)}" required>
                </div>
                <div class="form-group">
                    <label>Email PEC</label>
                    <input type="email" id="edit-pec-email" value="${App.escapeHtml(pec.email)}" required>
                </div>
                <div class="form-group">
                    <label>Username SMTP</label>
                    <input type="text" id="edit-pec-username" value="${App.escapeHtml(pec.username)}" required>
                </div>
                <div class="form-group">
                    <label>Password (lasciare vuoto per non cambiare)</label>
                    <input type="password" id="edit-pec-password" autocomplete="new-password" placeholder="Lasciare vuoto = non cambiare">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="edit-pec-active" ${pec.is_active ? 'checked' : ''} style="width:auto;margin-right:8px;">
                        Attiva
                    </label>
                </div>
                <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:12px;margin-top:12px;">
                    <p style="color:var(--text-muted);font-size:0.85rem;margin:0;">
                        <strong>Parametri SMTP (fissi):</strong> smtps.pec.aruba.it : 465 (SSL)
                    </p>
                </div>
            </form>`;

        showModal(`Modifica PEC: ${pec.label}`, body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Salva', class: 'btn-primary', onClick: () => this.savePec(pec.id) },
        ]);
    },

    async savePec(pecId) {
        const label = document.getElementById('edit-pec-label').value.trim();
        const email = document.getElementById('edit-pec-email').value.trim();
        const username = document.getElementById('edit-pec-username').value.trim();
        const password = document.getElementById('edit-pec-password').value;
        const isActive = document.getElementById('edit-pec-active').checked;

        if (!label || !email || !username) {
            showToast('Compilare etichetta, email e username', 'error');
            return;
        }

        const payload = { label, email, username, is_active: isActive };
        if (password) payload.password = password;

        try {
            const res = await Auth.apiRequest(`/admin/pec/${pecId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore aggiornamento PEC');
            }
            closeModal();
            showToast('Connessione PEC aggiornata', 'success');
            this.loadPecAccounts();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    confirmDeletePec(pec) {
        showModal(
            'Conferma eliminazione',
            `<p>Vuoi eliminare la connessione PEC <strong>${App.escapeHtml(pec.label)}</strong> (${App.escapeHtml(pec.email)})?</p>`,
            [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                { label: 'Elimina', class: 'btn-danger', onClick: () => this.deletePec(pec.id) },
            ]
        );
    },

    async deletePec(pecId) {
        try {
            const res = await Auth.apiRequest(`/admin/pec/${pecId}`, { method: 'DELETE' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore eliminazione PEC');
            }
            closeModal();
            showToast('Connessione PEC eliminata', 'success');
            this.loadPecAccounts();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async testPec(pecId) {
        const resultSpan = document.getElementById(`pec-test-result-${pecId}`);
        if (resultSpan) {
            resultSpan.innerHTML = '<span style="color:var(--text-muted)">Test in corso...</span>';
        }

        try {
            const res = await Auth.apiRequest(`/admin/pec/${pecId}/test`, { method: 'POST' });
            if (!res.ok) throw new Error('Errore durante il test');
            const data = await res.json();

            if (resultSpan) {
                if (data.success) {
                    resultSpan.innerHTML = '<span style="color:var(--accent-green);font-weight:600;">&#10003; Connesso</span>';
                } else {
                    resultSpan.innerHTML = `<span style="color:var(--accent-red);font-weight:600;">&#10007; ${App.escapeHtml(data.error || 'Errore')}</span>`;
                }
            }
        } catch (err) {
            if (resultSpan) {
                resultSpan.innerHTML = `<span style="color:var(--accent-red);">&#10007; ${App.escapeHtml(err.message)}</span>`;
            }
        }
    },

    // --- System info ---

    async loadSystemInfo() {
        const container = document.getElementById('admin-system-info');
        try {
            const res = await fetch('/health');
            const data = await res.json();
            container.innerHTML = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
                    <div class="stat-card">
                        <div class="stat-label">Versione</div>
                        <div class="stat-value">${data.version}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Stato</div>
                        <div class="stat-value" style="color:var(--accent-green)">${data.status.toUpperCase()}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Uptime</div>
                        <div class="stat-value">${App.formatUptime(data.uptime_seconds)}</div>
                    </div>
                </div>`;
        } catch {
            container.innerHTML = '<p style="color:var(--accent-red)">Impossibile contattare il servizio</p>';
        }
    },

    // --- Aggiornamenti ---

    async loadUpdates() {
        const container = document.getElementById('admin-updates');
        try {
            const res = await Auth.apiRequest('/admin/updates/branches');
            if (!res.ok) throw new Error('Errore caricamento branch');
            const data = await res.json();

            const options = data.branches.map(b => {
                const selected = b.name === data.current_branch ? 'selected' : '';
                return `<option value="${App.escapeHtml(b.name)}" ${selected}>${App.escapeHtml(b.name)} (${App.escapeHtml(b.sha)})</option>`;
            }).join('');

            container.innerHTML = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:16px;">
                    <div class="stat-card">
                        <div class="stat-label">Branch corrente</div>
                        <div class="stat-value">${App.escapeHtml(data.current_branch)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Branch disponibili</div>
                        <div class="stat-value">${data.branches.length}</div>
                    </div>
                </div>
                <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:16px;">
                    <select id="branch-select" style="padding:8px 12px;border-radius:6px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-primary);font-size:0.9rem;">
                        ${options}
                    </select>
                    <button class="btn btn-primary btn-sm" id="btn-check-updates">Controlla aggiornamenti</button>
                </div>
                <div id="update-check-result"></div>`;

            document.getElementById('btn-check-updates').addEventListener('click', () => {
                const branch = document.getElementById('branch-select').value;
                this.checkForUpdates(branch);
            });
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    async checkForUpdates(branch) {
        const result = document.getElementById('update-check-result');
        result.innerHTML = '<div class="spinner" style="margin:12px auto;"></div>';
        try {
            const res = await Auth.apiRequest(`/admin/updates/check?branch=${encodeURIComponent(branch)}`);
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore controllo aggiornamenti');
            }
            const data = await res.json();

            const statusColor = data.update_available ? 'var(--accent-yellow, #f0ad4e)' : 'var(--accent-green)';
            const statusText = data.update_available
                ? `${data.commits_behind} commit da scaricare`
                : 'Nessun aggiornamento disponibile';

            let applyBtn = '';
            if (data.update_available) {
                applyBtn = `<button class="btn btn-primary btn-sm" id="btn-apply-update" style="margin-top:12px;">Applica aggiornamento</button>`;
            }

            result.innerHTML = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:8px;">
                    <div class="stat-card">
                        <div class="stat-label">Stato</div>
                        <div class="stat-value" style="color:${statusColor};font-size:0.95rem;">${statusText}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">SHA locale</div>
                        <div class="stat-value" style="font-family:monospace;font-size:0.95rem;">${App.escapeHtml(data.local_sha)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">SHA remoto</div>
                        <div class="stat-value" style="font-family:monospace;font-size:0.95rem;">${App.escapeHtml(data.remote_sha)}</div>
                    </div>
                </div>
                ${data.commits_ahead > 0 ? `<p style="color:var(--text-muted);font-size:0.85rem;margin:4px 0;">${data.commits_ahead} commit locali in avanti rispetto al remoto</p>` : ''}
                ${applyBtn}`;

            const applyBtnEl = document.getElementById('btn-apply-update');
            if (applyBtnEl) {
                applyBtnEl.addEventListener('click', () => this.applyUpdate(branch));
            }
        } catch (err) {
            result.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    applyUpdate(branch) {
        showModal(
            'Conferma aggiornamento',
            `<p>Vuoi aggiornare al branch <strong>${App.escapeHtml(branch)}</strong>?</p>
             <p style="color:var(--text-muted);font-size:0.85rem;">Verranno eseguiti: <strong>git pull</strong>, <strong>pip install</strong> e <strong>riavvio del servizio</strong>.<br>La pagina si ricaricherà automaticamente al termine.</p>`,
            [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                {
                    label: 'Aggiorna',
                    class: 'btn-primary',
                    onClick: async () => {
                        closeModal();
                        const result = document.getElementById('update-check-result');
                        result.innerHTML = '<div class="spinner" style="margin:12px auto;"></div><p style="text-align:center;color:var(--text-muted);">Aggiornamento in corso...</p>';
                        try {
                            const res = await Auth.apiRequest('/admin/updates/apply', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ branch })
                            });
                            if (!res.ok) {
                                const err = await res.json();
                                throw new Error(err.detail || 'Errore aggiornamento');
                            }
                            const data = await res.json();

                            const logHtml = (data.log || []).map(entry => {
                                const color = entry.success ? 'var(--accent-green)' : 'var(--accent-red)';
                                return `<div style="padding:4px 0;font-size:0.85rem;font-family:monospace;">
                                    <span style="color:${color};font-weight:600;">${entry.success ? 'OK' : 'ERR'}</span>
                                    <span style="color:var(--text-muted);margin:0 8px;">${App.escapeHtml(entry.step)}</span>
                                    <span style="color:var(--text-primary);">${App.escapeHtml((entry.output || '').substring(0, 200))}</span>
                                </div>`;
                            }).join('');

                            let countdown = 15;
                            const countdownId = setInterval(() => {
                                countdown--;
                                const el = document.getElementById('update-countdown');
                                if (el) el.textContent = countdown;
                                if (countdown <= 0) {
                                    clearInterval(countdownId);
                                    window.location.reload();
                                }
                            }, 1000);

                            result.innerHTML = `
                                <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:12px;margin-top:8px;">
                                    <strong style="color:var(--accent-green);">Aggiornamento completato</strong>
                                    <span style="color:var(--text-muted);margin-left:12px;">${App.escapeHtml(data.old_sha)} → ${App.escapeHtml(data.new_sha)}</span>
                                    <div style="margin-top:8px;">${logHtml}</div>
                                    <p style="margin-top:12px;color:var(--text-muted);font-size:0.85rem;">
                                        Il servizio si sta riavviando. La pagina si ricarica tra <strong id="update-countdown">${countdown}</strong> secondi...
                                    </p>
                                </div>`;
                        } catch (err) {
                            showToast(err.message, 'error');
                            result.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
                        }
                    }
                },
            ]
        );
    },

    // --- Audit Log ---

    async loadAuditLog(page = 1) {
        this.auditPage = page;
        const container = document.getElementById('admin-audit-log');
        try {
            const res = await Auth.apiRequest(`/admin/audit-log?per_page=15&page=${page}`);
            if (!res.ok) throw new Error('Errore caricamento audit log');
            const data = await res.json();
            if (!data.items.length) {
                container.innerHTML = '<p style="color:var(--text-muted)">Nessuna voce nel log.</p>';
                return;
            }

            const rows = data.items.map(log => {
                const ts = log.timestamp ? new Date(log.timestamp).toLocaleString('it-IT') : '-';
                let detail = log.detail || '-';
                try {
                    const parsed = JSON.parse(detail);
                    detail = Object.entries(parsed).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ');
                } catch { /* keep as-is */ }

                return `
                    <tr>
                        <td><span class="badge" style="background:var(--bg-tertiary);color:var(--accent)">${App.escapeHtml(log.action)}</span></td>
                        <td style="color:var(--text-muted);max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${App.escapeHtml(detail)}</td>
                        <td style="color:var(--text-muted);font-size:0.85rem;white-space:nowrap">${ts}</td>
                    </tr>`;
            }).join('');

            const totalPages = Math.ceil(data.total / data.per_page);
            const pagination = totalPages > 1 ? `
                <div style="display:flex;justify-content:center;gap:8px;margin-top:16px;">
                    ${page > 1 ? `<button class="btn btn-sm btn-audit-prev">Precedente</button>` : ''}
                    <span style="color:var(--text-muted);padding:8px;">Pagina ${page} di ${totalPages}</span>
                    ${page < totalPages ? `<button class="btn btn-sm btn-audit-next">Successiva</button>` : ''}
                </div>` : '';

            container.innerHTML = `
                <div class="table-container">
                    <table>
                        <thead><tr><th>Azione</th><th>Dettaglio</th><th>Data</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                ${pagination}`;

            const prevBtn = container.querySelector('.btn-audit-prev');
            const nextBtn = container.querySelector('.btn-audit-next');
            if (prevBtn) prevBtn.addEventListener('click', () => this.loadAuditLog(page - 1));
            if (nextBtn) nextBtn.addEventListener('click', () => this.loadAuditLog(page + 1));
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>`;
        }
    },

    // --- Database Backup / Restore ---

    async downloadBackup() {
        try {
            const res = await Auth.apiRequest('/admin/db/backup');
            if (!res.ok) throw new Error('Errore durante il backup');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            const disposition = res.headers.get('content-disposition') || '';
            const match = disposition.match(/filename="?([^"]+)"?/);
            a.download = match ? match[1] : 'mubi_backup.db';
            a.href = url;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showToast('Backup scaricato con successo', 'success');
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    showRestoreModal() {
        const body = `
            <p style="color:var(--accent-amber);margin-bottom:16px;font-weight:600;">
                Questa operazione sovrascrive il database corrente. Assicurati di avere un backup recente.
            </p>
            <div id="restore-drop-zone" style="border:2px dashed var(--border);border-radius:var(--radius);padding:40px 20px;text-align:center;cursor:pointer;transition:border-color 0.2s,background 0.2s;">
                <p style="color:var(--text-muted);margin-bottom:8px;">Trascina qui il file .db oppure clicca per selezionarlo</p>
                <input type="file" id="restore-file-input" accept=".db" style="display:none;">
                <p id="restore-file-name" style="color:var(--text-primary);font-weight:600;margin-top:8px;display:none;"></p>
            </div>
            <div id="restore-progress" style="display:none;margin-top:16px;text-align:center;">
                <div class="spinner" style="margin:10px auto;"></div>
                <p style="color:var(--text-muted);">Ripristino in corso...</p>
            </div>`;

        showModal('Ripristina Database', body, [
            { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
            { label: 'Ripristina', class: 'btn-danger', onClick: () => this.executeRestore() },
        ]);

        const dropZone = document.getElementById('restore-drop-zone');
        const fileInput = document.getElementById('restore-file-input');
        const fileName = document.getElementById('restore-file-name');

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--accent)';
            dropZone.style.background = 'var(--bg-tertiary)';
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = 'transparent';
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = 'transparent';
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                fileName.textContent = e.dataTransfer.files[0].name;
                fileName.style.display = 'block';
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                fileName.textContent = fileInput.files[0].name;
                fileName.style.display = 'block';
            }
        });
    },

    async executeRestore() {
        const fileInput = document.getElementById('restore-file-input');
        if (!fileInput || !fileInput.files.length) {
            showToast('Seleziona un file .db da ripristinare', 'error');
            return;
        }

        const file = fileInput.files[0];
        if (!file.name.endsWith('.db')) {
            showToast('Il file deve avere estensione .db', 'error');
            return;
        }

        const progress = document.getElementById('restore-progress');
        if (progress) progress.style.display = 'block';

        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await Auth.apiRequest('/admin/db/restore', {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore durante il ripristino');
            }
            const data = await res.json();
            closeModal();
            showToast(`Database ripristinato. Backup automatico: ${data.auto_backup}`, 'success');
            // Ricarica la pagina per riflettere il nuovo DB
            setTimeout(() => window.location.reload(), 1500);
        } catch (err) {
            if (progress) progress.style.display = 'none';
            showToast(err.message, 'error');
        }
    },

    confirmReinitDb() {
        showModal(
            'Reinizializza Database',
            `<p style="color:var(--accent-red);font-weight:600;margin-bottom:12px;">
                Attenzione: questa operazione elimina tutti i dati presenti nel database.
             </p>
             <p style="color:var(--text-muted);font-size:0.9rem;">
                Verrà eseguito un backup automatico prima di procedere.<br>
                Utenti, PEC, pratiche e tutti i record verranno cancellati definitivamente.
             </p>`,
            [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                {
                    label: 'Reinizializza',
                    class: 'btn-danger',
                    onClick: async () => {
                        closeModal();
                        try {
                            const res = await Auth.apiRequest('/admin/db/reinit', { method: 'POST' });
                            if (!res.ok) {
                                const err = await res.json();
                                throw new Error(err.detail || 'Errore durante la reinizializzazione');
                            }
                            const data = await res.json();
                            showToast(`Database reinizializzato. Backup: ${data.auto_backup}`, 'success');
                            setTimeout(() => window.location.reload(), 1500);
                        } catch (err) {
                            showToast(err.message, 'error');
                        }
                    },
                },
            ]
        );
    },
};
