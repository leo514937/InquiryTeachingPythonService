import {test,expect} from '@playwright/test';

test.skip(process.env.INQUIRY_E2E_REAL_MODEL !== '1', 'Requires the configured external model');
for (const scenario of [
  {name:'完整教学设计', mode:'lesson', goal:'设计一节初中物理光的反射探究课，45分钟，包含教学目标、探究问题、实验活动和学习评价。'},
  {name:'独立实验', mode:'experiment', goal:'仅设计一个安全的初中物理光的反射实验，包含材料、实验步骤与安全措施。'},
]) {
  test(`真实模型：${scenario.name}`, async ({page}) => {
    test.setTimeout(360000);
    const response=await page.request.post('http://127.0.0.1:18760/api/auth/register',{data:{username:`real_${scenario.mode}_${Date.now()}`,password:'test-password-123'}});
    expect(response.ok()).toBeTruthy();
    await page.goto('/');
    await page.getByRole('button',{name:'探究教学工作空间'}).click();
    await page.getByLabel('教学需求',{exact:true}).fill(scenario.goal);
    await page.getByLabel('生成范围').selectOption(scenario.mode);
    await page.getByRole('button',{name:'生成教学空间'}).click();
    await expect(page.getByRole('heading',{name:'Agent 编排图'})).toBeVisible({timeout:30000});
    const graph = page.locator('.vue-flow__node');
    await expect(graph.first()).toBeVisible({timeout:180000});
    await page.getByRole('button',{name:'Agent 编排图'}).click();
    await expect.poll(async()=>page.locator('.dag-run-summary strong').innerText(),{timeout:300000, intervals:[2000,5000]}).toMatch(/已完成|等待教师审核|失败/);
    const status=await page.locator('.dag-run-summary strong').innerText();
    expect(status).toBe('已完成');
    await expect(page.locator('.agent-node.state-failed')).toHaveCount(0);
    await page.getByRole('button',{name:'教学设计',exact:true}).click();
    await expect(page.locator('.teaching-card').first()).toBeVisible();
    await page.getByRole('button',{name:'报告预览',exact:true}).click();
    await expect(page.locator('.report-paper section').first()).toBeVisible();
    await page.getByRole('button',{name:'创建快照'}).click();
    await expect(page.getByRole('button',{name:'导出 Word'})).toBeEnabled();
  });
}
