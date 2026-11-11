import { test, expect } from '@playwright/test';

test('workspace keeps its shell and experiment draft while changing views', async ({ page }) => {
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `shell_${Date.now()}`, password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  const created = await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '反射实验预览'}});
  const workspaceId = (await created.json()).data.id;
  await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/experiments/reflection`);
  await page.goto('/');
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name: '反射实验预览'}).click();
  await expect(page.getByRole('navigation', {name: '工作空间工具栏'})).toBeVisible();
  await page.getByRole('button', {name: '打开实验'}).click();
  await page.getByLabel('观察结论').fill('尚未保存的观察');
  await page.getByRole('button', {name: '教学设计', exact: true}).click();
  await expect(page.getByRole('heading', {name: '教学画布'})).toBeVisible();
  await page.getByRole('button', {name: '实验探索', exact: true}).click();
  await expect(page.getByLabel('观察结论')).toHaveValue('尚未保存的观察');
  await expect(page.getByRole('button', {name: 'AI 协作'})).toBeVisible();
});

test('all three workbenches open the same authorized workspace from the header', async ({ page }) => {
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `shared_${Date.now()}`, password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  const created = await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '共同使用的探究空间'}});
  expect(created.ok()).toBeTruthy();
  await page.goto('/');
  for (const role of ['教师工作台', '研学基地工作台', '家长工作台']) {
    await page.getByRole('button', {name: role, exact: true}).click();
    const entry = page.locator('header.workspace-header').getByRole('button', {name: '探究教学工作空间'});
    await expect(entry).toBeVisible();
    await entry.click();
    await expect(page.locator('.workspace-nav').getByRole('button', {name: '共同使用的探究空间'})).toBeVisible();
    await page.getByRole('button', {name: '返回对话模式'}).click();
    await expect(page.getByRole('button', {name: role, exact: true})).toHaveClass(/active/);
  }
});

test('teacher edits experiment fields and preserves activity order after refresh', async ({ page }) => {
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `canvas_${Date.now()}`, password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  await page.goto('/');
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.getByLabel('教学需求', {exact: true}).fill('光的反射教学');
  await page.getByRole('button', {name: '生成教学空间'}).click();
  const group = page.locator('#group-activities');
  await expect(group.getByRole('heading', {name: '记录数据'})).toBeVisible();
  await group.getByRole('button', {name: '编辑属性'}).first().click();
  await page.getByLabel('实验材料').fill('平面镜\n手电筒');
  await page.getByRole('button', {name: '保存修改'}).click();
  await expect(group.getByText('器材：平面镜、手电筒')).toBeVisible();
  await group.getByRole('button', {name: '上移 记录数据'}).click();
  await expect(group.locator('article').first()).toContainText('记录数据');
  await page.reload();
  await expect(group.locator('article').first()).toContainText('记录数据');
  await expect(group.getByText('器材：平面镜、手电筒')).toBeVisible();
});

test('narrow workspace can open navigation and collaboration drawers', async ({ page }) => {
  await page.setViewportSize({width: 390, height: 844});
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `mobile_${Date.now()}`, password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  const created = await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '移动端探究'}});
  await page.goto('/');
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.getByRole('button', {name: '打开空间导航'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name: '移动端探究'}).click();
  await expect(page.getByRole('heading', {name: '教学画布'})).toBeVisible();
  await page.getByRole('button', {name: '打开协作面板'}).click();
  await expect(page.getByRole('button', {name: 'AI 协作'})).toBeInViewport();
  expect((await created.json()).data.id).toBeTruthy();
});

test('administrator can open curriculum settings on a narrow workspace', async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  const registered=await page.request.post('http://127.0.0.1:18760/api/auth/admin/register', {data:{username:`admin_${Date.now()}`,password:'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  await page.goto('/');
  await page.getByRole('button', {name:'探究教学工作空间'}).click();
  await page.getByRole('button', {name:'打开空间导航'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name:'课标检索设置'}).click();
  await expect(page.getByRole('heading', {name:'课标检索设置'})).toBeVisible();
});

test('concurrent refresh requires merge and preserves unknown server fields', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `merge_${Date.now()}`, password: 'test-password-123'}});
  const workspaceId = (await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '并发编辑'}})).json()).data.id;
  const item = (await (await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/experiments/reflection`)).json()).data;
  await page.goto('/');
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name:'并发编辑'}).click();
  await page.getByRole('button', {name:'编辑属性'}).click();
  await page.getByLabel('内容说明').fill('我的说明');
  expect((await page.request.patch(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/artifacts/${item.id}`, {data:{expected_version:item.version,content:{...item.content, custom:'同事新增字段'}}})).ok()).toBeTruthy();
  await page.locator('.workspace-nav').getByRole('button', {name:'并发编辑'}).click();
  await page.getByRole('button', {name:'保存修改'}).click();
  await expect(page.getByText('对象已更新，本地输入已保留。请对照最新内容手动合并。')).toBeVisible();
  await page.getByRole('button', {name:'以最新版本继续合并'}).click();
  await page.getByRole('button', {name:'保存修改'}).click();
  await expect(page.getByRole('button', {name:'保存修改'})).toBeDisabled();
  await expect.poll(async () => {
    const stored = (await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}`)).json()).data.artifacts.find((a:any)=>a.id===item.id);
    return [stored.content.description, stored.content.custom];
  }).toEqual(['我的说明', '同事新增字段']);
});

