import test from 'node:test';
import assert from 'node:assert/strict';
import { moduleUrl } from './browser_modules.mjs';

const { coalesceFrame } = await import(moduleUrl('render_schedule.js'));
test('many telemetry updates paint the latest state once per frame', () => {
  const queue=[];
  let latest=0;
  const painted=[];
  const schedule=coalesceFrame(()=>painted.push(latest), callback=>queue.push(callback));
  for (let i=1;i<=100;i++) { latest=i; schedule(); }
  assert.equal(queue.length,1);
  queue.shift()();
  assert.deepEqual(painted,[100]);
  latest=101; schedule(); queue.shift()();
  assert.deepEqual(painted,[100,101]);
});
