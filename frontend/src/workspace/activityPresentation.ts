type Field = {label:string; key:string};
const specific:Record<string,Field[]> = {
  ReadingInquiryTask:[{label:'阅读材料',key:'passages'},{label:'思考问题',key:'questions'}],
  SurveyTask:[{label:'调查问题',key:'questions'},{label:'调查对象',key:'respondents'}],
  ObservationTask:[{label:'观察对象',key:'observation_targets'},{label:'观察记录',key:'recording_method'}],
  DataInquiryTask:[{label:'数据来源',key:'data_sources'},{label:'分析方法',key:'analysis_methods'}],
  CollaborationTask:[{label:'合作分工',key:'roles'}],
  EvidenceRecord:[{label:'证据记录',key:'evidence_fields'}],
  PresentationTask:[{label:'表达方式',key:'presentation_formats'}],
};
const common:Field[]=[{label:'活动步骤',key:'steps'},{label:'材料',key:'materials'},{label:'评价标准',key:'criteria'}];
export function activityFields(type:string,content:Record<string,unknown>):Array<{label:string;value:string}> {
 return [...(specific[type] || []),...common].flatMap(({label,key})=>{
  const value=content[key];
  const display=Array.isArray(value)?value.filter(item=>typeof item==='string'||typeof item==='number').join('、'):typeof value==='string'||typeof value==='number'?String(value):'';
  return display.trim() ? [{label:key==='materials' && type==='Experiment' ? '器材' : label,value:display}] : [];
 });
}
