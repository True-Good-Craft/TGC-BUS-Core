// SPDX-License-Identifier: AGPL-3.0-or-later
// Contacts & Vendors card (unified shallow/deep flows)

import { apiDelete, apiGet, apiPost, apiPut, ensureToken } from '../api.js';

const ROLE_FILTERS = [
  { key: 'all', label: 'All', is_vendor: null },
  { key: 'vendors', label: 'Vendors', is_vendor: true },
  { key: 'contacts', label: 'Contacts', is_vendor: false },
];

function formatDate(val) {
  if (!val) return '';
  try {
    const d = new Date(val);
    if (Number.isNaN(d.getTime())) return String(val);
    return d.toLocaleString();
  } catch {
    return String(val);
  }
}

function chip(text, tone = 'default') {
  const span = document.createElement('span');
  span.textContent = text;
  span.className = `contacts-chip contacts-chip--${tone}`;
  return span;
}

function button(label) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = label;
  btn.className = 'contacts-btn';
  return btn;
}

function input(label, type = 'text') {
  const wrap = document.createElement('label');
  wrap.className = 'contacts-field';

  const span = document.createElement('span');
  span.textContent = label;
  span.className = 'contacts-field-label';
  const field = document.createElement('input');
  field.type = type;
  field.className = 'contacts-input';

  wrap.append(span, field);
  return { wrap, field };
}

function select(label) {
  const wrap = document.createElement('label');
  wrap.className = 'contacts-field';

  const span = document.createElement('span');
  span.textContent = label;
  span.className = 'contacts-field-label';
  const field = document.createElement('select');
  field.className = 'contacts-input';

  wrap.append(span, field);
  return { wrap, field };
}

function toast(message, tone = 'ok') {
  const el = document.createElement('div');
  el.textContent = message;
  el.className = `contacts-toast contacts-toast--${tone === 'error' ? 'error' : 'ok'}`;
  document.body.appendChild(el);
  setTimeout(() => {
    el.classList.add('contacts-toast--hide');
    setTimeout(() => el.remove(), 300);
  }, 2000);
}

function vendorLabel(isVendor) {
  return isVendor ? 'Vendor' : 'Contact';
}

function buildContactPayload(modalEl) {
  const name = modalEl.querySelector('[data-field="name"]')?.value?.trim() || '';
  const email = modalEl.querySelector('[data-field="email"]')?.value?.trim() || '';
  const phone = modalEl.querySelector('[data-field="phone"]')?.value?.trim() || '';
  const extend = modalEl.querySelector('[data-field="extend"]')?.checked || false;
  const isVendor = modalEl.querySelector('[data-field="is_vendor"]')?.checked || false;
  const isOrg = modalEl.querySelector('[data-field="is_org"]')?.checked || false;
  const orgRaw = modalEl.querySelector('[data-field="organization_id"]')?.value;
  const organizationId = Number.isInteger(Number(orgRaw)) && Number(orgRaw) > 0 ? Number(orgRaw) : undefined;

  const addr1 = modalEl.querySelector('[data-field="addr1"]')?.value?.trim() || '';
  const addr2 = modalEl.querySelector('[data-field="addr2"]')?.value?.trim() || '';
  const city = modalEl.querySelector('[data-field="city"]')?.value?.trim() || '';
  const state = modalEl.querySelector('[data-field="state"]')?.value?.trim() || '';
  const zip = modalEl.querySelector('[data-field="zip"]')?.value?.trim() || '';
  const notes = modalEl.querySelector('[data-field="notes"]')?.value?.trim() || '';

  const address = {
    line1: addr1 || null,
    line2: addr2 || null,
    city: city || null,
    state: state || null,
    zip: zip || null,
  };
  const hasAddress = Object.values(address).some(Boolean);

  const meta = {
    email: email || null,
    phone: phone || null,
  };

  if (extend || hasAddress) {
    meta.address = address;
  }

  if (extend || notes) {
    meta.notes = notes || null;
  }

  if (!meta.email) delete meta.email;
  if (!meta.phone) delete meta.phone;
  if (meta.address && !hasAddress) delete meta.address;
  if (meta.notes == null) delete meta.notes;

  const payload = {
    name,
    contact: email || phone || null,
    is_vendor: !!isVendor,
    is_org: !!isOrg,
  };

  if (!isOrg && organizationId !== undefined) {
    payload.organization_id = organizationId;
  }

  if (Object.keys(meta).length) {
    payload.meta = meta;
  }

  return payload;
}

