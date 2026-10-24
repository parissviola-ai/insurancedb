// Server-side anonymous browser for the public Connecture shopping flows.
// Fresh isolated context per request; no login, stored session, or credentials.
const {chromium}=require('playwright');
async function main(){
  const input=JSON.parse(await new Promise(resolve=>{let text='';process.stdin.on('data',d=>text+=d);process.stdin.on('end',()=>resolve(text));}));
  if(!['Molina','Highmark','Excellus BlueCross BlueShield'].includes(input.carrier)||!/^\d{5}$/.test(input.zip)||!/^\d{5}$/.test(input.county)||![2026,2027].includes(input.year))throw Error('Invalid shopping request');
  const host=input.carrier==='Molina'?'molina1.destinationrx.com':input.carrier==='Highmark'?'highmark1.destinationrx.com':'excellus1.destinationrx.com';
  const source=`https://${host}/PC/${input.year}/Shopping/${input.carrier==='Highmark'?'Home':'PlanList'}${input.carrier==='Excellus BlueCross BlueShield'?'?zip='+input.zip:''}`;
  const options={headless:true};
  if(process.env.SHOPPING_CHROMIUM_PATH)options.executablePath=process.env.SHOPPING_CHROMIUM_PATH;
  // --no-sandbox is enabled only for explicitly configured container runtimes.
  if(process.env.SHOPPING_CHROMIUM_NO_SANDBOX==='1')options.args=['--no-sandbox'];
  const browser=await chromium.launch(options);
  let finish;const received=new Promise(resolve=>finish=resolve);
  try{
    const context=await browser.newContext({...(process.env.HTTPS_PROXY?{proxy:{server:process.env.HTTPS_PROXY}}:{})});
    const page=await context.newPage();page.setDefaultTimeout(30000);
    page.on('response',async response=>{
      const u=new URL(response.url());
      if(u.hostname!=='www.drxwebservices.com'||u.pathname!==`/spa${input.year}/v1/plans`||response.request().method()!=='POST')return;
      try{
        const request=JSON.parse(response.request().postData());
        if(request.demographics?.zip!==input.zip||request.demographics?.fips!==input.county||String(request.search?.year)!==String(input.year)){
          finish({error:'county_mismatch',message:'The public form selected a different county. Results withheld; confirm the county on the carrier site.'});return;
        }
        if(!response.ok()){finish({error:'unavailable',message:'Public shopping request failed.'});return;}
        const data=await response.json();
        if(!Array.isArray(data.data)||data.totalCount!==data.data.length){finish({error:'incomplete',message:'The shopping site returned incomplete or changed plan results.'});return;}
        // Keep only plan facts needed by the dashboard; omit anonymous session
        // tokens, marketing history, and pharmacy/provider/medication data.
        const keys=['id','contractId','planId','segmentId','planYear','planName','carrierName','annualPlanPremium','planType','planTypeAbbreviation','planSNPCategories','hasDrugCoverage'];
        finish({source_url:source,plans:data.data.map(p=>Object.fromEntries(keys.map(k=>[k,p[k]])))});
      }catch{finish({error:'response_changed',message:'The public shopping result could not be verified.'});}
    });
    await page.goto(source,{waitUntil:'domcontentloaded',timeout:45000});
    if(input.carrier!=='Excellus BlueCross BlueShield'){
    const field=page.locator(input.carrier==='Molina'?'#demographic_input_modal':'#demographic_input');
    await field.fill(input.zip);
    // Wait for the public form's ZIP resolution before submitting it.
    await page.waitForTimeout(1800);
    await page.getByRole('button',{name:input.carrier==='Molina'?'Shop for plans':'Browse plans',exact:true}).click();
    }
    let timer;const result=await Promise.race([received,new Promise(resolve=>{timer=setTimeout(()=>resolve({error:'unavailable',message:'Public shopping timed out. No plan availability determined.'}),30000);})]);clearTimeout(timer);
    process.stdout.write(JSON.stringify(result));
  }finally{await browser.close();}
}
main().catch(()=>{process.stdout.write(JSON.stringify({error:'unavailable',message:'Public shopping browser unavailable. Check browser setup or retry.'}));process.exitCode=1;});
