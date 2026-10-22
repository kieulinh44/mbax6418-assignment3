const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/static/app.js'), 'utf8');
const functionSource = source.slice(source.indexOf('function playSet()'), source.indexOf('function seekFromPointer'));

test('Resume retries the current clip without resetting or advancing the queue', async () => {
  let advances = 0;
  let plays = 0;
  const context = {session: {idx: 3, resumePending: true}, els: {playBtn: {}, pauseBtn: {}, deckStatus: {}, player: {paused: true, play: () => { plays++; return Promise.resolve(); }}}, next: () => advances++};
  vm.createContext(context);
  vm.runInContext(functionSource + '\nplaySet();', context);
  assert.equal(context.session.idx, 3);
  assert.equal(advances, 0);
  assert.equal(plays, 1);
});

test('A failed retry leaves another usable Resume action', async () => {
  const context = {session: {idx: 3, resumePending: true}, els: {playBtn: {}, pauseBtn: {}, deckStatus: {}, player: {paused: true, play: () => Promise.reject(Error('blocked'))}}, next: () => assert.fail('must not advance')};
  vm.createContext(context);
  vm.runInContext(functionSource + '\nplaySet();', context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(context.session.resumePending, true);
  assert.equal(context.els.playBtn.hidden, false);
});

const nextSource = source.slice(source.indexOf('function next()'), source.indexOf('function playSetAt'));
test('Skip pauses the current clip before starting the next one and stops at the end', () => {
  const events = [];
  const skip = {};
  const context = {
    session: {idx: 0, resumePending: true, manifest: {playlist: [{audio: '/intro'}, {audio: '/song'}]}},
    els: {player: {pause: () => events.push('pause'), set src(url) { events.push(url); }, play: () => { events.push('play'); return Promise.resolve(); }}, queue: {children: []}, deckStatus: {}, playBtn: {}, pauseBtn: {}, vinyl: {classList: {remove: () => {}}}},
    $: () => skip, setNowPlaying: () => {}, setProgress: () => {}
  };
  vm.createContext(context);
  vm.runInContext(nextSource + '\nnext();', context);
  assert.deepEqual(events, ['pause', '/song', 'play']);
  assert.equal(context.session.resumePending, false);
  assert.equal(skip.disabled, false);
  vm.runInContext('next();', context);
  assert.deepEqual(events, ['pause', '/song', 'play', 'pause']);
  assert.equal(skip.disabled, true);
});