function buildModal() {
  const overlay = document.createElement('div');
  overlay.className = 'contacts-modal';

  const box = document.createElement('div');
  box.className = 'contacts-modal-box';

  overlay.appendChild(box);
  return { overlay, box };
}

export function mountContacts(host) {
  if (!host) return;
  host.innerHTML = '';
  host.className = 'contacts-shell';

  const state = {
    list: [],
    orgs: [],
    expandedId: null,
    filterRole: 'all',
    search: '',
  };

  const header = document.createElement('div');
  header.className = 'contacts-header';

  const headLeft = document.createElement('div');
  headLeft.className = 'contacts-head-left';

  const title = document.createElement('h2');
  title.textContent = 'Contacts';
  title.className = 'contacts-title';

  const subtitle = document.createElement('div');
  subtitle.textContent = 'Vendors & people you deal with';
  subtitle.className = 'contacts-subtitle';

  headLeft.append(title, subtitle);

  const newBtn = button('+ New Contact');

  header.append(headLeft, newBtn);

  const filtersRow = document.createElement('div');
  filtersRow.className = 'contacts-filters-row';

  ROLE_FILTERS.forEach((f) => {
    const b = button(f.label);
    b.classList.add('contacts-filter-btn');
    const setActive = () => {
      b.classList.toggle('active', state.filterRole === f.key);
    };
    setActive();
    b.addEventListener('click', () => {
      state.filterRole = f.key;
      setActive();
      void loadData();
    });
    filtersRow.appendChild(b);
  });

  const searchWrap = document.createElement('div');
  searchWrap.className = 'contacts-search-wrap';

  const searchField = document.createElement('input');
  searchField.type = 'search';
  searchField.placeholder = 'Search name or contact…';
  searchField.className = 'contacts-search-input';
  searchField.addEventListener('input', () => {
    state.search = searchField.value.trim();
    void loadData();
  });

  searchWrap.appendChild(searchField);
  filtersRow.appendChild(searchWrap);

  const table = document.createElement('div');
  table.className = 'contacts-table';

  const headerRow = document.createElement('div');
  headerRow.className = 'contacts-table-head';
    ['Name', 'Contact', 'Flags'].forEach((col) => {
      const c = document.createElement('div');
      c.textContent = col;
      headerRow.appendChild(c);
    });

  const body = document.createElement('div');
  body.className = 'contacts-table-body';

  table.append(headerRow, body);

  host.append(header, filtersRow, table);

  function orgName(id) {
    if (id == null) return null;
    const found = state.orgs.find((o) => o.id === id) || state.list.find((o) => o.id === id);
    return found?.name || null;
  }

  function contactSummary(entry) {
    const meta = entry?.meta || {};
    return [meta.email, meta.phone].filter(Boolean).join(' | ');
  }

  function renderRow(entry) {
    const row = document.createElement('div');
    row.className = 'contacts-row';

    const nameCol = document.createElement('div');
    nameCol.className = 'contacts-name-col';

    const nameLine = document.createElement('div');
    nameLine.className = 'contacts-name-line';
    const nm = document.createElement('div');
    nm.textContent = entry.name || '(unnamed)';
    nm.className = 'contacts-name-text';
    const vendorBadge = chip(vendorLabel(Boolean(entry.is_vendor)), entry.is_vendor ? 'accent' : 'default');
    if (!entry.is_vendor) vendorBadge.classList.add('contacts-chip--muted');
    nameLine.append(nm, vendorBadge);
    if (entry.is_org) {
      const orgBadge = chip('Organization');
      nameLine.append(orgBadge);
    }

    const metaLine = document.createElement('div');
    metaLine.className = 'contacts-meta-line';
    const org = orgName(entry.organization_id);
    metaLine.textContent = [contactSummary(entry), org ? `Org: ${org}` : '']
      .filter(Boolean)
      .join(' • ');

    nameCol.append(nameLine, metaLine);

    const contactCol = document.createElement('div');
    contactCol.textContent = contactSummary(entry) || '—';
    contactCol.className = 'contacts-contact-col';

    const flagsCol = document.createElement('div');
    flagsCol.className = 'contacts-flags-col';
    flagsCol.append(chip(vendorLabel(Boolean(entry.is_vendor)), entry.is_vendor ? 'accent' : 'default'));
    if (entry.is_org) {
      flagsCol.append(chip('Organization'));
    }

    // Do not render actions in the collapsed row; they appear in the drawer only.
    row.append(nameCol, contactCol, flagsCol);

    const expanded = document.createElement('div');
    expanded.className = 'contacts-expanded';
    expanded.classList.toggle('is-open', state.expandedId === entry.id);

    const left = document.createElement('div');
    left.className = 'contacts-expanded-left';
    const nameLabel = document.createElement('div');
    nameLabel.textContent = entry.name || '(unnamed)';
    nameLabel.className = 'contacts-expanded-name';
    const chipsRow = document.createElement('div');
    chipsRow.className = 'contacts-expanded-chips';
    chipsRow.append(chip(vendorLabel(Boolean(entry.is_vendor)), entry.is_vendor ? 'accent' : 'default'));
    if (entry.is_org) chipsRow.append(chip('Organization'));
    const orgLine = document.createElement('div');
    orgLine.className = 'contacts-expanded-org';
    const orgLabel = orgName(entry.organization_id);
    orgLine.textContent = orgLabel ? `Organization: ${orgLabel}` : 'No organization linked';
    left.append(nameLabel, chipsRow, orgLine);

    const right = document.createElement('div');
    right.className = 'contacts-expanded-right';
    const contactLine = document.createElement('div');
    contactLine.textContent = `Contact: ${contactSummary(entry) || '—'}`;
    const createdLine = document.createElement('div');
    createdLine.textContent = `Created at: ${formatDate(entry.created_at) || '—'}`;
    right.append(contactLine, createdLine);

    const footer = document.createElement('div');
    footer.className = 'contacts-expanded-footer';
    const edit2 = button('Edit');
    edit2.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openEditor(entry);
    });
    const del2 = button('Delete');
    del2.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openDelete(entry);
    });
    footer.append(edit2, del2);

    expanded.append(left, right, footer);

    row.addEventListener('click', () => {
      state.expandedId = state.expandedId === entry.id ? null : entry.id;
      render();
    });

    const wrapper = document.createElement('div');
    wrapper.append(row, expanded);
    return wrapper;
  }

  function renderEmpty() {
    const empty = document.createElement('div');
    empty.textContent = 'No contacts yet.';
    empty.className = 'contacts-empty';
    return empty;
  }

  function render() {
    body.innerHTML = '';
    if (!state.list.length) {
      body.appendChild(renderEmpty());
      return;
    }
    state.list.forEach((entry) => body.appendChild(renderRow(entry)));
  }

  async function loadOrgs() {
    try {
      let res = await apiGet('/app/vendors?is_org=true');
      if (!Array.isArray(res) || !res.length) {
        res = await apiGet('/app/vendors?is_vendor=true');
      }
      state.orgs = Array.isArray(res) ? res : [];
    } catch (err) {
      if (err && (err.status === 404 || err.status === 500)) {
        state.orgs = [];
      } else {
        throw err;
      }
    }
  }

  function handleContactsDeepLink() {
    const r = window.BUS_ROUTE;
    if (!r || r.base !== '#/contacts' || !r.id) return;

    const id = String(r.id);
    const it = (state.list || []).find((x) => String(x?.id) === id);

    if (it) {
      state.expandedId = it.id;
      render();
    } else {
      toast(`Contact not found: ${id}`, 'error');
      window.location.hash = '#/contacts';
    }

    window.BUS_ROUTE = { ...r, id: null };
  }

  async function loadData() {
    const params = new URLSearchParams();
    const selected = ROLE_FILTERS.find((f) => f.key === state.filterRole);
    if (selected && selected.is_vendor !== null && selected.is_vendor !== undefined) params.set('is_vendor', selected.is_vendor);
    if (state.search) params.set('q', state.search);
    try {
      const res = await apiGet(`/app/contacts?${params.toString()}`);
      state.list = Array.isArray(res)
        ? res.map((r) => ({ ...r, facade: r.is_vendor ? 'vendors' : 'contacts' }))
        : [];
    } catch (err) {
      if (err && (err.status === 404 || err.status === 500)) {
        state.list = [];
      } else {
        throw err;
      }
    }
    await loadOrgs();
    render();
  }

  function buildToggle(label, initial = false) {
    const wrap = document.createElement('label');
    wrap.className = 'contacts-toggle';
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = !!initial;
    const text = document.createElement('span');
    text.textContent = label;
    text.className = 'contacts-toggle-label';
    wrap.append(box, text);
    return {
      wrap,
      input: box,
      getValue: () => box.checked,
      setValue: (val) => {
        box.checked = !!val;
      },
    };
  }

  function openEditor(entry = {}) {
    const isEdit = Boolean(entry?.id);
    const { overlay, box } = buildModal();

    const meta = entry.meta || {};
    const addressMeta = meta.address || {};
    let inferredEmail = meta.email || entry.email || '';
    let inferredPhone = meta.phone || entry.phone || '';

    if (!inferredEmail && typeof entry.contact === 'string') {
      const [maybeEmail, maybePhone] = entry.contact.split('|').map((s) => s.trim());
      if (maybeEmail) inferredEmail = maybeEmail;
      if (maybePhone && !inferredPhone) inferredPhone = maybePhone;
    }
    const initialNotes = meta.notes || '';
    const initialExtended = Boolean(
      addressMeta.line1 ||
        addressMeta.line2 ||
        addressMeta.city ||
        addressMeta.state ||
        addressMeta.zip ||
        initialNotes
    );

    const titleRow = document.createElement('div');
    titleRow.className = 'contacts-modal-title-row';

    const heading = document.createElement('div');
    heading.textContent = isEdit ? 'Edit Contact' : 'New Contact';
    heading.className = 'contacts-modal-title';

    const closeBtn = button('Cancel');

    titleRow.append(heading, closeBtn);

    const form = document.createElement('div');
    form.className = 'contacts-modal-form';

    const { wrap: nameWrap, field: nameField } = input('Name *');
    nameField.required = true;
    nameField.placeholder = 'Full name or company';
    nameField.value = entry?.name || '';
    nameField.dataset.field = 'name';

    const { wrap: emailWrap, field: emailField } = input('Email', 'email');
    emailField.placeholder = 'name@domain.com';
    emailField.value = inferredEmail || '';
    emailField.dataset.field = 'email';

    const { wrap: phoneWrap, field: phoneField } = input('Phone', 'tel');
    phoneField.placeholder = '555-0123';
    phoneField.value = inferredPhone || '';
    phoneField.dataset.field = 'phone';

    const togglesRow = document.createElement('div');
    togglesRow.className = 'contacts-toggles-row';

    const extendToggle = buildToggle('Add Address & Notes', initialExtended);
    const vendorToggle = buildToggle('Treat as Vendor', entry?.is_vendor ?? entry?.facade === 'vendors');
    const orgToggle = buildToggle('Treat as Organization', !!entry?.is_org);

    extendToggle.input.dataset.field = 'extend';
    vendorToggle.input.dataset.field = 'is_vendor';
    orgToggle.input.dataset.field = 'is_org';

    const orgSelectWrap = document.createElement('label');
    orgSelectWrap.className = 'contacts-field';
    const orgSelectLabel = document.createElement('span');
    orgSelectLabel.className = 'contacts-field-label';
    orgSelectLabel.textContent = 'Parent Organization';
    const orgSelect = document.createElement('select');
    orgSelect.className = 'contacts-input';
    orgSelect.dataset.field = 'organization_id';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = 'None';
    orgSelect.appendChild(noneOpt);
    (state.orgs || [])
      .filter((o) => o && o.id != null && String(o.id) !== String(entry?.id))
      .forEach((o) => {
        const opt = document.createElement('option');
        opt.value = String(o.id);
        opt.textContent = o.name || `Org #${o.id}`;
        orgSelect.appendChild(opt);
      });
    if (entry?.organization_id != null) {
      orgSelect.value = String(entry.organization_id);
    }
    orgSelectWrap.append(orgSelectLabel, orgSelect);
    const syncOrgParentState = () => {
      orgSelectWrap.classList.toggle('hidden', orgToggle.getValue());
      orgSelect.disabled = orgToggle.getValue();
      if (orgToggle.getValue()) orgSelect.value = '';
    };
    orgToggle.input.addEventListener('change', syncOrgParentState);
    syncOrgParentState();

    togglesRow.append(extendToggle.wrap, vendorToggle.wrap, orgToggle.wrap);

    const extendedSection = document.createElement('div');
    extendedSection.className = 'contacts-extended-section';
    extendedSection.classList.toggle('is-open', extendToggle.getValue());

    const { wrap: addr1Wrap, field: addr1Field } = input('Address Line 1');
    addr1Field.placeholder = '123 Main St';
    addr1Field.value = addressMeta.line1 || '';
    addr1Field.dataset.field = 'addr1';

    const { wrap: addr2Wrap, field: addr2Field } = input('Address Line 2');
    addr2Field.placeholder = 'Unit, Suite, etc.';
    addr2Field.value = addressMeta.line2 || '';
    addr2Field.dataset.field = 'addr2';

    const cityStateZip = document.createElement('div');
    cityStateZip.className = 'contacts-city-grid';

    const { wrap: cityWrap, field: cityField } = input('City');
    cityField.placeholder = 'City';
    cityField.dataset.field = 'city';

    const { wrap: stateWrap, field: stateField } = input('State');
    stateField.placeholder = 'State';
    stateField.dataset.field = 'state';

    const { wrap: zipWrap, field: zipField } = input('Zip');
    zipField.placeholder = 'Zip';
    zipField.dataset.field = 'zip';

    cityStateZip.append(cityWrap, stateWrap, zipWrap);

    const notesWrap = document.createElement('label');
    notesWrap.className = 'contacts-field';
    const notesLabel = document.createElement('span');
    notesLabel.textContent = 'Notes';
    notesLabel.className = 'contacts-field-label';
    const notesField = document.createElement('textarea');
    notesField.rows = 3;
    notesField.placeholder = 'Anything helpful…';
    notesField.className = 'contacts-input contacts-textarea';
    notesField.value = initialNotes;
    notesField.dataset.field = 'notes';
    notesWrap.append(notesLabel, notesField);

    extendedSection.append(addr1Wrap, addr2Wrap, cityStateZip, notesWrap);

    extendToggle.input.addEventListener('change', () => {
      extendedSection.classList.toggle('is-open', extendToggle.getValue());
    });

    form.append(nameWrap, emailWrap, phoneWrap, togglesRow, orgSelectWrap, extendedSection);

    const actions = document.createElement('div');
    actions.className = 'contacts-modal-actions';

    const saveBtn = button('Save');
    saveBtn.disabled = !nameField.value.trim();

    const cancelBtn = button('Cancel');
    cancelBtn.addEventListener('click', () => document.body.removeChild(overlay));

    nameField.addEventListener('input', () => {
      saveBtn.disabled = !nameField.value.trim();
    });

    async function save() {
      const nameVal = box.querySelector('[data-field="name"]')?.value?.trim() || '';
      const payload = buildContactPayload(box);

      const errors = [];
      if (!nameVal) errors.push('Name is required.');
      if (errors.length) {
        toast(errors.join(' '), 'error');
        return;
      }

      try {
        saveBtn.textContent = 'Saving…';
        saveBtn.disabled = true;
        await ensureToken();
        let saved;
        if (isEdit) {
          const facade = entry.facade || (entry.is_vendor ? 'vendors' : 'contacts');
          saved = await apiPut(`/app/${facade}/${entry.id}`, payload);
          toast('Saved');
        } else {
          saved = await apiPost('/app/contacts', payload);
          toast('Created');
        }
        if (saved) {
          window.dispatchEvent(new CustomEvent('contacts:saved', { detail: saved }));
        }
        overlay.remove();
        await loadData();
      } catch (err) {
        console.error('save contact failed', err);
        const detail = (() => {
          try {
            return err?.response?.data ?? err?.data ?? err?.detail;
          } catch (e) {
            console.warn('error parsing save response', e);
            return null;
          }
        })();
        if (detail) {
          const msg = typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => d.msg || d.error || JSON.stringify(d)).join('\n')
              : JSON.stringify(detail);
          toast(msg, 'error');
        } else {
          toast('Save failed', 'error');
        }
        saveBtn.textContent = 'Save';
        saveBtn.disabled = false;
      }
    }

    saveBtn.addEventListener('click', save);

    overlay.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        save();
      }
      if (e.key === 'Escape') {
        // Do not close on backdrop/escape; explicit Cancel only
        e.preventDefault();
        e.stopPropagation();
      }
    });

    closeBtn.addEventListener('click', () => {
      document.body.removeChild(overlay);
    });

    actions.append(cancelBtn, saveBtn);

    box.append(titleRow, form, actions);
    document.body.appendChild(overlay);
    nameField.focus();
  }

  async function openDelete(entry) {
    const { overlay, box } = buildModal();
    const heading = document.createElement('div');
    heading.textContent = 'Delete contact/vendor';
    heading.className = 'contacts-modal-title';

    const bodyText = document.createElement('div');
    bodyText.className = 'contacts-modal-body';
    bodyText.textContent = `What should happen to ${entry.name || 'this record'}?`;

    const actions = document.createElement('div');
    actions.className = 'contacts-delete-actions';

    const buttonsRow = document.createElement('div');
    buttonsRow.className = 'contacts-delete-buttons';

    const cancel = button('Cancel');
    cancel.addEventListener('click', () => document.body.removeChild(overlay));

    const confirm = button('Confirm');
    const facade = entry.facade || (entry.is_vendor ? 'vendors' : 'contacts');

    if (entry.is_org) {
      const notice = document.createElement('div');
      notice.className = 'contacts-modal-body';
      notice.textContent = 'Delete this organization. Optionally cascade to linked contacts.';

      const cascadeWrap = document.createElement('label');
      cascadeWrap.className = 'contacts-toggle';
      const cascadeBox = document.createElement('input');
      cascadeBox.type = 'checkbox';
      const cascadeLabel = document.createElement('span');
      cascadeLabel.textContent = 'Also delete linked contacts (counting…)';
      cascadeWrap.append(cascadeBox, cascadeLabel);

      actions.append(notice, cascadeWrap);

      try {
        const res = await apiGet(`/app/contacts?organization_id=${entry.id}`);
        const count = Array.isArray(res) ? res.length : 0;
        cascadeLabel.textContent = `Also delete ${count} linked contact${count === 1 ? '' : 's'}`;
      } catch (err) {
        console.warn('child count failed', err);
      }

      confirm.addEventListener('click', async () => {
        try {
          confirm.textContent = 'Deleting…';
          confirm.disabled = true;
          await ensureToken();
          const qs = cascadeBox.checked ? '?cascade_children=true' : '';
          await apiDelete(`/app/vendors/${entry.id}${qs}`);
          toast('Deleted');
          document.body.removeChild(overlay);
          await loadData();
        } catch (err) {
          console.error('delete org failed', err);
          toast('Delete failed', 'error');
          confirm.textContent = 'Confirm';
          confirm.disabled = false;
        }
      });
    } else {
      confirm.addEventListener('click', async () => {
        try {
          confirm.textContent = 'Deleting…';
          confirm.disabled = true;
          await ensureToken();
          await apiDelete(`/app/${facade}/${entry.id}`);
          toast('Deleted');
          document.body.removeChild(overlay);
          await loadData();
        } catch (err) {
          console.error('delete failed', err);
          toast('Delete failed', 'error');
          confirm.textContent = 'Confirm';
          confirm.disabled = false;
        }
      });
    }

    buttonsRow.append(cancel, confirm);

    box.append(heading, bodyText, actions, buttonsRow);
    document.body.appendChild(overlay);
    overlay.focus();
  }

  newBtn.addEventListener('click', () => openEditor({ is_vendor: false, is_org: false, facade: 'contacts' }));

  if (!window.__contactsHotkeyBlocker) {
    // Kill any plain "n" shortcut on the Contacts screen
    document.addEventListener(
      'keydown',
      (e) => {
        const target = e.target;
        const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
        if (typing) return;
        if ((e.key === 'n' || e.key === 'N') && !e.ctrlKey && !e.metaKey && !e.altKey) {
          e.stopImmediatePropagation();
          // do NOT open a new contact here
        }
      },
      true,
    );
    window.__contactsHotkeyBlocker = true;
  }

  if (!window.__contactsModalListener) {
    window.addEventListener('open-contacts-modal', (ev) => {
      const prefill = ev.detail?.prefill || {};
      openEditor({ ...prefill, facade: 'contacts' });
    });
    window.__contactsModalListener = true;
  }

  (async () => {
    await loadData();
    handleContactsDeepLink();
  })();
}


export default mountContacts;