test('switching workspaces never reuses the previous report snapshot', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `snap_${Date.now()}`, password: 'test-password-123'}});
  await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '空间甲'}});
  await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title: '空间乙'}});
  await page.goto('/');
  await page.getByRole('button', {name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name:'空间甲'}).click();
  await page.getByRole('button', {name:'报告预览', exact:true}).click();
  await page.getByRole('button', {name:'创建快照'}).click();
  await expect(page.getByRole('button', {name:'导出 Word'})).toBeEnabled();
  await page.locator('.workspace-nav').getByRole('button', {name:'空间乙'}).click();
  await page.getByRole('button', {name:'报告预览', exact:true}).click();
  await expect(page.getByRole('button', {name:'导出 Word'})).toBeDisabled();
});

test('inline edits to multiple objects keep each unsaved title', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `draft_${Date.now()}`, password: 'test-password-123'}});
  const workspaceId = (await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title:'多对象草稿'}})).json()).data.id;
  await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/experiments/reflection`);
  await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/experiments/reflection`);
  await page.goto('/');
  await page.getByRole('button', {name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name:'多对象草稿'}).click();
  const cards=page.locator('#group-activities article');
  await cards.nth(0).getByRole('button', {name:'内联编辑标题'}).click();
  await cards.nth(0).getByLabel('标题').fill('未保存标题甲');
  await cards.nth(1).getByRole('button', {name:'内联编辑标题'}).click();
  await expect(cards.nth(0).getByLabel('标题')).toHaveValue('未保存标题甲');
  await cards.nth(0).getByRole('button', {name:'保存标题'}).click();
  await expect(cards.nth(0).getByRole('heading', {name:'未保存标题甲'})).toBeVisible();
  await cards.nth(0).getByRole('button', {name:'编辑属性'}).click();
  await expect(page.locator('.inspector-content').getByLabel('标题')).toHaveValue('未保存标题甲');
  await expect(page.getByRole('button', {name:'保存修改'})).toBeDisabled();
});

