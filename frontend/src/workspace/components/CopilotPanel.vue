<template>
  <div class="copilot-content">
    <div class="copilot-intro"><span class="copilot-icon">✳</span><div><span class="eyebrow">YOUR TEACHING COPILOT</span><h3>一起完善探究设计</h3></div></div>
    <p class="side-help">以教学内容为中心。你可以发起新一轮生成，或根据已保存的修改更新相关对象。</p>
    <div v-if="selectedIds.length > 1" class="copilot-note">已选择 {{ selectedIds.length }} 个对象。多对象联合 AI 指令待支持。</div>
    <section class="copilot-block"><div class="block-title"><strong>追加到当前工作空间</strong><span>保留现有对象</span></div><p>根据教学需求创建新的教学对象，不会原位修改现有对象。</p><textarea v-model="goal" aria-label="工作空间生成需求" rows="3" placeholder="描述你想设计的教学内容"/><button type="button" :disabled="busy || !goal.trim()" @click="$emit('generate', goal)">开始生成</button></section>
    <section class="copilot-block"><div class="block-title"><strong>更新受影响对象</strong><span>局部协作</span></div><p v-if="artifact">当前对象：{{ artifact.content.title || artifact.type }} · v{{ artifact.version }}。先保存修改，再预览下游影响。</p><p v-else>在画布选择并修改一个对象后，可以更新相关的下游对象。</p><textarea v-model="instruction" aria-label="下游调整要求" rows="3" :disabled="!artifact || busy || dirty" placeholder="例如：结合新材料调整活动步骤"/><button type="button" :disabled="!artifact || busy || dirty || selectedIds.length > 1" @click="$emit('preview')">查看受影响对象</button>
      <div v-if="preview" class="impact-preview"><strong>依赖影响预览</strong><p v-if="!preview.targets.length && !preview.requires_review.length">没有可自动更新的受影响对象。</p><template v-if="preview.targets.length"><p>可更新</p><ul><li v-for="target in preview.targets" :key="target.id">{{ titleOf(target.id) }}</li></ul></template><template v-if="preview.requires_review.length"><p>需要教师审核</p><ul><li v-for="id in preview.requires_review" :key="id">{{ titleOf(id) }}</li></ul></template><button type="button" class="primary" :disabled="busy || !preview.targets.length" @click="$emit('replan', instruction)">确认更新下游对象</button></div>
    </section>
    <section v-if="run" class="copilot-block"><div class="block-title"><strong>最近执行</strong><span>{{ runLabel(run.status) }}</span></div><p v-if="run.error" role="alert">{{ run.error }}</p><ul v-if="run.warnings?.length"><li v-for="warning in run.warnings" :key="warning">{{ warning }}</li></ul><ul class="run-list"><li v-for="node in run.nodes" :key="node.id"><span>{{ capabilityLabel(node.capability) }}</span><small>{{ runLabel(node.status) }}</small></li></ul><div class="inline-actions"><button v-if="running || run.status === 'waiting_review'" type="button" @click="$emit('cancel')">取消本次运行</button><button v-if="run.review_approvable" type="button" @click="$emit('approve')">已检查风险，确认继续</button><button type="button" @click="$emit('details')">查看执行详情</button></div></section>
  </div>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue';
import type { Artifact } from '../api';
type Run = {id:string; status:string; error:string; review_approvable?:boolean; warnings:string[]; nodes:Array<{id:string;capability:string;status:string}>};
type Preview = {targets:Array<{id:string;version:number;type:string}>; requires_review:string[]};
const props = defineProps<{title:string; artifact:Artifact|null; artifacts:Artifact[]; selectedIds:string[]; busy:boolean; dirty:boolean; running:boolean; run:Run|null; preview:Preview|null}>();
defineEmits<{generate:[goal:string]; preview:[]; replan:[instruction:string]; cancel:[]; approve:[]; details:[]}>();
const goal=ref(props.title), instruction=ref('');
watch(() => props.title, value => { goal.value = value; });
function titleOf(id:string) { return String(props.artifacts.find(a=>a.id===id)?.content.title || '关联对象不可用'); }
function runLabel(status:string) { return ({queued:'等待执行',planning:'正在规划',running:'正在生成',succeeded:'已完成',completed:'生成完成',failed:'生成失败',cancelled:'已取消',waiting_review:'需要教师审核'} as Record<string,string>)[status] || status; }
function capabilityLabel(id:string) { return ({'requirements.analyze@1':'理解需求','knowledge.retrieve@1':'查找课程依据','knowledge.map@1':'分析知识','goals.compose@1':'设计学习目标','inquiry.design@1':'设计探究问题','activity.design@1':'设计实验与活动','assessment.design@1':'设计评价','quality.evaluate@1':'检查教学成果','report.assemble@1':'组装报告','report.narrative@1':'撰写说明','component.bind@1':'绑定实验组件'} as Record<string,string>)[id] || id; }
</script>
