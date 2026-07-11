/* Shared utilities + roommate state — loaded by every page (household hub, and future pages) */

const COLORS = ['#D8A31A','#C0532D','#6F8F63','#5C7EA8','#A45D8C','#8A6D3B'];
const ROOMMATES_STORAGE_KEY = 'household-hub-roommates';
const ADD_ROOMMATE_VISIBLE_KEY = 'household-hub-show-add-roommate';

let roommates = [];
let addRoommateVisibleFallback = false;

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeAttr(s) { return s.replace(/'/g, "\\'"); }

function colorFor(name) {
  if (!name) return '#B4B2A9';
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return COLORS[Math.abs(hash) % COLORS.length];
}

async function loadRoommates() {
  try {
    const result = await window.storage.get(ROOMMATES_STORAGE_KEY, true);
    if (result && result.value) roommates = JSON.parse(result.value);
  } catch (e) {
    // no saved roommates yet, use defaults
  }
}

async function saveRoommates() {
  try {
    await window.storage.set(ROOMMATES_STORAGE_KEY, JSON.stringify(roommates), true);
  } catch (e) {
    console.error('save failed', e);
  }
}

function renderRoommates() {
  const strip = document.getElementById('roommatesStrip');
  if (!strip) return;
  if (roommates.length === 0) {
    strip.innerHTML = '<span style="color: var(--kraft-dark); font-size: 13px;">no roommates added yet</span>';
    return;
  }
  strip.innerHTML = roommates.map(name => `
    <div class="roommate-chip">
      <span class="dot" style="background:${colorFor(name)}"></span>
      ${escapeHtml(name)}
      <button aria-label="remove ${escapeHtml(name)}" onclick="removeRoommate('${escapeAttr(name)}')">×</button>
    </div>
  `).join('');
}

function addRoommate() {
  const input = document.getElementById('newRoommate');
  const name = input.value.trim();
  if (!name) return;
  if (roommates.includes(name)) { input.value = ''; return; }
  roommates.push(name);
  input.value = '';
  saveRoommates();
  renderRoommates();
  document.dispatchEvent(new CustomEvent('roommates-changed', { detail: { roommates } }));
}

function removeRoommate(name) {
  roommates = roommates.filter(r => r !== name);
  saveRoommates();
  renderRoommates();
  document.dispatchEvent(new CustomEvent('roommate-removed', { detail: { name } }));
}

function assigneeOptions(current) {
  let opts = '<option value="">unassigned</option>';
  roommates.forEach(r => {
    opts += `<option value="${escapeAttr(r)}" ${r === current ? 'selected' : ''}>${escapeHtml(r)}</option>`;
  });
  return opts;
}

function isAddRoommateVisible() {
  try {
    return localStorage.getItem(ADD_ROOMMATE_VISIBLE_KEY) === 'true';
  } catch (e) {
    return addRoommateVisibleFallback;
  }
}

function toggleAddRoommate() {
  const next = !isAddRoommateVisible();
  try {
    localStorage.setItem(ADD_ROOMMATE_VISIBLE_KEY, String(next));
  } catch (e) {
    addRoommateVisibleFallback = next;
  }
  applyAddRoommateVisibility();
}

function applyAddRoommateVisibility() {
  const visible = isAddRoommateVisible();
  const row = document.getElementById('addRoommateRow');
  const btn = document.getElementById('roommateToggleBtn');
  if (row) row.style.display = visible ? 'flex' : 'none';
  if (btn) btn.textContent = visible ? '− hide add roommate' : '+ manage roommates';
}

/* Confirm modal — auto-injected so pages don't need to hand-copy its markup */
const CONFIRM_MODAL_HTML = `
<div class="modal-overlay" id="confirmModal">
  <div class="modal-box">
    <div class="tape"></div>
    <p class="modal-title" id="confirmModalTitle">are you sure?</p>
    <p class="modal-message" id="confirmModalMessage"></p>
    <div class="modal-actions">
      <button class="ghost-btn" id="confirmModalCancel">cancel</button>
      <button class="danger-btn" id="confirmModalOk">delete</button>
    </div>
  </div>
</div>`;

function ensureConfirmModal() {
  if (!document.getElementById('confirmModal')) {
    document.body.insertAdjacentHTML('beforeend', CONFIRM_MODAL_HTML);
  }
}

function confirmModal(message) {
  ensureConfirmModal();
  return new Promise(resolve => {
    const overlay = document.getElementById('confirmModal');
    document.getElementById('confirmModalMessage').textContent = message;
    const okBtn = document.getElementById('confirmModalOk');
    const cancelBtn = document.getElementById('confirmModalCancel');

    const close = result => {
      overlay.classList.remove('open');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      overlay.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    };
    const onOk = () => close(true);
    const onCancel = () => close(false);
    const onOverlay = e => { if (e.target === overlay) close(false); };
    const onKey = e => { if (e.key === 'Escape') close(false); };

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
    overlay.classList.add('open');
  });
}

/* Call once per page after the roommate strip / toggle markup is in the DOM */
async function initShared() {
  ensureConfirmModal();
  try {
    applyAddRoommateVisibility();
  } catch (e) {
    console.error('roommate toggle init failed', e);
  }
  const newRoommateInput = document.getElementById('newRoommate');
  if (newRoommateInput) {
    newRoommateInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') addRoommate();
    });
  }
  await loadRoommates();
}
