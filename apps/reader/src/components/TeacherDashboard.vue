<script setup>
import { computed, nextTick, ref } from 'vue';
const passages = [
  { id: 'demo', wordCount: '49', title: 'A Morning in the Garden', detail: 'A short story about discovery · 49 words' },
  { id: 'park-caretaker-qa', wordCount: '360', title: "Let’s Meet a Park Caretaker", detail: 'Community and nature · 360 words' },
  { id: 'pride-and-prejudice', wordCount: '1,156', title: 'Excerpt from Pride and Prejudice', detail: 'Classic literature · Jane Austen · 1,156 words' },
];
function read(key, fallback) { try { const value = JSON.parse(localStorage.getItem(key)); return Array.isArray(value) ? value : fallback; } catch { return fallback; } }
const roster = ref(read('soundworks.roster', ['Alex', 'Jordan', 'Sam', 'Taylor']));
const assignments = ref(read('soundworks.assignments', []));
const selected = ref([]);
const passage = ref(new URLSearchParams(location.search).get('passage') || '');
if (!passages.some(p => p.id === passage.value)) passage.value = '';
const search = ref(passages.find(p => p.id === passage.value)?.title || '');
const searching = ref(!passage.value);
const searchInput = ref(null);
const changeButton = ref(null);
const selectedReading = computed(() => passages.find(p => p.id === passage.value));
function changeReading() { search.value = ''; searching.value = true; nextTick(() => searchInput.value?.focus()); }
const readingResults = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return passages.filter(p => !query || p.title.toLocaleLowerCase().includes(query) || p.detail.toLocaleLowerCase().includes(query));
});
function searchReadings() { passage.value = ''; searching.value = true; }
function selectReading(reading) { passage.value = reading.id; search.value = reading.title; searching.value = false; nextTick(() => changeButton.value?.focus()); }
const audio = ref(true);
const due = ref('');
const name = ref('');
const status = ref('');
const error = ref('');
const allSelected = computed(() => roster.value.length > 0 && selected.value.length === roster.value.length);
function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { error.value = 'Your browser could not save this change. Check storage settings and try again.'; return false; } }
function addStudent() {
  const value = name.value.trim();
  if (!value || roster.value.some(n => n.toLowerCase() === value.toLowerCase())) return;
  const next = [...roster.value, value];
  if (save('soundworks.roster', next)) { roster.value = next; name.value = ''; }
}
function assign() {
  error.value = ''; status.value = '';
  if (!passage.value) { error.value = 'Choose a reading from the search results.'; return; }
  if (!selected.value.length) { error.value = 'Choose at least one student.'; return; }
  const item = { id: crypto.randomUUID(), passage: passage.value, students: [...selected.value], audio: audio.value, due: due.value, created: new Date().toISOString() };
  const next = [item, ...assignments.value];
  if (save('soundworks.assignments', next)) { assignments.value = next; status.value = `Assigned to ${item.students.length} student${item.students.length === 1 ? '' : 's'}. Share the reading link below.`; selected.value = []; }
}
function link(item) {
  const url = new URL(location.pathname, location.origin);
  url.searchParams.set('passage', item.passage);
  url.searchParams.set('audio', item.audio ? 'on' : 'off');
  return url.href;
}
async function copy(item) { try { await navigator.clipboard.writeText(link(item)); status.value = 'Reading link copied.'; } catch { error.value = 'Could not copy. Open the reading and copy its address instead.'; } }
function remove(item) { const next = assignments.value.filter(a => a.id !== item.id); if (save('soundworks.assignments', next)) assignments.value = next; }
const title = id => passages.find(p => p.id === id)?.title || id;
</script>
<template>
  <header class="site-header"><a class="brand" href="/">Read<span>Works</span><sup>®</sup></a><nav class="teacher-nav"><span>Teacher dashboard</span><a href="/">Open reader ↗</a></nav></header>
  <main class="teacher-page">
    <section class="teacher-intro"><h1>Assignments</h1></section>
    <div class="teacher-grid">
      <form class="teacher-card assignment-form" @submit.prevent="assign">
        <h2>Create an assignment</h2>
        <fieldset><legend><span class="step">1</span> Choose a reading</legend>
          <div v-if="selectedReading && !searching" class="chosen-reading"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg><div><span class="chosen-label">Selected reading</span><strong>{{ selectedReading.title }}</strong><small>{{ selectedReading.wordCount }} words</small></div><button ref="changeButton" type="button" @click="changeReading">Change</button></div>
          <div v-else class="reading-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><input ref="searchInput" type="search" aria-label="Search readings" placeholder="Search by title or author" v-model="search" @input="searchReadings" @focus="searching = true" @keydown.esc="searching = false" autocomplete="off" aria-controls="reading-results"></div>
          <div v-if="searching" id="reading-results" class="reading-results"><button v-for="reading in readingResults" :key="reading.id" type="button" @click="selectReading(reading)"><strong>{{ reading.title }}</strong><small>{{ reading.detail }}</small><span v-if="passage === reading.id" class="selected-reading">Selected</span></button><p v-if="!readingResults.length" role="status">No readings found. Try another title or author.</p></div>
        </fieldset>
        <fieldset><legend><span class="step">2</span> Set reading support</legend><div class="support-options"><label :class="{ chosen: audio }"><input type="radio" name="support" :value="true" v-model="audio"><strong>With audio</strong><span>Listen, follow highlighting, and replay words.</span></label><label :class="{ chosen: !audio }"><input type="radio" name="support" :value="false" v-model="audio"><strong>Without audio</strong><span>Read independently with text and display settings.</span></label></div></fieldset>
        <fieldset><legend><span class="step">3</span> Choose students</legend><label class="select-all"><input type="checkbox" :checked="allSelected" @change="selected = allSelected ? [] : [...roster]"> Select all <span>{{ selected.length }} selected</span></label><div class="student-grid"><label v-for="student in roster" :key="student"><input type="checkbox" :value="student" v-model="selected"><span class="avatar">{{ student.slice(0,1).toUpperCase() }}</span>{{ student }}</label></div><div class="add-student"><input aria-label="Student name" maxlength="60" placeholder="Add a student name" v-model="name" @keydown.enter.prevent="addStudent"><button type="button" @click="addStudent" :disabled="!name.trim()">Add student</button></div></fieldset>
        <label class="due-date">Due date <span>(optional)</span><input type="date" v-model="due"></label>
        <p v-if="error" role="alert" class="teacher-error">{{ error }}</p><button class="assign-primary" type="submit">Assign reading <span>→</span></button>
      </form>
      <aside class="teacher-card assignment-summary"><h2>Your classroom</h2><div class="class-stats"><div><strong>{{ roster.length }}</strong><span>Students</span></div><div><strong>{{ assignments.length }}</strong><span>Assignments</span></div></div><hr><p>Audio can be turned on or off for each assignment. Text size and font settings are always available.</p></aside>
    </div>
    <section class="assignment-list"><div class="list-heading"><h2>Assigned readings</h2><span>{{ assignments.length }} total</span></div><p role="status" class="teacher-success" v-if="status">{{ status }}</p><div v-if="!assignments.length" class="empty-assignments"><h3>No assignments yet.</h3><p>Assigned readings will appear here.</p></div><article class="assignment-row" v-for="item in assignments" :key="item.id"><div><span class="audio-badge">{{ item.audio ? 'With audio' : 'Without audio' }}</span><h3>{{ title(item.passage) }}</h3><p>{{ item.students.join(', ') }}</p><small v-if="item.due">Due {{ item.due }}</small></div><div class="assignment-actions"><a :href="link(item)" target="_blank" rel="noopener">Open reading ↗</a><button @click="copy(item)">Copy link</button><button class="remove-assignment" @click="remove(item)" :aria-label="`Remove assignment: ${title(item.passage)}`">Remove</button></div></article></section>
  </main>
