const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/static/app.js'), 'utf8');

// Slices cover the merged playback flow: onPlayBtnClick/showResume/playAudio/playSet
// (resume semantics) and next() (advance / end of set).
const resumeSource = source.slice(source.indexOf('function onPlayBtnClick'), source.indexOf('function onEnded'));
// next() calls playAudio(), which is defined before it in the file.
const nextSource = source.slice(source.indexOf('function playAudio'), source.indexOf('function jumpTo'));

test('Resume retries the current clip without resetting or advancing the queue', () => {
  let advances = 0;
  let plays = 0;
  const context = {
    resumeMode: true,
    playbackAttempt: 0,
    session: {idx: 3, manifest: {playlist: [{}, {}]}},
    els: {player: {paused: true, play: () => { plays++; return Promise.resolve(); }},
          playBtn: {}, pauseBtn: {}, deckStatus: {}, vinyl: {classList: {remove: () => {}}}},
    next: () => advances++,
    updateTransport: () => {},
  };
  vm.createContext(context);
  vm.runInContext(resumeSource + '\nonPlayBtnClick();', context);
  assert.equal(context.session.idx, 3, 'queue must not advance');
  assert.equal(advances, 0, 'next() must not be called');
  assert.equal(plays, 1, 'current clip must be retried');
  assert.equal(context.resumeMode, false, 'resume mode cleared after a successful play');
});

test('A failed retry leaves another usable Resume action', async () => {
  const context = {
    resumeMode: true,
    playbackAttempt: 0,
    session: {idx: 3, manifest: {playlist: [{}, {}]}},
    els: {player: {paused: true, play: () => Promise.reject(Error('blocked'))},
          playBtn: {}, pauseBtn: {textContent: '', setAttribute: () => {}}, deckStatus: {}, vinyl: {classList: {remove: () => {}}}},
    next: () => assert.fail('must not advance'),
    updateTransport: () => {},
  };
  vm.createContext(context);
  vm.runInContext(resumeSource + '\nonPlayBtnClick();', context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(context.resumeMode, true, 'resume action must remain available');
  assert.equal(context.els.pauseBtn.textContent, '▶ Resume');
});

test('next() advances the set and stops cleanly at the end', () => {
  const events = [];
  const context = {
    session: {idx: 0, manifest: {playlist: [{audio: '/intro'}, {audio: '/song'}]}},
    els: {
      player: {play: () => { events.push('play'); return Promise.resolve(); }, set src(v) { events.push('src:' + v); }},
      queue: {children: []},
      deckStatus: {}, pauseBtn: {}, playBtn: {}, vinyl: {classList: {remove: () => {}}},
      seekDot: {}, progressTrack: {setAttribute: () => {}, style: {setProperty: () => {}}}, nextBtn: {},
    },
    playbackAttempt: 0,
    setNowPlaying: () => {}, setProgress: () => {}, updateTransport: () => {},
    resetPlaybackProgress: () => {},
  };
  vm.createContext(context);
  vm.runInContext(nextSource + '\nnext();', context);
  assert.deepEqual(events, ['src:/song', 'play'], 'advance to the next clip');
  assert.equal(context.session.idx, 1);
  vm.runInContext('next();', context);
  assert.equal(context.els.deckStatus.textContent, 'Set finished — thanks for listening!');
  assert.equal(context.session.idx, 1, 'must not advance past the end');
});
