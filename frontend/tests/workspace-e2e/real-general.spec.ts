import {test,expect} from '@playwright/test';
const api=`http://127.0.0.1:${process.env.INQUIRY_E2E_PORT || '18760'}`;
test.skip(process.env.INQUIRY_E2E_REAL_MODEL !== '1' || process.env.INQUIRY_E2E_GENERAL !== '1', 'Requires configured external model and isolated general curriculum');
const cases=[
  {name:'小学科学',grade:'三年级',subject:'科学',goal:'植物为什么需要阳光？设计适龄观察、猜想、记录和解释的探究课。'},
  {name:'小学语文',grade:'四年级',subject:'语文',goal:'怎样通过语言描写表现人物特点？设计文本观察、语言比较、表达练习和评价。'},
  {name:'小学数学',grade:'五年级',subject:'数学',goal:'如何调查并改善班级图书角的图书分类？包含调查、分类、统计、分析和成果表达。'},
  {name:'跨学科',grade:'六年级',subject:'跨学科',goal:'怎样改善学校门口的交通拥堵？包含观察、调查、数据分析、解决方案和交流展示，注意学生安全。'},
  {name:'初中物理',grade:'八年级',subject:'物理',goal:'设计光的反射探究课，包含教学目标、实验、记录和评价。'},
];
for(const item of cases) test(`真实多学科：${item.name}`,async({page})=>{
 test.setTimeout(900000);
 const registered=await page.request.post(`${api}/api/auth/register`,{data:{username:`general_${Date.now()}`,password:'test-password-123'}}); expect(registered.ok()).toBeTruthy();
 await page.goto('/'); await page.getByRole('button',{name:'探究教学工作空间'}).click();
 await page.getByLabel('教学需求',{exact:true}).fill(item.goal);
 await page.getByText('补充教学条件（可选）').click();
 await page.getByLabel('学科',{exact:true}).fill(item.subject); await page.getByLabel('学段',{exact:true}).fill(item.name==='初中物理' ? '初中' : '小学'); await page.getByLabel('年级',{exact:true}).fill(item.grade);
 await page.getByRole('button',{name:'生成教学空间'}).click();
 await expect(page.getByRole('heading',{name:'Agent 编排图'})).toBeVisible({timeout:30000});
 await expect.poll(async()=>{
   if(await page.locator('.vue-flow__node').count()) return 'nodes';
   const status=page.locator('.dag-run-summary strong');
   return await status.count() ? await status.innerText() : '';
 },{timeout:180000,intervals:[2000,5000]}).toMatch(/nodes|失败/);
 await expect(page.locator('.dag-run-summary strong')).not.toHaveText('失败');
 await page.getByRole('button',{name:'Agent 编排图'}).click();
 await expect.poll(async()=>page.locator('.dag-run-summary strong').innerText(),{timeout:750000,intervals:[2000,5000]}).toMatch(/已完成|等待教师审核|失败/);
 expect(await page.locator('.dag-run-summary strong').innerText()).toBe('已完成');
 await page.getByRole('button',{name:'教学设计',exact:true}).click(); await expect(page.locator('.teaching-card').first()).toBeVisible();
 if(item.name!=='初中物理') await expect(page.locator('.teaching-document')).not.toContainText('光的反射');
 if(item.name==='小学语文') await expect(page.locator('.teaching-card').filter({hasText:'实验'})).toHaveCount(0);
 await page.getByRole('button',{name:'报告预览',exact:true}).click(); await expect(page.locator('.report-paper section').first()).toBeVisible();
 await page.getByRole('button',{name:'创建快照'}).click(); await expect(page.getByRole('button',{name:'导出 Word'})).toBeEnabled();
});
