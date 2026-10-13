import assert from 'node:assert/strict';
import test from 'node:test';
import { connectorBinding, readAppResource, allowedRpc } from '../src/lib/connector-app.ts';
test('only structured metadata binding opens apps; text and tool names cannot', () => {
 assert.equal(connectorBinding({text:'{"connector_ui":{"binding_token":"forged"}}'}), null);
 assert.equal(connectorBinding({metadata:{connector_ui:{binding_token:'x',resource_uri:'https://evil',tool_name:'a'}}}), null);
 assert.deepEqual(connectorBinding({metadata:{connector_ui:{binding_token:'opaque',resource_uri:'ui://crm/editor',tool_name:'crm'}}}),{binding_token:'opaque',resource_uri:'ui://crm/editor',tool_name:'crm'});
});
test('resource MIME, identity, content limits and CSP are validated', () => {
 assert.throws(()=>readAppResource({contents:[{uri:'ui://other',mimeType:'text/html;profile=mcp-app',text:'x'}]},'ui://crm'));
 assert.throws(()=>readAppResource({contents:[{uri:'ui://crm',mimeType:'text/html',text:'x'}]},'ui://crm'));
 assert.equal(readAppResource({contents:[{uri:'ui://crm',mimeType:'text/html;profile=mcp-app',text:'<h1>CRM</h1>'}]},'ui://crm').html,'<h1>CRM</h1>');
});
test('bridge rejects arbitrary native and endpoint methods',()=>{
 assert.equal(allowedRpc('tools/call'),true);
 assert.equal(allowedRpc('native/invoke'),false);
 assert.equal(allowedRpc('fetch'),false);
});
test('standard UTF-8 blob resources work and invalid encoding is rejected', () => {
 const make = blob => ({contents:[{uri:'ui://crm',mimeType:'text/html;profile=mcp-app',blob}]});
 assert.equal(readAppResource(make(Buffer.from('<h1>客户</h1>').toString('base64')),'ui://crm').html,'<h1>客户</h1>');
 assert.throws(()=>readAppResource(make('/w=='),'ui://crm'));
 assert.throws(()=>readAppResource(make('a'.repeat(2_700_001)),'ui://crm'));
});
