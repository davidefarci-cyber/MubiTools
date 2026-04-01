/**
 * MUBI Tools — Pannello Admin
 * Gestione utenti, aggiornamenti, audit log
 */

const Admin = {
    users: [],
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
                <div class="card-title">Aggiornamenti</div>
                <div id="admin-updates">
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
        this.loadUsers();
        this.loadUpdateInfo();
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
        document.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const user = this.users.find(u => u.id === parseInt(btn.dataset.id));
                if (user) this.showEditUserModal(user);
            });
        });
        document.querySelectorAll('.btn-toggle').forEach(btn => {
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

    // --- Updates ---

    async loadUpdateInfo() {
        const container = document.getElementById('admin-updates');
        try {
            const res = await Auth.apiRequest('/admin/update/check');
            if (!res.ok) throw new Error('Errore controllo aggiornamenti');
            const data = await res.json();

            const hasUpdate = data.update_available;
            const errorMsg = data.error ? `<p style="color:var(--accent-amber);font-size:0.85rem;margin-top:8px;">Errore controllo: ${App.escapeHtml(data.error)}</p>` : '';

            container.innerHTML = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:16px;">
                    <div class="stat-card">
                        <div class="stat-label">Versione locale</div>
                        <div class="stat-value">${data.local_version || '-'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Versione remota</div>
                        <div class="stat-value" style="color:${hasUpdate ? 'var(--accent-green)' : 'var(--text-primary)'}">
                            ${data.remote_version || 'N/D'}
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Stato</div>
                        <div class="stat-value" style="color:${hasUpdate ? 'var(--accent-amber)' : 'var(--accent-green)'}">
                            ${hasUpdate ? 'Aggiornamento disponibile' : 'Aggiornato'}
                        </div>
                    </div>
                </div>
                ${errorMsg}
                <div style="display:flex;gap:12px;margin-top:8px;">
                    <button class="btn btn-sm btn-edit" id="btn-check-updates">Controlla Aggiornamenti</button>
                    ${hasUpdate ? '<button class="btn btn-sm btn-primary" id="btn-do-update">Aggiorna Ora</button>' : ''}
                </div>
                <div id="update-log" style="margin-top:16px;display:none;"></div>
            `;

            document.getElementById('btn-check-updates').addEventListener('click', () => this.loadUpdateInfo());
            const btnUpdate = document.getElementById('btn-do-update');
            if (btnUpdate) {
                btnUpdate.addEventListener('click', () => this.confirmUpdate());
            }
        } catch (err) {
            container.innerHTML = `<p style="color:var(--accent-red)">${App.escapeHtml(err.message)}</p>
                <button class="btn btn-sm btn-edit" onclick="Admin.loadUpdateInfo()">Riprova</button>`;
        }
    },

    confirmUpdate() {
        showModal(
            'Conferma Aggiornamento',
            '<p>Vuoi aggiornare MUBI Tools all\'ultima versione?</p><p style="color:var(--text-muted);font-size:0.85rem;margin-top:8px;">Il sistema eseguira\' git pull, aggiornerà le dipendenze e riavviera\' il servizio.</p>',
            [
                { label: 'Annulla', class: 'btn-cancel', onClick: () => closeModal() },
                { label: 'Aggiorna Ora', class: 'btn-primary', onClick: () => { closeModal(); this.performUpdate(); } },
            ]
        );
    },

    async performUpdate() {
        const logDiv = document.getElementById('update-log');
        if (logDiv) {
            logDiv.style.display = 'block';
            logDiv.innerHTML = '<div class="spinner" style="margin:10px auto;"></div><p style="color:var(--text-muted);text-align:center;">Aggiornamento in corso...</p>';
        }

        try {
            const res = await Auth.apiRequest('/admin/update', { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Errore avvio aggiornamento');
            }

            // Poll per risultato
            this._pollUpdateStatus(logDiv);
        } catch (err) {
            if (logDiv) logDiv.innerHTML = `<p style="color:var(--accent-red)">Errore: ${App.escapeHtml(err.message)}</p>`;
            showToast(err.message, 'error');
        }
    },

    async _pollUpdateStatus(logDiv) {
        const poll = async () => {
            try {
                const res = await Auth.apiRequest('/admin/update/status');
                if (!res.ok) return;
                const data = await res.json();

                if (data.running) {
                    setTimeout(poll, 2000);
                    return;
                }

                if (data.result) {
                    const r = data.result;
                    const logHtml = (r.log || []).map(entry => {
                        const icon = entry.success ? 'var(--accent-green)' : 'var(--accent-red)';
                        return `<div style="padding:4px 0;font-size:0.85rem;">
                            <span style="color:${icon};font-weight:600;">${entry.success ? 'OK' : 'ERR'}</span>
                            <span style="color:var(--text-muted);margin:0 8px;">${App.escapeHtml(entry.step)}</span>
                            <span>${App.escapeHtml((entry.output || '').substring(0, 200))}</span>
                        </div>`;
                    }).join('');

                    if (logDiv) {
                        logDiv.innerHTML = `
                            <div style="background:var(--bg-tertiary);border-radius:var(--radius);padding:12px;margin-top:8px;">
                                <strong style="color:${r.success ? 'var(--accent-green)' : 'var(--accent-red)'}">
                                    ${r.success ? 'Aggiornamento completato' : 'Aggiornamento fallito'}
                                </strong>
                                ${r.new_version ? `<span style="color:var(--text-muted);margin-left:12px;">v${r.new_version}</span>` : ''}
                                <div style="margin-top:8px;">${logHtml}</div>
                            </div>`;
                    }

                    showToast(
                        r.success ? 'Aggiornamento completato' : 'Aggiornamento fallito',
                        r.success ? 'success' : 'error'
                    );
                }
            } catch {
                if (logDiv) logDiv.innerHTML = '<p style="color:var(--accent-red)">Errore nel polling stato aggiornamento</p>';
            }
        };
        setTimeout(poll, 2000);
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
             <p style="color:var(--text-muted);font-size:0.85rem;">L'applicazione potrebbe richiedere un riavvio dopo l'aggiornamento.</p>`,
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
                            const msg = data.restart_required
                                ? `Aggiornamento completato (${data.old_sha} → ${data.new_sha}). Riavvio consigliato.`
                                : `Aggiornamento completato. Nessuna modifica rilevata.`;
                            showToast(msg, 'success');
                            this.loadUpdates();
                            this.loadSystemInfo();
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
    }
};
