
import dagre from '@dagrejs/dagre';
import type { DagSnapshot } from './api';

export function layoutDag(graph: DagSnapshot): Record<string, {x: number; y: number}> {
  const layout = new dagre.graphlib.Graph();
  layout.setGraph({rankdir: 'TB', nodesep: 48, ranksep: 100, marginx: 35, marginy: 35});
  layout.setDefaultEdgeLabel(() => ({}));
  for (const node of graph.nodes) layout.setNode(node.id, {width: 220, height: 110});
  for (const edge of graph.edges) layout.setEdge(edge.source, edge.target);
  dagre.layout(layout);
  return Object.fromEntries(graph.nodes.map(node => {
    const pos = layout.node(node.id);
    return [node.id, {x: pos.x - 110, y: pos.y - 55}];
  }));
}

export const nodeStatusLabels: Record<string, string> = {
  queued: '等待执行', running: '运行中', succeeded: '已完成', failed: '失败',
  skipped: '已跳过', cancelled: '已取消', result_discarded: '结果未采纳 / 执行状态未知',
  unknown: '状态未记录',
};
export const runStatusLabels: Record<string, string> = {
  queued: '等待执行', planning: '正在规划', running: '运行中', evaluating: '检查结果',
  completed: '已完成', failed: '失败', cancelled: '已取消', waiting_review: '等待教师审核',
};
export const capabilityLabels: Record<string, string> = {
  'requirements.analyze@1': '需求分析', 'knowledge.retrieve@1': '课程依据检索',
  'knowledge.map@1': '知识分析', 'goals.compose@1': '目标生成',
  'inquiry.design@1': '探究问题设计', 'activity.design@1': '实验与活动设计',
  'reading.design@1': '文本探究设计', 'survey.design@1': '观察与调查设计', 'data.design@1': '数据探究设计',
  'assessment.design@1': '学习评价设计', 'quality.evaluate@1': '质量检查',
  'report.assemble@1': '报告组装', 'component.bind@1': '交互组件绑定',
  'report.narrative@1': '报告叙述生成',
};
export function capabilityName(capability: string): string { return capabilityLabels[capability] || capability; }

