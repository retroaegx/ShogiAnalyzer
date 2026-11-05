import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleUrl } from './browser_modules.mjs';
const {StepOutbox,graceIndicator,previewStep} = await import(moduleUrl('reconnect.js'));
const {sfenAfterMove} = await import(moduleUrl('shogi.js'));
const {DEFAULT_START_SFEN} = await import(moduleUrl('vendor/sfen.js'));
function base() { return {game_id:'g',current_node_id:'root',current_position_sfen:DEFAULT_START_SFEN,
  root_node_id:'root',nodes:[{node_id:'root',parent_id:null,position_sfen:DEFAULT_START_SFEN}],
  children_index:{},current_path_node_ids:['root'],current_path_moves:[],ui_state:{}}; }
function outbox(storage=null) { const q=new StepOutbox(storage,()=>'op'); q.grant(); q.disconnect(); return q; }
test('notice waits three seconds and repeated retries cannot postpone it',()=>{
  let now=0, next=1; const tasks=new Map(), events=[];
  const timers={setTimeout:(fn,ms)=>{const id=next++;tasks.set(id,[now+ms,fn]);return id},clearTimeout:id=>tasks.delete(id)};
  const tick=n=>{now+=n;for(const [id,[at,fn]] of tasks)if(at<=now){tasks.delete(id);fn()}};
  const notice=graceIndicator(()=>events.push('show'),()=>events.push('hide'),3000,timers);
  notice.start();tick(1500);notice.start();tick(1499);assert.deepEqual(events,[]);
  tick(1);assert.deepEqual(events,['show']);notice.stop();tick(5000);assert.deepEqual(events,['show','hide']);
  notice.start();tick(200);notice.stop();tick(3000);assert.equal(events.filter(x=>x==='show').length,1);
});
test('one offline move can be previewed; a second operation is refused',()=>{
  const q=outbox(),game=base();
  const p=q.stage(game,'node:play_move',{from_node_id:'root',move_usi:'7g7f'});
  const preview=previewStep(p,sfenAfterMove(game.current_position_sfen,'7g7f'),'７六歩');
  assert.equal(preview.current_path_moves[0],'7g7f'); assert.equal(game.nodes.length,1);
  assert.equal(q.stage(preview,'node:play_move',{move_usi:'3c3d'}),null);
  assert.equal(q.inspect(game),'replay');assert.equal(q.inspect(preview),'applied');
  q.clear();assert.equal(q.canStep(),true);
});
test('a lost reply does not create a duplicate move',()=>{
  const q=outbox(),game=base();
  const p=q.stage(game,'node:play_move',{from_node_id:'root',move_usi:'7g7f'});
  const accepted=previewStep(p,sfenAfterMove(game.current_position_sfen,'7g7f'),'７六歩');
  accepted.nodes[1].node_id='server-node'; accepted.current_node_id='server-node';
  assert.equal(q.inspect(accepted),'applied');assert.equal(accepted.nodes.length,2);
});
test('another game or current position is a conflict, not an automatic replay',()=>{
  const q=outbox(),game=base();q.stage(game,'node:play_move',{from_node_id:'root',move_usi:'7g7f'});
  assert.equal(q.inspect({...game,game_id:'other'}),'conflict');
  const changed=base();changed.nodes.push({node_id:'other',parent_id:'root',move_usi:'2g2f'});changed.current_node_id='other';
  assert.equal(q.inspect(changed),'conflict');
});
test('a pending step survives reload but a revoked session cannot queue a step',()=>{
  const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const q=outbox(storage);q.stage(base(),'node:play_move',{from_node_id:'root',move_usi:'7g7f'});
  const restored=new StepOutbox(storage);assert.equal(restored.inspect(base()),'replay');
  restored.revoke();assert.equal(restored.stage(base(),'node:jump',{node_id:'root'}),null);assert.equal(values.size,0);
});
test('offline navigation is limited to one adjacent ply',()=>{
  const game=base();game.nodes.push({node_id:'one',parent_id:'root'},{node_id:'two',parent_id:'one'});
  assert.equal(outbox().stage(game,'node:jump',{node_id:'two'}),null);
  assert.ok(outbox().stage(game,'node:jump',{node_id:'one'}));
});
test('provisional moves enforce turn and promotion legality',()=>{
  assert.equal(sfenAfterMove(DEFAULT_START_SFEN,'3c3d'),null);
  assert.equal(sfenAfterMove(DEFAULT_START_SFEN,'7g7f+'),null);
  assert.equal(sfenAfterMove(DEFAULT_START_SFEN,'P*5e'),null);
  assert.equal(sfenAfterMove(DEFAULT_START_SFEN,'7g7f').split(' ')[3],'2');
});
