/* household-hub.html page-specific logic (chores / meals / recipe box / errands) */

const DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
const PREP_TIMES = [
  { key: 'quick', label: 'quick (< 20 min)' },
  { key: 'medium', label: 'medium (20–45 min)' },
  { key: 'slow', label: 'slow / long (45+ min)' },
  { key: '', label: 'uncategorized' }
];
const DEFAULT_STATE = {
  chores: [
    { id: 'c1', name: 'kitchen wipe-down', assignee: '', done: false },
    { id: 'c2', name: 'take out trash/recycling', assignee: '', done: false },
    { id: 'c3', name: 'vacuum common areas', assignee: '', done: false },
    { id: 'c4', name: 'bathroom clean', assignee: '', done: false }
  ],
  meals: {
    mon: { note: '', recipeId: '' }, tue: { note: '', recipeId: '' }, wed: { note: '', recipeId: '' },
    thu: { note: '', recipeId: '' }, fri: { note: '', recipeId: '' }, sat: { note: '', recipeId: '' }, sun: { note: '', recipeId: '' }
  },
  recipes: [],
  errands: []
};
let state = JSON.parse(JSON.stringify(DEFAULT_STATE));
const STORAGE_KEY = 'household-hub-state';

async function loadState() {
  try {
    const result = await window.storage.get(STORAGE_KEY, true);
    if (result && result.value) {
      state = JSON.parse(result.value);
    }
  } catch (e) {
    // no saved state yet, use defaults
  }
}

function migrateState() {
  if (!Array.isArray(state.recipes)) state.recipes = [];
  state.recipes.forEach(r => { if (r.prepTime === undefined) r.prepTime = ''; });
  DAYS.forEach(d => {
    const m = state.meals[d];
    if (typeof m === 'string') {
      state.meals[d] = { note: m, recipeId: '' };
    } else if (!m) {
      state.meals[d] = { note: '', recipeId: '' };
    }
  });

  // roommates used to live inside this same blob; migrate them into the
  // shared roommates store (used across pages) the first time we see them.
  if (Array.isArray(state.roommates) && state.roommates.length > 0 && roommates.length === 0) {
    state.roommates.forEach(name => { if (!roommates.includes(name)) roommates.push(name); });
    saveRoommates();
  }
  if ('roommates' in state) {
    delete state.roommates;
  }
}

async function saveState() {
  try {
    await window.storage.set(STORAGE_KEY, JSON.stringify(state), true);
  } catch (e) {
    console.error('save failed', e);
  }
}

function switchTab(tab) {
  ['chores','meals','errands'].forEach(t => {
    document.getElementById('panel-' + t).style.display = t === tab ? 'block' : 'none';
    document.querySelector(`.tab[data-tab="${t}"]`).classList.toggle('active', t === tab);
  });
}

let editingChoreId = null;

function renderChores() {
  const panel = document.getElementById('panel-chores');
  const cards = state.chores.map(c => `
    <div class="note ${c.done ? 'done' : ''}">
      <div class="tape"></div>
      ${c.id === editingChoreId
        ? `<input class="chore-name-input" value="${escapeAttr(c.name)}" maxlength="40" onblur="saveChoreEdit('${c.id}', this)" onkeydown="handleEditKey(event)">`
        : `<div class="chore-name" title="click to edit" onclick="startEditChore('${c.id}')">${escapeHtml(c.name)}</div>`}
      <div class="note-row">
        <select class="assignee" onchange="setChoreAssignee('${c.id}', this.value)">
          ${assigneeOptions(c.assignee)}
        </select>
        <div>
          <button class="icon-btn check" title="mark done" onclick="toggleChore('${c.id}')">${c.done ? '↺' : '✓'}</button>
          <button class="icon-btn" title="remove" onclick="removeChore('${c.id}')">×</button>
        </div>
      </div>
    </div>
  `).join('');

  panel.innerHTML = `
    <p class="section-title">this week's chores</p>
    <div class="chore-grid">${cards || '<p class="empty-msg">no chores yet — add one below</p>'}</div>
    <div class="add-chore-row">
      <input id="newChore" placeholder="add a chore" maxlength="40" onkeydown="if(event.key==='Enter') addChore()">
      <button class="primary-btn" onclick="addChore()">add</button>
    </div>
    <div class="chore-footer">
      <span class="week-label">week of ${weekLabel()}</span>
      <button class="ghost-btn" onclick="shuffleChores()">shuffle assignments</button>
    </div>
  `;

  if (editingChoreId) {
    const input = panel.querySelector('.chore-name-input');
    if (input) { input.focus(); input.select(); }
  }
}