test('revoked access hides cached teaching content until rechecked', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: `revoked_${Date.now()}`, password: 'test-password-123'}});
  const workspaceId = (await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data: {title:'撤权空间'}})).json()).data.id;
  await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${workspaceId}/experiments/reflection`);
  await page.goto('/');
  await page.getByRole('button', {name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button', {name:'撤权空间'}).click();
  await expect(page.getByRole('heading', {name:'光的反射交互实验'})).toBeVisible();
  await page.route(`**/api/inquiry-workspaces/${workspaceId}/dependencies`, route => route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'来源权限已撤销'})}));
  await page.locator('.workspace-nav').getByRole('button', {name:'撤权空间'}).click();
  await expect(page.getByRole('heading', {name:'工作空间暂不可访问'})).toBeVisible();
  await expect(page.getByRole('heading', {name:'光的反射交互实验'})).toBeHidden();
});

test('teacher generates, experiments, edits narrative, exports, and returns to dialogue', async ({ page }) => {
  const username = `e2e_${Date.now()}`;
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username, password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  await page.goto('/');
  await page.getByRole('button', {name: '教师工作台'}).click();
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.getByLabel('教学需求', {exact: true}).fill('为八年级设计一课时光的反射探究活动');
  await page.getByRole('button', {name: '生成教学空间'}).click();
  await expect(page.getByRole('heading', {name: '教学画布'})).toBeVisible({timeout: 30000});
  await expect(page.getByRole('heading', {name: '理解反射规律'})).toBeVisible();
  await page.getByRole('button', {name: '打开实验'}).click();
  for (const angle of [30, 45, 60]) {
    await page.getByLabel('入射角度数').fill(String(angle));
    await page.getByRole('button', {name: '记录一组数据'}).click();
    await expect(page.locator('.reflection').getByRole('status')).toContainText('已保存');
  }
  await page.getByLabel('观察结论').fill('反射角等于入射角');
  await page.getByRole('button', {name: '保存结论'}).click();
  await page.getByLabel('将记录加入报告').check();
  await page.getByRole('button', {name: '返回画布'}).click();
  await page.getByRole('button', {name: '报告预览'}).click();
  await page.getByRole('button', {name: '添加报告叙述'}).click();
  await page.getByLabel('编辑报告段落').last().fill('学生通过比较数据理解规律。');
  await page.getByRole('button', {name: '保存叙述'}).last().click();
  await page.getByRole('button', {name: '创建快照'}).click();
  await expect(page.getByText('当前导出快照：')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', {name: '导出 Word'}).click();
  expect((await download).suggestedFilename()).toMatch(/docx$/);
  await page.getByRole('button', {name: '返回对话模式'}).click();
  await expect(page.locator('.chat-column')).toBeVisible();
});

test('agent graph shows the persisted plan and remains read only', async ({ page }) => {
  const registered = await page.request.post('http://127.0.0.1:18760/api/auth/register', {data: {username: 'graph_' + Date.now(), password: 'test-password-123'}});
  expect(registered.ok()).toBeTruthy();
  await page.goto('/');
  await page.getByRole('button', {name: '探究教学工作空间'}).click();
  await page.getByLabel('教学需求', {exact: true}).fill('光的反射教学设计');
  await page.getByRole('button', {name: '生成教学空间'}).click();
  await page.getByRole('button', {name: 'Agent 编排图'}).click();
  await expect(page.getByRole('heading', {name: 'Agent 编排图'})).toBeVisible();
  await expect(page.locator('.vue-flow__node')).toHaveCount(6, {timeout: 30000});
  await expect(page.locator('.vue-flow__edge')).toHaveCount(10);
  await expect(page.getByLabel('运行事件')).toContainText('任务已接收');
  await page.waitForTimeout(800);
  const pane = await page.locator('.dag-flow-wrap').boundingBox();
  for (const node of await page.locator('.vue-flow__node').all()) {
    const box = await node.boundingBox();
    expect(box && pane && box.x >= pane.x - 2 && box.x + box.width <= pane.x + pane.width + 2).toBeTruthy();
  }
  await page.getByRole('button', {name: /目标生成/}).first().click();
  await expect(page.getByRole('heading', {name: '节点详情'})).toBeVisible();
  await expect(page.getByText('goals.compose@1', {exact: true}).first()).toBeVisible();
  await page.keyboard.press('Delete');
  await expect(page.locator('.vue-flow__node')).toHaveCount(6);
  await expect(page.getByLabel('历史运行')).toBeVisible();
});


test('agent graph updates from live events and can reopen history', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data:{username:'live_graph_'+Date.now(),password:'test-password-123'}});
  const created=await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces', {data:{title:'实时编排'}});
  const ws=(await created.json()).data.id;
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'实时编排'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.getByText('暂无可访问的运行。', {exact:false})).toBeVisible();
  const first=await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces/'+ws+'/runs', {data:{goal:'慢速图：光的反射',mode:'lesson',idempotency_key:'first'}});
  const run1=(await first.json()).data.id;
  await page.getByRole('button',{name:'教学设计',exact:true}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.locator('.agent-node.state-running').first()).toBeVisible({timeout:10000});
  await expect(page.locator('.agent-node.state-succeeded')).toHaveCount(6,{timeout:20000});
  const second=await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces/'+ws+'/runs', {data:{goal:'再做一遍',mode:'lesson',idempotency_key:'second'}});
  expect(second.ok()).toBeTruthy();
  const run2=(await second.json()).data.id;
  await page.getByRole('button',{name:'教学设计',exact:true}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.getByLabel('历史运行').locator('option')).toHaveCount(2);
  await page.getByLabel('历史运行').selectOption(run1);
  await expect(page.locator('.agent-node.state-succeeded')).toHaveCount(6,{timeout:10000});
  await page.getByLabel('历史运行').selectOption(run2);
  await expect(page.locator('.vue-flow__node')).toHaveCount(6,{timeout:15000});
});



test('a completed historical graph rechecks permissions while it remains open', async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.setTimeout;
    window.setTimeout = ((handler: TimerHandler, delay?: number, ...args: unknown[]) =>
      original(handler, delay === 15000 || delay === 3000 ? 250 : delay, ...args)) as typeof window.setTimeout;
  });
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data:{username:'graph_acl_'+Date.now(),password:'test-password-123'}});
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.getByLabel('教学需求',{exact:true}).fill('权限复核演示');
  await page.getByRole('button',{name:'生成教学空间'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.locator('.agent-node.state-succeeded')).toHaveCount(6,{timeout:20000});
  let failures = 0;
  await page.route('**/api/inquiry-workspaces/*/runs/*/graph', route => {
    failures++;
    return route.fulfill(failures === 1
      ? {status:503,contentType:'application/json',body:JSON.stringify({detail:'暂时不可用'})}
      : {status:403,contentType:'application/json',body:JSON.stringify({detail:'来源权限已撤销'})});
  });
  await expect(page.getByRole('heading',{name:'工作空间暂不可访问'})).toBeVisible({timeout:5000});
  expect(failures).toBeGreaterThanOrEqual(2);
  await expect(page.locator('.agent-node')).toHaveCount(0);
});



test('review pause is displayed for the run without inventing paused nodes', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data:{username:'graph_review_'+Date.now(),password:'test-password-123'}});
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.getByLabel('教学需求',{exact:true}).fill('审核图：设计光的反射课程');
  await page.getByRole('button',{name:'生成教学空间'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.locator('.dag-run-summary').getByText('等待教师审核', {exact:true})).toBeVisible({timeout:20000});
  await expect(page.locator('.agent-node.state-succeeded')).toHaveCount(6);
  await expect(page.locator('.agent-node.state-waiting_review')).toHaveCount(0);
});


test('new runs open the live DAG and restore it after a refresh', async ({ page }) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data:{username:'auto_graph_'+Date.now(),password:'test-password-123'}});
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.getByLabel('教学需求',{exact:true}).fill('慢速图：光的反射');
  await page.getByRole('button',{name:'生成教学空间'}).click();
  await expect(page.getByRole('heading',{name:'Agent 编排图'})).toBeVisible();
  await expect(page.locator('.agent-node.state-running').first()).toBeVisible({timeout:10000});
  await page.reload();
  await expect(page.getByRole('heading',{name:'Agent 编排图'})).toBeVisible({timeout:10000});
  await expect(page.locator('.vue-flow__node').first()).toBeVisible({timeout:10000});
  await expect(page.getByRole('heading',{name:'教学画布'})).toBeVisible({timeout:30000});
});

test('report provides section navigation and links a section to its teaching object', async ({page}) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register', {data:{username:'report_nav_'+Date.now(),password:'test-password-123'}});
  const ws=(await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces',{data:{title:'报告定位'}})).json()).data.id;
  await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}/experiments/reflection`);
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'报告定位'}).click();
  await page.getByRole('button',{name:'报告预览',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'报告章节'})).toBeVisible();
  await page.getByRole('button',{name:'定位到教学对象'}).first().click();
  await expect(page.getByRole('heading',{name:'教学画布'})).toBeVisible();
  await expect(page.locator('.teaching-card.selected')).toHaveCount(1);
});

