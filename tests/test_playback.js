const test = require('node:test');
const assert = require('node:assert/strict');
const { seekTime } = require('../app/static/playback.js');

test('seekTime maps a click position to the matching audio time', () => {
  assert.equal(seekTime(25, 0, 400, 120), 7.5);
  assert.equal(seekTime(0, 10, 400, 120), 0);
  assert.equal(seekTime(410, 10, 400, 120), 120);
});

test('seekTime safely handles unusable progress geometry', () => {
  assert.equal(seekTime(100, 10, 0, 120), null);
  assert.equal(seekTime(100, 10, 400, 0), null);
});
