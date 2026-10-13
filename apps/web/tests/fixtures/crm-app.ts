import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({ name: 'CRM acceptance fixture', version: '1.0.0' }, {});
document.body.innerHTML = '<label>商机名称<input id="title"></label><button id="save">保存商机</button><button id="assist">请求助手</button><output id="result"></output>';
const title = document.querySelector<HTMLInputElement>('#title')!;
const output = document.querySelector<HTMLOutputElement>('#result')!;
app.ontoolresult = result => {
  title.value = String(result.structuredContent?.title ?? '');
};
document.querySelector('#save')!.addEventListener('click', async () => {
  const result = await app.callServerTool({ name: 'crm_opportunity_save', arguments: { title: title.value } });
  output.textContent = result.isError ? '保存失败' : `已保存：${result.structuredContent?.title}`;
});
document.querySelector('#assist')!.addEventListener('click', async () => {
  const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text: '请分析当前商机' }] });
  output.textContent = result.isError ? '发送失败' : '已发送';
});
void app.connect();