test('teacher can submit a new goal from the orchestration view', async ({page}) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:'composer_'+Date.now(),password:'test-password-123'}});
  const ws=(await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces',{data:{title:'编排输入'}})).json()).data.id;
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'编排输入'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.getByLabel('编排教学需求')).toBeVisible({timeout:3000});
  await page.getByLabel('编排教学需求').fill('慢速图：探究光的反射');
  await page.getByLabel('追加到当前工作空间').check();
  await page.getByRole('button',{name:'开始自动编排'}).click();
  await expect(page.locator('.vue-flow__node').first()).toBeVisible({timeout:15000});
  const runs=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}/runs`)).json()).data.items;
  expect(runs).toHaveLength(1);
});

test('a disconnected event stream recovers without starting another run', async ({page}) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:'reconnect_'+Date.now(),password:'test-password-123'}});
  const ws=(await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces',{data:{title:'断线恢复'}})).json()).data.id;
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'断线恢复'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  const stream='**/api/inquiry-workspaces/*/runs/*/events?follow=true*';
  await page.route(stream, route=>route.abort());
  await page.getByLabel('编排教学需求').fill('慢速图：光的反射');
  await page.getByLabel('追加到当前工作空间').check();
  await page.getByRole('button',{name:'开始自动编排'}).click();
  await expect(page.getByText('实时连接中断', {exact:false})).toBeVisible({timeout:15000});
  await page.unroute(stream);
  await expect(page.locator('.agent-node.state-succeeded').first()).toBeVisible({timeout:20000});
  const runs=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}/runs`)).json()).data.items;
  expect(runs).toHaveLength(1);
});

