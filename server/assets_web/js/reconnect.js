// One unacknowledged board operation, independent of the WebSocket and the DOM.
export class StepOutbox {
  constructor(storage = null, makeId = () => crypto.randomUUID()) {
    this.storage = storage;
    this.makeId = makeId;
    this.ready = false;
    this.wasOwner = false;
    this.pending = null;
    try {
      const saved = JSON.parse(storage?.getItem('shogi_pending_step') || 'null');
      if (saved?.base?.game_id && saved?.payload?.operation_id && ['node:jump','node:play_move'].includes(saved.type)) {
        this.pending = saved;
        this.wasOwner = true;
      }
    } catch {}
  }
  persist() {
    try {
      if (this.pending) this.storage?.setItem('shogi_pending_step', JSON.stringify(this.pending));
      else this.storage?.removeItem('shogi_pending_step');
    } catch {}
  }
  disconnect() { this.ready = false; }
  grant() { this.ready = true; this.wasOwner = true; }
  clear() { this.pending = null; this.persist(); }
  revoke() { this.ready = false; this.wasOwner = false; this.clear(); }
  canStep() { return this.wasOwner && !this.pending; }
  stage(game, type, payload) {
    if (!this.canStep() || !game?.current_node_id || !['node:jump','node:play_move'].includes(type)) return null;
    const from = game.current_node_id;
    const nodes = new Map(game.nodes.map(n => [n.node_id,n]));
    if (!this.ready && type === 'node:jump') {
      const target = nodes.get(payload.node_id);
      if (!target || (target.parent_id !== from && nodes.get(from)?.parent_id !== target.node_id)) return null;
    }
    this.pending = {
      type, base: structuredClone(game),
      payload: {...payload, operation_id:this.makeId(), expected_game_id:game.game_id,
        expected_node_id:from, expected_sfen:game.current_position_sfen, step_limited:!this.ready},
    };
    this.persist();
    return this.pending;
  }
  inspect(game) {
    const p = this.pending;
    if (!p) return 'none';
    if (game?.game_id !== p.base.game_id) return 'conflict';
    const current = game.nodes.find(n => n.node_id === game.current_node_id);
    if (p.type === 'node:jump' && current?.node_id === p.payload.node_id) return 'applied';
    if (p.type === 'node:play_move' && current?.parent_id === p.payload.expected_node_id && current.move_usi === p.payload.move_usi) return 'applied';
    if (current?.node_id === p.payload.expected_node_id && current.position_sfen === p.payload.expected_sfen) return 'replay';
    return 'conflict';
  }
}

// Repeated connection attempts must not restart the three-second grace period.
export function graceIndicator(show, hide, delay = 3000, timers = globalThis) {
  let timer = null;
  let active = false;
  return {
    start() {
      if (active) return;
      active = true;
      timer = timers.setTimeout(() => { timer = null; if (active) show(); }, delay);
    },
    stop() {
      active = false;
      if (timer !== null) timers.clearTimeout(timer);
      timer = null;
      hide();
    },
  };
}

export function previewStep(pending, nextSfen, label) {
  const game = structuredClone(pending.base);
  const p = pending.payload;
  let target = game.nodes.find(n => n.node_id === p.node_id);
  if (pending.type === 'node:play_move') {
    target = game.nodes.find(n => n.parent_id === p.expected_node_id && n.move_usi === p.move_usi);
    if (!target) {
      if (!nextSfen) return null;
      target = {node_id:'pending:'+p.operation_id,game_id:game.game_id,parent_id:p.expected_node_id,
        order_index:(game.children_index[p.expected_node_id] || []).length, move_usi:p.move_usi,
        move_label:label,comment:'',position_sfen:nextSfen,created_at:new Date().toISOString()};
      game.nodes.push(target);
      (game.children_index[p.expected_node_id] ||= []).push(target.node_id);
      game.dirty = true;
    }
  }
  if (!target) return null;
  const map = new Map(game.nodes.map(n => [n.node_id,n]));
  const path = [];
  for (let n = target; n; n = map.get(n.parent_id)) path.unshift(n);
  game.current_node_id = target.node_id;
  game.current_position_sfen = target.position_sfen;
  game.current_path_node_ids = path.map(n => n.node_id);
  game.current_path_moves = path.map(n => n.move_usi).filter(Boolean);
  return game;
}
