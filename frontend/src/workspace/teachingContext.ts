import type { TeachingContextInput } from './api';
const keys: Array<keyof TeachingContextInput> = ['subject','stage','grade','duration_minutes','learning_goals','prior_knowledge','language_level','real_life_context','resources','activity_formats','safety_constraints','teacher_requirements'];
export function cleanTeachingContext(value:TeachingContextInput):TeachingContextInput {
  return Object.fromEntries(keys.filter(key => value[key] !== undefined).map(key => [key,value[key]])) as TeachingContextInput;
}
export function changedTeachingFields(previous:TeachingContextInput, current:TeachingContextInput): Array<keyof TeachingContextInput> {
  const normalized = (value: unknown) => value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0) ? null : value;
  return keys.filter(key => JSON.stringify(normalized(previous[key])) !== JSON.stringify(normalized(current[key])));
}