test('editing an experiment replans affected objects and refreshes the report', async ({page}) => {
  test.setTimeout(90000);
  await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:`replan_${Date.now()}`,password:'test-password-123'}});
  await page.goto('/');
  await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.getByLabel('教学需求',{exact:true}).fill('光的反射探究与评价');
  await page.getByRole('button',{name:'生成教学空间'}).click();
  await expect(page.getByRole('heading',{name:'光的反射实验'})).toBeVisible({timeout:30000});
  const spaces=(await (await page.request.get('http://127.0.0.1:18760/api/inquiry-workspaces')).json()).data;
  const ws=spaces.find((item:any)=>item.title==='光的反射探究与评价').id;
  const before=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}`)).json()).data;
  const experiment=before.artifacts.find((a:any)=>a.type==='Experiment');
  const goal=before.artifacts.find((a:any)=>a.type==='LearningGoal');
  await page.locator(`#artifact-${experiment.id}`).getByRole('button',{name:'编辑属性'}).click();
  await page.getByLabel('实验材料').fill('平面镜\n手电筒');
  await page.getByRole('button',{name:'保存修改'}).click();
  await page.getByRole('button',{name:'AI 协作'}).click();
  await page.getByRole('button',{name:'查看受影响对象'}).click();
  await expect(page.getByText('依赖影响预览')).toBeVisible();
  await page.getByRole('button',{name:'确认更新下游对象'}).click();
  await expect(page.getByRole('heading',{name:'Agent 编排图'})).toBeVisible();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await expect(page.locator('.dag-run-summary')).toContainText('局部重编排');
  await expect(page.locator('.dag-run-summary strong')).toHaveText('已完成',{timeout:30000});
  const after=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}`)).json()).data;
  expect(after.artifacts.find((a:any)=>a.id===goal.id).version).toBe(goal.version);
  expect(after.artifacts.some((a:any)=>a.version>1 && a.content.title?.startsWith('更新后'))).toBeTruthy();
  await page.getByRole('button',{name:'报告预览',exact:true}).click();
  await expect(page.locator('.report-paper')).toContainText('更新后');
});

test('thirty-node DAG is usable with keyboard and reduced motion', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1366,height:900});
  await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:`scale_${Date.now()}`,password:'test-password-123'}});
  const ws=(await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces',{data:{title:'大图布局'}})).json()).data.id;
  const run=(await (await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}/runs`,{data:{goal:'慢速图：布局',mode:'lesson',idempotency_key:'scale'}})).json()).data;
  await page.route(`**/api/inquiry-workspaces/${ws}/runs/${run.id}/graph`, async route=>{
    const original=await route.fetch(); const json=await original.json();
    const base=json.data;
    const nodes=Array.from({length:30},(_,i)=>({id:`n${i}`,capability:'goals.compose@1',depends_on:i?['n0']:[],status:i===0?'running':'queued',attempts:0,started_at:null,finished_at:null,error_code:null,error_message:null,input_summary:'',output_summary:'',result_refs:[],change_kind:null}));
    json.data={...base,status:'running',nodes,edges:nodes.slice(1).map(n=>({id:`n0-${n.id}`,source:'n0',target:n.id}))};
    await route.fulfill({response:original,json});
  });
  await page.goto('/'); await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'大图布局'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  const start=Date.now(); await expect(page.locator('.vue-flow__node')).toHaveCount(30,{timeout:15000});
  const ms=Date.now()-start; console.log(`30-node graph render: ${ms} ms`);
  expect((await page.locator('.dag-flow-wrap').boundingBox())!.y).toBeLessThan(500);
  await page.getByRole('button',{name:'适配画布'}).click();
  await expect.poll(async()=>{ const pane=await page.locator('.dag-flow-wrap').boundingBox(); const left=await page.locator('.vue-flow__node').nth(1).boundingBox(); const right=await page.locator('.vue-flow__node').last().boundingBox(); return !!pane && !!left && !!right && left.x>=pane.x-2 && right.x+right.width<=pane.x+pane.width+2; },{timeout:5000}).toBe(true);
  const running=page.locator('.agent-node.state-running').first();
  await expect(running).toBeVisible();
  expect(await running.evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
  const list=page.locator('.dag-accessible-list');
  const button=list.getByRole('button').first(); await button.focus(); await page.keyboard.press('Enter');
  await expect(button).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('heading',{name:'节点详情'})).toBeVisible();
  await page.screenshot({path:'../.test-tmp/dag-30-reduced-motion.png'});
});

