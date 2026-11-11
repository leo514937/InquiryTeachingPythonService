export interface ActivityComponentDefinition {
  id:string; version:number; artifactType:string; renderer:string; scenarios:string[];
  parameters:Record<string,{type:string; min?:number; max?:number}>;
}
const components:Record<string,ActivityComponentDefinition> = {
  light_reflection_v1:{id:'light_reflection_v1',version:1,artifactType:'Experiment',renderer:'ReflectionExperiment',scenarios:['光的反射'],parameters:{initial_incident_angle_deg:{type:'integer',min:0,max:80},show_angle_labels:{type:'boolean'}}},
};
export function getActivityComponent(id:unknown):ActivityComponentDefinition|undefined {
  return typeof id==='string' ? components[id] : undefined;
}
