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

import { request } from '../token.js';

let initialized = false;
let vendorEditId = null;
let itemEditId = null;
let vendorCache = [];
let vendorTableEl;
let vendorForm;
let vendorSubmitBtn;
let vendorCancelBtn;
let vendorNameInput;
let vendorContactInput;
let vendorNotesInput;
let itemForm;
let itemSubmitBtn;
let itemCancelBtn;
let itemVendorSelect;
let itemSkuInput;
let itemNameInput;
let itemQtyInput;
let itemUnitInput;
let itemPriceInput;
let itemNotesInput;
let itemTableEl;
let itemFilterSelect;

async function jsonRequest(url, options){
  const opts = { ...(options || {}) };
  const headers = new Headers(opts.headers || {});
  if (opts.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const resp = await request(url, { ...opts, headers });
  if(resp.status === 204){
    return {};
  }
  if(!resp.ok){
    const text = await resp.text();
    throw new Error(text || resp.statusText);
  }
  return resp.json();
}

function clearVendorForm(){
  vendorEditId = null;
  vendorNameInput.value = '';
  vendorContactInput.value = '';
  vendorNotesInput.value = '';
  vendorSubmitBtn.textContent = 'Add Vendor';
  vendorCancelBtn.style.display = 'none';
}

function clearItemForm(){
  itemEditId = null;
  itemVendorSelect.value = '';
  itemSkuInput.value = '';
  itemNameInput.value = '';
  itemQtyInput.value = '';
  itemUnitInput.value = '';
  itemPriceInput.value = '';
  itemNotesInput.value = '';
  itemSubmitBtn.textContent = 'Add Item';
  itemCancelBtn.style.display = 'none';
}

function ensureTableStyles(table){
  table.style.width='100%';
  table.style.borderCollapse='collapse';
  table.querySelectorAll('th,td').forEach(cell=>{
    cell.style.borderBottom='1px solid #222';
    cell.style.padding='6px 8px';
    cell.style.verticalAlign='top';
  });
}

function renderVendors(vendors){
  vendorTableEl.innerHTML='';
  if(!vendors.length){
    vendorTableEl.textContent='No vendors yet.';
    return;
  }
  const table=document.createElement('table');
  const thead=document.createElement('thead');
  const headerRow=document.createElement('tr');
  ['ID','Name','Contact','Notes','Created','Actions'].forEach(label=>{
    const th=document.createElement('th');
    th.textContent=label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody=document.createElement('tbody');
  vendors.forEach(v=>{
    const tr=document.createElement('tr');
    const cells=[v.id,v.name||'',v.contact||'',v.notes||'',new Date(v.created_at).toLocaleString()];
    cells.forEach(val=>{
      const td=document.createElement('td');
      td.textContent=val==null?'':String(val);
      tr.appendChild(td);
    });
    const actions=document.createElement('td');
    const edit=document.createElement('button');
    edit.textContent='Edit';
    edit.onclick=()=>{
      vendorEditId=v.id;
      vendorNameInput.value=v.name||'';
      vendorContactInput.value=v.contact||'';
      vendorNotesInput.value=v.notes||'';
      vendorSubmitBtn.textContent='Update Vendor';
      vendorCancelBtn.style.display='inline-block';
    };
    const del=document.createElement('button');
    del.style.marginLeft='8px';
    del.textContent='Delete';
    del.onclick=async()=>{
      if(!confirm('Delete vendor '+(v.name||v.id)+'?')) return;
      try{
        await jsonRequest(`/app/vendors/${v.id}`,{method:'DELETE'});
        await loadVendors();
        await loadItems();
      }catch(err){
        alert('Delete failed: '+err.message);
      }
    };
    actions.appendChild(edit);
    actions.appendChild(del);
    tr.appendChild(actions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  ensureTableStyles(table);
  vendorTableEl.appendChild(table);
}

function vendorOptions(){
  const frag=document.createDocumentFragment();
  const empty=document.createElement('option');
  empty.value='';
  empty.textContent='— Vendor (optional) —';
  frag.appendChild(empty);
  vendorCache.forEach(v=>{
    const opt=document.createElement('option');
    opt.value=String(v.id);
    opt.textContent=v.name||`Vendor ${v.id}`;
    frag.appendChild(opt);
  });
  return frag;
}

function updateVendorSelects(){
  const currentVendorValue=itemVendorSelect.value;
  itemVendorSelect.innerHTML='';
  itemVendorSelect.appendChild(vendorOptions());
  if(currentVendorValue){
    itemVendorSelect.value=currentVendorValue;
  }
  const currentFilterValue=itemFilterSelect.value;
  const filterOptions=document.createDocumentFragment();
  const allOpt=document.createElement('option');
  allOpt.value='';
  allOpt.textContent='All vendors';
  filterOptions.appendChild(allOpt);
  vendorCache.forEach(v=>{
    const opt=document.createElement('option');
    opt.value=String(v.id);
    opt.textContent=v.name||`Vendor ${v.id}`;
    filterOptions.appendChild(opt);
  });
  itemFilterSelect.innerHTML='';
  itemFilterSelect.appendChild(filterOptions);
  if(currentFilterValue){
    itemFilterSelect.value=currentFilterValue;
  }
}

function vendorNameById(id){
  const found=vendorCache.find(v=>v.id===id);
  return found?found.name||`Vendor ${id}`:'';
}

function renderItems(items){
  itemTableEl.innerHTML='';
  if(!items.length){
    itemTableEl.textContent='No items yet.';
    return;
  }
  const table=document.createElement('table');
  const thead=document.createElement('thead');
  const headerRow=document.createElement('tr');
  ['ID','Vendor','SKU','Name','Qty','Unit','Price','Notes','Created','Actions'].forEach(label=>{
    const th=document.createElement('th');
    th.textContent=label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody=document.createElement('tbody');
  items.forEach(it=>{
    const tr=document.createElement('tr');
    const cells=[
      it.id,
      vendorNameById(it.vendor_id||0),
      it.sku||'',
      it.name||'',
      it.qty!=null?String(it.qty):'',
      it.unit||'',
      it.price!=null?String(it.price):'',
      it.notes||'',
      new Date(it.created_at).toLocaleString()
    ];
    cells.forEach(val=>{
      const td=document.createElement('td');
      td.textContent=val==null?'':String(val);
      tr.appendChild(td);
    });
    const actions=document.createElement('td');
    const edit=document.createElement('button');
    edit.textContent='Edit';
    edit.onclick=()=>{
      itemEditId=it.id;
      itemVendorSelect.value=it.vendor_id!=null?String(it.vendor_id):'';
      itemSkuInput.value=it.sku||'';
      itemNameInput.value=it.name||'';
      itemQtyInput.value=it.qty!=null?String(it.qty):'';
      itemUnitInput.value=it.unit||'';
      itemPriceInput.value=it.price!=null?String(it.price):'';
      itemNotesInput.value=it.notes||'';
      itemSubmitBtn.textContent='Update Item';
      itemCancelBtn.style.display='inline-block';
    };
    const del=document.createElement('button');
    del.style.marginLeft='8px';
    del.textContent='Delete';
    del.onclick=async()=>{
      if(!confirm('Delete item '+(it.name||it.id)+'?')) return;
      try{
        await jsonRequest(`/app/items/${it.id}`,{method:'DELETE'});
        await loadItems();
      }catch(err){
        alert('Delete failed: '+err.message);
      }
    };
    actions.appendChild(edit);
    actions.appendChild(del);
    tr.appendChild(actions);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  ensureTableStyles(table);
  itemTableEl.appendChild(table);
}

async function loadVendors(){
  try{
    vendorTableEl.textContent='Loading vendors…';
    vendorCache = await jsonRequest('/app/vendors');
    renderVendors(vendorCache);
    updateVendorSelects();
  }catch(err){
    vendorTableEl.textContent='Failed to load vendors';
  }
}

async function loadItems(){
  try{
    itemTableEl.textContent='Loading items…';
    const vendorFilter=itemFilterSelect.value?`?vendor_id=${encodeURIComponent(itemFilterSelect.value)}`:'';
    const items=await jsonRequest(`/app/items${vendorFilter}`);
    renderItems(items);
  }catch(err){
    itemTableEl.textContent='Failed to load items';
  }
}

function normalizeFloat(value){
  if(value===''||value==null) return null;
  const n=parseFloat(value);
  return Number.isFinite(n)?n:null;
}

function normalizeInt(value){
  if(value===''||value==null) return null;
  const n=parseInt(value,10);
  return Number.isFinite(n)?n:null;
}

export async function mountDomainCard(root){
  if(initialized){
    await loadVendors();
    await loadItems();
    return;
  }
  initialized=true;
  root.innerHTML=`
    <section>
      <h3>Vendors</h3>
      <form id="vendor-form">
        <div class="row">
          <input id="vendor-name" name="name" placeholder="Name" required>
          <input id="vendor-contact" name="contact" placeholder="Contact">
        </div>
        <textarea id="vendor-notes" name="notes" placeholder="Notes" rows="2" style="width:100%;margin-top:8px"></textarea>
        <div class="row" style="margin-top:8px">
          <button type="submit" id="vendor-submit">Add Vendor</button>
          <button type="button" id="vendor-cancel" style="display:none">Cancel</button>
        </div>
      </form>
      <div id="vendor-table" class="muted" style="margin-top:12px"></div>
    </section>
    <section style="margin-top:20px">
      <h3>Items</h3>
      <form id="item-form">
        <div class="row">
          <select id="item-vendor" name="vendor" style="min-width:200px"></select>
          <input id="item-sku" name="sku" placeholder="SKU">
          <input id="item-name" name="name" placeholder="Name" required>
        </div>
        <div class="row" style="margin-top:8px">
          <input id="item-qty" name="qty" placeholder="Qty" style="max-width:120px">
          <input id="item-unit" name="unit" placeholder="Unit" style="max-width:160px">
          <input id="item-price" name="price" placeholder="Price" style="max-width:160px">
        </div>
        <textarea id="item-notes" name="notes" placeholder="Notes" rows="2" style="width:100%;margin-top:8px"></textarea>
        <div class="row" style="margin-top:8px">
          <button type="submit" id="item-submit">Add Item</button>
          <button type="button" id="item-cancel" style="display:none">Cancel</button>
        </div>
      </form>
      <div class="row" style="margin-top:12px;align-items:center">
        <label class="muted">Filter by vendor:
          <select id="item-filter" style="margin-left:8px;min-width:200px"></select>
        </label>
      </div>
      <div id="item-table" class="muted" style="margin-top:12px"></div>
    </section>
  `;

  vendorForm=root.querySelector('#vendor-form');
  vendorSubmitBtn=root.querySelector('#vendor-submit');
  vendorCancelBtn=root.querySelector('#vendor-cancel');
  vendorNameInput=root.querySelector('#vendor-name');
  vendorContactInput=root.querySelector('#vendor-contact');
  vendorNotesInput=root.querySelector('#vendor-notes');
  vendorTableEl=root.querySelector('#vendor-table');

  vendorForm.addEventListener('submit',async (ev)=>{
    ev.preventDefault();
    const body={
      name:vendorNameInput.value.trim(),
      contact:vendorContactInput.value.trim()||null,
      notes:vendorNotesInput.value.trim()||null,
    };
    try{
      if(!body.name){
        alert('Name required');
        return;
      }
      if(vendorEditId){
        await jsonRequest(`/app/vendors/${vendorEditId}`,{method:'PUT',body:JSON.stringify(body)});
      }else{
        await jsonRequest('/app/vendors',{method:'POST',body:JSON.stringify(body)});
      }
      clearVendorForm();
      await loadVendors();
      await loadItems();
    }catch(err){
      alert('Save failed: '+err.message);
    }
  });

  vendorCancelBtn.addEventListener('click',()=>clearVendorForm());

  itemForm=root.querySelector('#item-form');
  itemSubmitBtn=root.querySelector('#item-submit');
  itemCancelBtn=root.querySelector('#item-cancel');
  itemVendorSelect=root.querySelector('#item-vendor');
  itemSkuInput=root.querySelector('#item-sku');
  itemNameInput=root.querySelector('#item-name');
  itemQtyInput=root.querySelector('#item-qty');
  itemUnitInput=root.querySelector('#item-unit');
  itemPriceInput=root.querySelector('#item-price');
  itemNotesInput=root.querySelector('#item-notes');
  itemTableEl=root.querySelector('#item-table');
  itemFilterSelect=root.querySelector('#item-filter');

  itemForm.addEventListener('submit',async(ev)=>{
    ev.preventDefault();
    const body={
      vendor_id:normalizeInt(itemVendorSelect.value),
      sku:itemSkuInput.value.trim()||null,
      name:itemNameInput.value.trim(),
      qty:normalizeFloat(itemQtyInput.value),
      unit:itemUnitInput.value.trim()||null,
      price:normalizeFloat(itemPriceInput.value),
      notes:itemNotesInput.value.trim()||null,
    };
    try{
      if(!body.name){
        alert('Name required');
        return;
      }
      if(itemEditId){
        await jsonRequest(`/app/items/${itemEditId}`,{method:'PUT',body:JSON.stringify(body)});
      }else{
        await jsonRequest('/app/items',{method:'POST',body:JSON.stringify(body)});
      }
      clearItemForm();
      await loadItems();
      await loadVendors();
    }catch(err){
      alert('Save failed: '+err.message);
    }
  });

  itemCancelBtn.addEventListener('click',()=>clearItemForm());
  itemFilterSelect.addEventListener('change',()=>loadItems());

  await loadVendors();
  await loadItems();
}