</template>
<style scoped>
.teacher-nav{display:flex;gap:24px;align-items:center;font-size:14px}.teacher-nav span{color:#687983}.teacher-nav a,a{color:#276f83}.teacher-page{background:#f5f7f7;min-height:100vh;padding:42px max(24px,calc((100vw - 1122px)/2)) 70px}.teacher-intro h1{font-size:36px;letter-spacing:-1px;margin:12px 0}.teacher-intro p{color:#64747d;line-height:1.6}.eyebrow{font-size:11px;font-weight:700;letter-spacing:1.8px;color:#347b91}.demo-notice{font-size:12px;line-height:1.6;color:#667780;margin:26px 0}.teacher-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:24px;align-items:start}.teacher-card{background:white;border:1px solid #e0e7e9;border-radius:12px;padding:28px}.teacher-card h2,.list-heading h2{font-size:21px;margin:0 0 24px}.assignment-form fieldset{border:0;padding:0;margin:0 0 28px;min-width:0}.assignment-form legend{font-size:15px;font-weight:650;margin-bottom:16px}.step{display:inline-grid;place-items:center;width:24px;height:24px;background:#edf5f7;color:#347b91;border-radius:50%;font-size:12px;margin-right:8px}.reading-option{display:flex;gap:12px;padding:15px;border:1px solid #dce4e7;border-radius:8px;margin:9px 0;align-items:center;cursor:pointer}.reading-option strong{display:block;font-size:14px}.reading-option small{display:block;color:#74818a;font-size:12px;margin-top:6px}.chosen{border-color:#347b91!important;background:#f0f7f9}.teacher-page input[type=checkbox],.teacher-page input[type=radio]{accent-color:#347b91;width:17px;height:17px;flex-shrink:0}.support-options{display:grid;grid-template-columns:1fr 1fr;gap:12px}.support-options label{display:grid;grid-template-columns:20px 1fr;gap:8px;border:1px solid #dce4e7;border-radius:8px;padding:16px;cursor:pointer}.support-options strong{font-size:14px}.support-options span{grid-column:2;font-size:12px;color:#64747d;line-height:1.6}.select-all{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:16px}.select-all span{margin-left:auto;color:#71818a}.student-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.student-grid label{display:flex;gap:9px;align-items:center;font-size:14px;padding:10px;background:#fafbfb;border-radius:6px;overflow-wrap:anywhere}.avatar{display:grid;place-items:center;background:#e6eff2;color:#347b91;border-radius:50%;width:30px;height:30px;flex-shrink:0;font-size:12px}.add-student{display:flex;gap:8px;margin-top:14px}.teacher-page input:not([type=checkbox]):not([type=radio]){border:1px solid #d9e1e4;border-radius:6px;padding:10px;min-width:0;width:100%;font-size:13px}.teacher-page button,.assignment-actions a{border:1px solid #cddce1;background:white;border-radius:6px;padding:10px 14px;color:#286c80;font-size:13px;text-decoration:none}.add-student button{white-space:nowrap}.due-date{display:block;font-size:13px}.due-date span{color:#77868d}.due-date input{display:block;margin:8px 0 22px;max-width:230px}.teacher-page .assign-primary{background:#347b91;color:white;border:0;width:100%;display:flex;justify-content:space-between;padding:15px 18px;font-weight:600}.class-stats{display:flex;gap:40px;margin:22px 0}.class-stats strong{font-size:32px;display:block}.class-stats span{display:block;color:#74818a;font-size:12px;margin-top:6px}.assignment-summary hr{border:0;border-top:1px solid #e5ebed;margin:26px 0}.assignment-summary h3{font-size:15px}.assignment-summary p{font-size:13px;line-height:1.8;color:#687983}.assignment-summary small{font-size:11px;line-height:1.8;color:#7b898f;display:block;margin-top:24px}.assignment-list{margin-top:40px}.list-heading{display:flex;justify-content:space-between;align-items:baseline}.list-heading span{color:#71818a;font-size:13px}.empty-assignments{padding:40px;text-align:center;border:1px dashed #ccd9de;border-radius:12px}.empty-assignments h3{font-size:17px}.empty-assignments p{font-size:13px;color:#71818a}.assignment-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:24px;background:white;border:1px solid #e0e7e9;border-radius:10px;margin-bottom:12px}.assignment-row h3{font-size:17px;margin:10px 0}.assignment-row p,.assignment-row small{font-size:13px;color:#71818a;overflow-wrap:anywhere}.audio-badge{font-size:11px;color:#286c80;background:#edf5f7;padding:4px 8px;border-radius:4px}.assignment-actions{display:flex;gap:8px;flex-wrap:wrap}.teacher-page .remove-assignment{border:0;color:#75818a}.teacher-success{color:#246c54;font-size:14px}.teacher-error{color:#a43434;font-size:14px}@media(max-width:800px){.teacher-grid{grid-template-columns:1fr}.assignment-summary{display:none}.teacher-intro h1{font-size:29px}.teacher-card{padding:20px}.assignment-row{align-items:flex-start;flex-direction:column}.teacher-nav span{display:none}}@media(max-width:450px){.support-options,.student-grid{grid-template-columns:1fr}.teacher-page{padding:28px 16px}.teacher-nav{font-size:12px}}
.reading-search{display:flex;align-items:center;gap:10px;border:1px solid #cddce1;border-radius:7px;padding:0 12px;background:white}.reading-search:focus-within{outline:2px solid #347b91;outline-offset:2px}.reading-search svg{width:18px;height:18px;color:#71818a;flex-shrink:0}.teacher-page .reading-search input{border:0!important;padding:13px 0!important;outline:none}.reading-results{border:1px solid #dce4e7;border-radius:7px;margin-top:8px;overflow:hidden}.teacher-page .reading-results button{display:block;position:relative;width:100%;border:0;border-bottom:1px solid #edf1f2;border-radius:0;text-align:left;padding:14px 16px;color:#344048}.reading-results button:last-child{border-bottom:0}.reading-results button:hover,.reading-results button:focus-visible{background:#edf5f7}.reading-results strong{display:block;font-size:14px}.reading-results small{display:block;color:#71818a;font-size:12px;margin-top:5px}.selected-reading{position:absolute;right:14px;top:15px;font-size:11px;color:#347b91}.reading-results p{font-size:13px;color:#71818a;padding:8px 16px}
.chosen-reading{display:flex;align-items:center;gap:14px;padding:17px;border:1px solid #b9d1d9;background:#f0f7f9;border-radius:8px}.chosen-reading>svg{color:#347b91;flex-shrink:0;width:21px;height:21px}.chosen-reading>div{flex:1;min-width:0}.chosen-label{display:block;font-size:11px;color:#527886;margin-bottom:6px}.chosen-reading strong{display:block;font-size:15px;line-height:1.4}.chosen-reading small{display:block;color:#71818a;font-size:12px;margin-top:5px}.teacher-page .chosen-reading button{flex-shrink:0;background:transparent}
</style>
