/* Public plan lookup only. Historical or incomplete mappings never confirm coverage. */
export const healthspringBase='https://data.healthspring.healthlx.com:8003/';

export function matchingYearPlans(bundle,cmsId,year) {
  if(bundle.resourceType!=='Bundle')throw new Error('Invalid HealthSpring directory response');
  const identifier=cmsId.replaceAll('-','_')+'_'+year+'0101';
  return (bundle.entry || []).map(e=>e.resource).filter(p=>p?.resourceType==='InsurancePlan'
    && p.status==='active' && (p.identifier || []).some(i=>i.value===identifier)
    && p.period?.start<=`${year}-01-01` && p.period?.end>=`${year}-12-31`
    && (p.network || []).some(n=>/^Organization\/[A-Za-z0-9.-]+$/.test(n.reference || '')));
}

export async function healthspringMapping(plan,signal) {
  const timeout=new AbortController();
  const cancel=()=>timeout.abort();signal?.addEventListener('abort',cancel,{once:true});
  if(signal?.aborted)timeout.abort();
  const timer=setTimeout(cancel,12000);
  try {
    const identifier=plan.cms_id.replaceAll('-','_')+'_'+plan.year+'0101';
    const response=await fetch(healthspringBase+'InsurancePlan?'+new URLSearchParams({identifier,_count:'10'}),
      {signal:timeout.signal,headers:{Accept:'application/fhir+json'}});
    if(!response.ok)throw new Error('HealthSpring directory returned HTTP '+response.status);
    const bundle=await response.json();
    const candidates=matchingYearPlans(bundle,plan.cms_id,plan.year);
    if((bundle.link || []).some(l=>l.relation==='next') || candidates.length>1)
      return {status:'unverified',message:'2027 plan network mapping requires review; provider coverage remains unverified.'};
    if(candidates.length===0)
      return {status:'unverified',message:'2027 plan network data is not available in the public directory. Provider and facility coverage remains unverified.'};
    return {status:'mapping-found',network:candidates[0].network,
      message:'2027 network references found. Provider and office checks still require connection validation; coverage remains unverified.'};
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
}
