import {test,expect} from '@playwright/test';
const api=`http://127.0.0.1:${process.env.INQUIRY_E2E_PORT || '18760'}`;
const scenarios=[
 {subject:'科学',grade:'三年级',topic:'植物为什么需要阳光？',capability:'activity.design@1',type:'ObservationTask'},
 {subject:'语文',grade:'四年级',topic:'怎样通过语言描写表现人物特点？',capability:'reading.design@1',type:'ReadingInquiryTask'},
 {subject:'数学',grade:'五年级',topic:'如何调查并改善班级图书角的图书分类？',capability:'data.design@1',type:'DataInquiryTask'},
 {subject:'跨学科',grade:'六年级',topic:'怎样改善学校门口的交通拥堵？',capability:'survey.design@1',type:'SurveyTask'},
];
for(const item of scenarios) test(`多学科隔离测试：${item.subject}`,async({page})=>{
 const registered=await page.request.post(`${api}/api/auth/register`,{data:{username:`subject_${Date.now()}`,password:'test-password-123'}}); expect(registered.ok()).toBeTruthy();
 await page.goto('/'); await page.getByRole('button',{name:'探究教学工作空间'}).click();
 await page.getByLabel('教学需求',{exact:true}).fill(item.topic);
 await page.getByText('补充教学条件（可选）').click();
 await page.getByLabel('学科',{exact:true}).fill(item.subject); await page.getByLabel('学段',{exact:true}).fill('小学'); await page.getByLabel('年级',{exact:true}).fill(item.grade);
 await page.getByRole('button',{name:'生成教学空间'}).click();
 await expect(page.getByText('学生任务：')).toBeVisible({timeout:30000});
 const spaces=(await (await page.request.get(`${api}/api/inquiry-workspaces`)).json()).data;
 const ws=spaces.find((s:any)=>s.title===item.topic).id;
 const data=(await (await page.request.get(`${api}/api/inquiry-workspaces/${ws}`)).json()).data;
 expect(data.latest_run.teaching_context.grade).toBe(item.grade);
 expect(data.artifacts.some((a:any)=>a.type===item.type)).toBe(true);
 expect(JSON.stringify(data.artifacts)).not.toContain('光的反射');
 const graph=(await (await page.request.get(`${api}/api/inquiry-workspaces/${ws}/runs/${data.latest_run.id}/graph`)).json()).data;
 expect(graph.nodes.some((n:any)=>n.capability===item.capability)).toBe(true);
 await page.getByRole('button',{name:'报告预览',exact:true}).click();
 await expect(page.locator('.report-paper')).toContainText('学生任务：');
 await expect(page.locator('.report-paper')).not.toContainText('光的反射');
});

test('unstructured topic does not receive a reflection demo from the test service',async({page})=>{
 const registered=await page.request.post(`${api}/api/auth/register`,{data:{username:`free_${Date.now()}`,password:'test-password-123'}}); expect(registered.ok()).toBeTruthy();
 await page.goto('/');await page.getByRole('button',{name:'探究教学工作空间'}).click();
 const topic='校园种植与观察';await page.getByLabel('教学需求',{exact:true}).fill(topic);
 await page.getByRole('button',{name:'生成教学空间'}).click();
 await expect(page.getByRole('heading',{name:'教学画布'})).toBeVisible({timeout:30000});
 await expect.poll(async()=>{const spaces=(await (await page.request.get(`${api}/api/inquiry-workspaces`)).json()).data;const ws=spaces.find((i:any)=>i.title===topic);if(!ws)return '';const data=(await (await page.request.get(`${api}/api/inquiry-workspaces/${ws.id}`)).json()).data;return data.latest_run?.status || '';},{timeout:30000}).toBe('completed');
 const spaces=(await (await page.request.get(`${api}/api/inquiry-workspaces`)).json()).data;
 const data=(await (await page.request.get(`${api}/api/inquiry-workspaces/${spaces.find((i:any)=>i.title===topic).id}`)).json()).data;
 expect(JSON.stringify(data.artifacts)).not.toContain('光的反射');
});
