import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultChat } from '../src/core/default-chat.ts';
const model = {type:'openai_credential',credential_id:'credential',model:'custom-model',parameters:{}};
const session = (id,updated_at,config=model) => ({session:{id,updated_at,config:{name:id,chat_model_config:config}}});
function fixture(sessions=[]) {
 return {agents:async()=>({agents:[{id:'agent',data:{name:'Assistant'}}]}),credentials:async()=>({credentials:[{id:'credential',type:'openai_credential'}]}),sessions:async()=>({sessions}),models:async()=>({models:[{name:'retired',status:'sunset'},{name:'default-model'}]}),createSession:async(agent, config)=>{assert.equal(agent,'agent');assert.equal(config.model,'default-model');return {session_id:'created'};}};
}
test('home resumes newest usable session without creating or calling model catalog',async()=>{
 const api=fixture([session('old','2026-01-01'),session('recent','2026-02-01')]);
 api.createSession=async()=>assert.fail('unexpected create');api.models=async()=>assert.fail('unexpected catalog');
 assert.deepEqual(await defaultChat(api),{id:'recent',agentId:'agent',agentName:'Assistant',name:'recent',model:'custom-model'});
});
test('first visit selects first active catalog model and creates a chat',async()=>{
 assert.equal((await defaultChat(fixture())).id,'created');
});
test('deleted credentials are not reused from history',async()=>{
 const result=await defaultChat(fixture([session('stale','2026-02-01',{...model,credential_id:'deleted'})]));
 assert.equal(result.id,'created');
});
test('missing agents or credentials produce setup errors without creating sessions',async()=>{
 const api=fixture();api.agents=async()=>({agents:[]});await assert.rejects(defaultChat(api));
 const other=fixture();other.credentials=async()=>({credentials:[]});await assert.rejects(defaultChat(other));
});

test('new chat prefers current session model including its parameters over a more recent session', async () => {
 const chosen={...model,parameters:{temperature:0.3}};
 const api=fixture([session('current','2026-01-01',chosen),session('newer','2026-03-01',{...model,model:'other-model'})]);
 api.models=async()=>assert.fail('catalog should not be needed');
 let creates=0;
 api.createSession=async(agent,config)=>{creates++;assert.equal(agent,'agent');assert.deepEqual(config,chosen);return {session_id:'fresh'};};
 const result=await defaultChat(api,()=>true,{agentId:'agent',sourceSessionId:'current',createNew:true});
 assert.equal(result.id,'fresh');assert.equal(creates,1);
});
test('new chat in history inherits most recent model and does not create after workspace changes', async () => {
 const api=fixture([session('old','2026-01-01'),session('new','2026-03-01',{...model,model:'latest'})]);
 api.createSession=async(agent,config)=>{assert.equal(config.model,'latest');return {session_id:'fresh'};};
 assert.equal((await defaultChat(api,()=>true,{agentId:'agent',createNew:true})).id,'fresh');
 api.createSession=async()=>assert.fail('stale workspace must not create');
 await assert.rejects(defaultChat(api,()=>false,{agentId:'agent',createNew:true}));
 await assert.rejects(defaultChat(api,()=>true,{agentId:'missing',createNew:true}));
});