test('a new topic creates a separate workspace without the previous manual artifact', async ({page}) => {
  await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:`isolation_${Date.now()}`,password:'test-password-123'}});
  const ws=(await (await page.request.post('http://127.0.0.1:18760/api/inquiry-workspaces',{data:{title:'原工作空间'}})).json()).data.id;
  const artifact=(await (await page.request.post(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}/experiments/reflection`)).json()).data;
  await page.goto('/'); await page.getByRole('button',{name:'探究教学工作空间'}).click();
  await page.locator('.workspace-nav').getByRole('button',{name:'原工作空间'}).click();
  await page.getByRole('button',{name:'Agent 编排图'}).click();
  await page.getByLabel('编排教学需求').fill('四年级语文人物描写');
  await expect(page.getByLabel('新建工作空间生成')).toBeChecked();
  await page.getByRole('button',{name:'开始自动编排'}).click();
  await expect.poll(async()=>(await (await page.request.get('http://127.0.0.1:18760/api/inquiry-workspaces')).json()).data.length,{timeout:15000}).toBe(2);
  const spaces=(await (await page.request.get('http://127.0.0.1:18760/api/inquiry-workspaces')).json()).data;
  const newId=spaces.find((s:any)=>s.id!==ws).id;
  const newSpace=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${newId}`)).json()).data;
  const oldSpace=(await (await page.request.get(`http://127.0.0.1:18760/api/inquiry-workspaces/${ws}`)).json()).data;
  expect(newSpace.artifacts.some((a:any)=>a.id===artifact.id)).toBe(false);
  expect(oldSpace.artifacts.some((a:any)=>a.id===artifact.id)).toBe(true);
});
