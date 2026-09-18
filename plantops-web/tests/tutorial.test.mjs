import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

// Test the exact pure TypeScript policy used by React, with the existing compiler.
const source = readFileSync(new URL('../src/tutorial/state.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ES2022}}).outputText;
const policy = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const snapshot = () => ({session_id:'one', scenario_profile:{id:'tutorial-v1'}, action_log:[], summary:{simulated_minutes:0, shift_minutes:60, machine_metrics:{laser_01:{processed:0, state:'IDLE', service:{pending:false, active:false}}}}});

test('navigation and reading precede action observation; no clock-only success', () => {
 const s=snapshot(), p=policy.emptyProgress('one');
 assert.equal(policy.tutorialStep(s,p),1);
 p.handoverRead=true; assert.equal(policy.tutorialStep(s,p),2);
 p.plantVisited=true; assert.equal(policy.tutorialStep(s,p),3);
 p.assetInspected=true; assert.equal(policy.tutorialStep(s,p),4);
 s.action_log.push({machine_id:'laser_01',kind:'EQUIPMENT_SERVICE_REQUESTED'});
 assert.equal(policy.tutorialStep(s,p),5);
 s.summary.simulated_minutes=20;
 assert.equal(policy.tutorialStep(s,p),5);
 s.summary.machine_metrics.laser_01.processed=5;
 s.summary.machine_metrics.laser_01.service.active=true;
 assert.equal(policy.tutorialStep(s,p),5);
 s.summary.machine_metrics.laser_01.service.active=false;
 assert.equal(policy.tutorialStep(s,p),6);
 p.reviewed=true; assert.equal(policy.tutorialStep(s,p),7);
});
test('run-first, late service and closed shift all permit outcome review', () => {
 const s=snapshot(), p={...policy.emptyProgress('one'),handoverRead:true,plantVisited:true,assetInspected:true,runFirst:true};
 assert.equal(policy.tutorialStep(s,p),5);
 s.summary.simulated_minutes=20; s.summary.machine_metrics.laser_01.processed=4;
 assert.equal(policy.tutorialStep(s,p),6);
 s.summary.machine_metrics.laser_01.service.pending=true;
 assert.equal(policy.tutorialStep(s,p),5);
 s.summary.simulated_minutes=60;
 assert.equal(policy.tutorialStep(s,p),6);
});
test('normal shifts, other sessions and dismissal never show coaching', () => {
 const s=snapshot(), p=policy.emptyProgress('one');
 p.dismissed=true; assert.equal(policy.tutorialStep(s,p),null);
 p.dismissed=false; s.scenario_profile.id='cnc-wear-v2'; assert.equal(policy.tutorialStep(s,p),null);
 s.scenario_profile.id='tutorial-v1'; p.sessionId='old'; assert.equal(policy.tutorialStep(s,p),null);
});
test('storage denial, malformed records, completion and dismissal persistence are safe', () => {
 globalThis.window={get localStorage(){throw Error('denied');},get sessionStorage(){throw Error('denied');}};
 assert.equal(policy.readStored('localStorage','status'),null);
 assert.doesNotThrow(()=>policy.writeStored('localStorage','status','completed'));
 assert.deepEqual(policy.restoreProgress('one'),policy.emptyProgress('one'));
 const values=new Map(); const store={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 globalThis.window={localStorage:store,sessionStorage:store};
 for(const status of ['completed','dismissed']){policy.writeStored('localStorage','plantops.tutorial.status',status);assert.equal(policy.readStored('localStorage','plantops.tutorial.status'),status);}
 values.set('plantops.tutorial.progress','{broken'); assert.deepEqual(policy.restoreProgress('one'),policy.emptyProgress('one'));
 const p={...policy.emptyProgress('one'),handoverRead:true,plantVisited:true};
 values.set('plantops.tutorial.progress',JSON.stringify(p)); assert.deepEqual(policy.restoreProgress('one'),p);
 assert.deepEqual(policy.restoreProgress('new'),policy.emptyProgress('new'));
});
test('step projection never mutates snapshots or invents random outcomes',()=>{
 const s=snapshot(), original=JSON.stringify(s);
 policy.tutorialStep(s,policy.emptyProgress('one')); assert.equal(JSON.stringify(s),original);
 assert.ok(!source.includes('Math.random'));
 const coach=readFileSync(new URL('../src/tutorial/Coach.tsx',import.meta.url),'utf8');
 assert.ok(!coach.includes('Math.random')); assert.ok(!coach.includes('setTimeout')); assert.ok(!coach.includes('setInterval'));
});
