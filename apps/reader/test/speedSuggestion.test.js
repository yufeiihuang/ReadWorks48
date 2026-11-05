import test from 'node:test';
import assert from 'node:assert/strict';
import { SPEED_OPTIONS, loadGradeId, suggestSpeed } from '../src/lib/speedSuggestion.js';

test('offers half speed through grade 4', () => {
  for (const grade of [16, 17, 18, 19, 20]) assert.equal(suggestSpeed(grade).speed, 0.5);
  assert.equal(suggestSpeed(17).question, 'Are you in 1st grade?');
});

test('offers 0.75× for grades 5 to 8', () => {
  for (const grade of [21, 22, 323, 343]) assert.equal(suggestSpeed(grade).speed, 0.75);
  assert.equal(suggestSpeed(21).question, 'Are you in 5th grade?');
});

test('has no suggestion for high school, other levels, or a missing grade', () => {
  for (const grade of [346, 347, 191923, 192000, null, undefined]) assert.equal(suggestSpeed(grade), null);
});

test('every suggestion can be selected in the speed menu', () => {
  for (const grade of [16, 17, 18, 19, 20, 21, 22, 323, 343]) assert.ok(SPEED_OPTIONS.includes(suggestSpeed(grade).speed));
});

test('reads a grade from the passage, or asks the API using the ReadWorks ID', async () => {
  assert.equal(await loadGradeId({ gradeId: 21 }, () => assert.fail('should not fetch')), 21);
  const urls = [];
  const fetcher = async url => { urls.push(url); return { ok: true, json: async () => ({ gradeId: 347 }) }; };
  assert.equal(await loadGradeId({ source: { uuid: 'abc-123' } }, fetcher), 347);
  assert.deepEqual(urls, ['/api/passages/abc-123']);
});

test('the original demo passage counts as 2nd grade without asking the API', async () => {
  const id = await loadGradeId({ id: 'demo' }, () => { throw new Error('no request expected'); });
  assert.equal(id, 18);
  assert.equal(suggestSpeed(id).question, 'Are you in 2nd grade?');
  assert.equal(suggestSpeed(id).speed, 0.5);
});

test('a missing grade never raises an error', async () => {
  const fail = () => assert.fail('should not fetch');
  assert.equal(await loadGradeId({ id: 'pride-and-prejudice' }, fail), null);
  assert.equal(await loadGradeId(null, fail), null);
  assert.equal(await loadGradeId({ source: { uuid: 'x' } }, async () => ({ ok: false })), null);
  assert.equal(await loadGradeId({ source: { uuid: 'x' } }, async () => { throw new Error('offline'); }), null);
  assert.equal(await loadGradeId({ source: { uuid: 'x' } }, async () => ({ ok: true, json: async () => ({}) })), null);
});