function weekLabel() {
  const d = new Date();
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function handleEditKey(e) {
  if (e.key === 'Enter') e.target.blur();
  else if (e.key === 'Escape') { e.target.dataset.cancelled = 'true'; e.target.blur(); }
}

function startEditChore(id) {
  editingChoreId = id;
  renderChores();
}

function saveChoreEdit(id, inputEl) {
  editingChoreId = null;
  if (inputEl.dataset.cancelled === 'true') { renderChores(); return; }
  const name = inputEl.value.trim();
  const c = state.chores.find(c => c.id === id);
  if (c && name) c.name = name;
  saveState();
  renderChores();
}

function addChore() {
  const input = document.getElementById('newChore');
  const name = input.value.trim();
  if (!name) return;
  state.chores.push({ id: 'c' + Date.now(), name, assignee: '', done: false });
  saveState();
  renderChores();
}

function removeChore(id) {
  state.chores = state.chores.filter(c => c.id !== id);
  saveState();
  renderChores();
}

function toggleChore(id) {
  const c = state.chores.find(c => c.id === id);
  if (c) c.done = !c.done;
  saveState();
  renderChores();
}

function setChoreAssignee(id, name) {
  const c = state.chores.find(c => c.id === id);
  if (c) c.assignee = name;
  saveState();
}

function shuffleChores() {
  if (roommates.length === 0) return;
  const shuffled = [...roommates].sort(() => Math.random() - 0.5);
  state.chores.forEach((c, i) => {
    c.assignee = shuffled[i % shuffled.length];
    c.done = false;
  });
  saveState();
  renderChores();
}

function recipeOptions(current) {
  let opts = '<option value="">no recipe linked</option>';
  state.recipes.forEach(r => {
    opts += `<option value="${escapeAttr(r.id)}" ${r.id === current ? 'selected' : ''}>${escapeHtml(r.title)}</option>`;
  });
  return opts;
}

function renderMeals() {
  const panel = document.getElementById('panel-meals');
  const cells = DAYS.map(d => `
    <div class="meal-day ${d === 'mon' ? 'meatless' : ''}">
      <div class="day-label">${d}</div>
      <select class="recipe-select" onchange="setDayRecipe('${d}', this.value)">
        ${recipeOptions(state.meals[d].recipeId)}
      </select>
      <textarea placeholder="${d === 'mon' ? 'meatless monday idea' : 'plan a meal'}" onblur="setMeal('${d}', this.value)">${escapeHtml(state.meals[d].note || '')}</textarea>
      ${d === 'mon' ? '<div class="meatless-tag">meatless monday</div>' : ''}
    </div>
  `).join('');

  const recipeSections = PREP_TIMES.map(pt => {
    const items = state.recipes.filter(r => (r.prepTime || '') === pt.key);
    if (items.length === 0) return '';
    const rows = items.map(r => `
      <div class="recipe-item">
        ${r.url
          ? `<a class="recipe-title" href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>`
          : `<span class="recipe-title">${escapeHtml(r.title)}</span>`}
        <button class="icon-btn recipe-remove-btn" title="remove" onclick="removeRecipe('${r.id}')">×</button>
      </div>
    `).join('');
    return `
      <div class="recipe-section">
        <p class="recipe-section-label">${pt.label}</p>
        <div class="recipe-list">${rows}</div>
      </div>
    `;
  }).join('');

  panel.innerHTML = `
    <p class="section-title">this week's meals</p>
    <div class="meal-grid">${cells}</div>
    <p class="meal-hint">tip: Add recipes below and link for each day of the week.</p>

    <div class="recipe-box">
      <p class="section-title">recipe box</p>
      ${recipeSections || '<p class="empty-msg">no recipes saved yet — add one below, then link it to a day above</p>'}
      <div class="add-recipe-row">
        <input id="newRecipeTitle" class="recipe-title-input" placeholder="recipe name" maxlength="60" onkeydown="if(event.key==='Enter') addRecipe()">
        <input id="newRecipeUrl" class="recipe-url-input" placeholder="link (optional)" maxlength="300" onkeydown="if(event.key==='Enter') addRecipe()">
        <select id="newRecipePrepTime" class="prep-time-select">
          ${PREP_TIMES.filter(pt => pt.key).map(pt => `<option value="${pt.key}">${pt.label}</option>`).join('')}
        </select>
        <button class="primary-btn" onclick="addRecipe()">add</button>
      </div>
    </div>
  `;
}

function setMeal(day, value) {
  state.meals[day].note = value;
  saveState();
}

function setDayRecipe(day, recipeId) {
  state.meals[day].recipeId = recipeId;
  saveState();
}

function addRecipe() {
  const titleInput = document.getElementById('newRecipeTitle');
  const urlInput = document.getElementById('newRecipeUrl');
  const prepTimeSelect = document.getElementById('newRecipePrepTime');
  const title = titleInput.value.trim();
  if (!title) return;
  let url = urlInput.value.trim();
  if (url && !/^https?:\/\//i.test(url)) url = 'https://' + url;
  const prepTime = prepTimeSelect.value;
  state.recipes.push({ id: 'r' + Date.now(), title, url, prepTime });
  titleInput.value = '';
  urlInput.value = '';
  saveState();
  renderMeals();
}

async function removeRecipe(id) {
  const recipe = state.recipes.find(r => r.id === id);
  if (!recipe) return;
  const ok = await confirmModal(`Delete "${recipe.title}" from the recipe box? This can't be undone.`);
  if (!ok) return;
  state.recipes = state.recipes.filter(r => r.id !== id);
  DAYS.forEach(d => { if (state.meals[d].recipeId === id) state.meals[d].recipeId = ''; });
  saveState();
  renderMeals();
}

let editingErrandId = null;

function renderErrands() {
  const panel = document.getElementById('panel-errands');
  const items = state.errands.map(e => `
    <div class="errand ${e.done ? 'done' : ''}">
      <button class="icon-btn check" onclick="toggleErrand('${e.id}')">${e.done ? '↺' : '✓'}</button>
      ${e.id === editingErrandId
        ? `<input class="errand-text-input" value="${escapeAttr(e.text)}" maxlength="60" onblur="saveErrandEdit('${e.id}', this)" onkeydown="handleEditKey(event)">`
        : `<span class="errand-text" title="click to edit" onclick="startEditErrand('${e.id}')">${escapeHtml(e.text)}</span>`}
      <select class="assignee" onchange="setErrandAssignee('${e.id}', this.value)">
        ${assigneeOptions(e.assignee)}
      </select>
      <button class="icon-btn" onclick="removeErrand('${e.id}')">×</button>
    </div>
  `).join('');

  panel.innerHTML = `
    <p class="section-title">errands & to-dos</p>
    <div class="errand-list">${items || '<p class="empty-msg">no errands yet — add one below</p>'}</div>
    <div class="add-errand-row">
      <input id="newErrand" placeholder="add an errand" maxlength="60" onkeydown="if(event.key==='Enter') addErrand()">
      <button class="primary-btn" onclick="addErrand()">add</button>
    </div>
  `;

  if (editingErrandId) {
    const input = panel.querySelector('.errand-text-input');
    if (input) { input.focus(); input.select(); }
  }
}

function startEditErrand(id) {
  editingErrandId = id;
  renderErrands();
}

function saveErrandEdit(id, inputEl) {
  editingErrandId = null;
  if (inputEl.dataset.cancelled === 'true') { renderErrands(); return; }
  const text = inputEl.value.trim();
  const e = state.errands.find(e => e.id === id);
  if (e && text) e.text = text;
  saveState();
  renderErrands();
}

function addErrand() {
  const input = document.getElementById('newErrand');
  const text = input.value.trim();
  if (!text) return;
  state.errands.push({ id: 'e' + Date.now(), text, assignee: '', done: false });
  saveState();
  renderErrands();
}

function removeErrand(id) {
  state.errands = state.errands.filter(e => e.id !== id);
  saveState();
  renderErrands();
}

function toggleErrand(id) {
  const e = state.errands.find(e => e.id === id);
  if (e) e.done = !e.done;
  saveState();
  renderErrands();
}

function setErrandAssignee(id, name) {
  const e = state.errands.find(e => e.id === id);
  if (e) e.assignee = name;
  saveState();
}

function render() {
  renderRoommates();
  renderChores();
  renderMeals();
  renderErrands();
}

document.addEventListener('roommate-removed', e => {
  const name = e.detail.name;
  state.chores.forEach(c => { if (c.assignee === name) c.assignee = ''; });
  state.errands.forEach(er => { if (er.assignee === name) er.assignee = ''; });
  saveState();
  renderChores();
  renderErrands();
});

document.addEventListener('roommates-changed', () => {
  renderChores();
  renderErrands();
});

async function init() {
  await Promise.all([initShared(), loadState()]);
  const hadLegacyRoommates = 'roommates' in state;
  migrateState();
  if (hadLegacyRoommates) saveState();
  render();
}

init();
