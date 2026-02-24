// SPDX-License-Identifier: AGPL-3.0-or-later
// TGC BUS Core (Business Utility System Core)
// Copyright (C) 2025 True Good Craft
//
// This file is part of TGC BUS Core.
//
// TGC BUS Core is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.
//
// TGC BUS Core is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

import { ensureToken, rawFetch } from '../api.js';

export function mountBackup(container) {
  if (container) {
    container.innerHTML = `
      <div class="card">
        <button type="button" data-action="export-backup">Export</button>
        <small class="muted">Downloads current app.db (or fallback endpoint).</small>
      </div>
    `;
  }
  mountBackupExport();
}

export function mountBackupExport() {
  const btn = document.querySelector('[data-action="export-backup"]');
  if (!btn || btn.dataset.backupBound) return;
  btn.dataset.backupBound = '1';

  btn.addEventListener('click', async () => {
    try {
      const token = await ensureToken();
      const tryDownload = async (url, filename) => {
        const res = await rawFetch(url, {
          headers: { 'X-Session-Token': token },
        });
        if (!res.ok) return false;
        const blob = await res.blob();
        const link = document.createElement('a');
        const href = URL.createObjectURL(blob);
        link.href = href;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
        return true;
      };

      if (await tryDownload('/app/backup', 'app-backup.db')) return;
      if (await tryDownload('/app.db', 'app.db')) return;
      alert('No backup endpoint found.');
    } catch (err) {
      console.error('backup export failed', err);
      alert('Could not export backup.');
    }
  });
}

export default mountBackup;
