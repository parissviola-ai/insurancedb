export const priorityKeys=['dental','otc','premium','moop','specialist','hospital','vision','hearing','transportation'];
export const lowerIsBetter=new Set(['premium','moop','specialist','hospital','hearing']);
/* Relative scores compare dollar allowances only; they do not establish coverage. */
export function rankPlans(plans, weights, needsDrugs=false) {
  const keys=priorityKeys.filter(k=>Number(weights[k])>0);
  const complete=plans.filter(p=>!p.special_needs && !(needsDrugs && p.ma_only) && keys.length && keys.every(k=>Number.isFinite(p.benefit_metrics?.[k]?.amount)));
  const ranges={};for(const k of keys) {
    const values=complete.map(p=>p.benefit_metrics[k].amount*(k==='otc'?4:1));
    ranges[k]=[Math.min(...values),Math.max(...values)];
  }
  const scores=new Map();const sum=keys.reduce((n,k)=>n+Number(weights[k]),0);
  for(const p of complete) {
    let score=0;
    for(const k of keys) {
      const [min,max]=ranges[k],v=p.benefit_metrics[k].amount*(k==='otc'?4:1);
      const normalized=max===min?1:lowerIsBetter.has(k)?(max-v)/(max-min):(v-min)/(max-min);
      score+=normalized*Number(weights[k]);
    }
    scores.set(p.id,100*score/sum);
  }
  return plans.map(p=>({plan:p,score:scores.get(p.id) ?? null,
    reason:p.special_needs?'Eligibility review required':needsDrugs&&p.ma_only?'No included Part D coverage':!keys.length?'Select at least one priority':'Missing a selected benefit amount'}))
    .sort((a,b)=>(b.score ?? -1)-(a.score ?? -1) || a.plan.name.localeCompare(b.plan.name));
}
