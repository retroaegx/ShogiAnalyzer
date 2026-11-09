import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../server/assets_web/js/app.js',import.meta.url),'utf8');
function renderer(name) {
  const start=source.indexOf(`function ${name}(`);
  assert.ok(start>=0);
  return source.slice(start,source.indexOf('\n}',start)+2);
}
function element(kind,classes='',text='') {
  const classesSet=new Set(classes.split(' ').filter(Boolean));
  return {kind,textContent:text,dataset:{},children:[],events:{},classList:{add:value=>classesSet.add(value),contains:value=>classesSet.has(value)},
    appendChild(child){this.children.push(child);},setAttribute(){},addEventListener(name,fn){this.events[name]=fn;},
    set innerHTML(value){this.children=[];}};
}
function fixture(line=['root','one','two','three']) {
  const nodes={root:{id:'root',parent_id:null},one:{id:'one',parent_id:'root'},two:{id:'two',parent_id:'one'},
    three:{id:'three',parent_id:'two'},firstAlt:{id:'firstAlt',parent_id:'root'},alt:{id:'alt',parent_id:'two'},alt2:{id:'alt2',parent_id:'two'}};
  for (const n of Object.values(nodes)) n.node_id=n.id;
  const state={mainLine:line,isOwner:true,game:{current_node_id:'two',children_index:{root:['one','firstAlt'],one:['two'],two:['three','alt','alt2'],three:[]}}};
  const list=element('list'); const jumped=[];
  const context={state,els:{moveList:list,kifuSub:{},varChips:element('chips'),variations:{},varTitle:{}},node:id=>nodes[id],children:id=>(state.game.children_index[id]||[]).map(id=>nodes[id]),
    el:element,icon:kind=>element(kind),nodeLabel:n=>n.id,updateMoveEvals(){},keepCurrentMoveVisible(){},jump(id){jumped.push(id);state.game.current_node_id=id;context.renderVariations();}};
  vm.createContext(context);
  vm.runInContext(renderer('renderMoveList')+'\n'+renderer('drawGraphBranches')+'\n'+renderer('renderVariations'),context);
  return {context,state,list,jumped};
}
function pins(context) {
  const result=[]; const gradient={addColorStop(){}};
  const ctx=new Proxy({arc(x,y,r){if(r>3)result.push(x);},measureText(){return {width:20};},
    createLinearGradient(){return gradient;},createRadialGradient(){return gradient;}},{get(target,key){return target[key]||(()=>{});}});
  context.drawGraphBranches(ctx,{compact:false,x0:40,x:i=>40+i*100,y:()=>100,pts:[],padY:0,yBottom:200,axisTop:220,fs:14,font:'14px sans-serif',
    pal:{pin:'#fc0',up:'200,180,0',cur:'#fff',pinLit:'#440',discTop:'#330',discBottom:'#110',pinInk:'#000'}});
  return result;
}

test('move-list branch markers select the position offering the next-move choices, including the root',()=>{
  const {context,list,jumped,state}=fixture();context.renderMoveList();
  const marked=list.children.filter(row=>row.children.some(child=>child.classList.contains('mv-branch')));
  assert.deepEqual(marked.map(row=>row.dataset.id),['root','two']);
  marked[1].events.click();
  assert.deepEqual(jumped,['two']);
  assert.deepEqual(state.game.children_index[jumped[0]],['three','alt','alt2']);
  assert.equal(context.els.variations.hidden,false);
  assert.equal(context.els.varTitle.textContent,'次の一手の変化');
  assert.deepEqual(context.els.varChips.children.map(button=>button.textContent),['three','alt','alt2']);
  context.els.varChips.children[1].events.click();
  assert.deepEqual(jumped,['two','alt']);
});
test('graph branch pins align with parent positions rather than the first move of each variation',()=>{
  assert.deepEqual(pins(fixture().context),[40,240]);
});
test('a truncated line still marks root choices, while a single continuation has no branch marker',()=>{
  const {context,state,list}=fixture(['root']);
  context.renderMoveList();
  assert.ok(list.children[0].children.some(child=>child.classList.contains('mv-branch')));
  assert.deepEqual(pins(context),[40]);
  state.game.children_index.root=['one'];context.renderMoveList();
  assert.ok(!list.children[0].children.some(child=>child.classList.contains('mv-branch')));
  assert.deepEqual(pins(context),[]);
});
