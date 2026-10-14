const form = document.querySelector('#search');
const results = document.querySelector('#results');
const state = document.querySelector('#state');
for (const name of ['NC','SC','GA','FL','AL','TN','VA','KY','LA','TX','OH','PA','DE','MI','NY']) {
  const option = document.createElement('option'); option.textContent = name; state.append(option);
}
function element(tag, text, className) {
  const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
  if (className) node.className = className; return node;
}
function source(parent, url, checked) {
  if (url && /^https:\/\//i.test(url)) {
    const link = element('a', 'Official source'); link.href = url; link.target = '_blank';
    link.rel = 'noopener noreferrer'; parent.append(link);
  }
  parent.append(element('p', `Last verified: ${checked || 'not verified'}`, 'metadata'));
}
let request;
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (request) request.abort(); request = new AbortController();
  const signal = request.signal;
  const params = new URLSearchParams(new FormData(form));
  if (!params.get('zip')) {
    results.replaceChildren(element('p','Enter a five-digit ZIP code to search official plans.')); return;
  }
  results.setAttribute('aria-busy','true'); results.replaceChildren(element('p','Searching…'));
  try {
    const endpoint = params.get('source') === 'devoted' ? '/api/devoted' : '/api/plans';
    const response = await fetch(endpoint + '?' + params, {signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Search failed. Please retry.');
    if (data.counties) {
      const county = document.querySelector('#county');
      county.replaceChildren();
      const placeholder = element('option','Select county'); placeholder.value = ''; county.append(placeholder);
      for (const c of data.counties) { const o = element('option',c.name); o.value=c.code; county.append(o); }
      county.value = data.selected_county || '';
      if (data.needs_county) county.focus();
    }
    results.replaceChildren(element('h2', `${data.plans.length} plan results`), element('p',data.notice));
    if (!data.plans.length && !data.counties) results.append(element('p','No imported plans match this location and filters. This does not establish that no plans are available.'));
    if (data.truncated) results.append(element('p','Some searches are incomplete or limited. Narrow your filters; missing matches remain unverified.'));
    for (const plan of data.plans) {
      const card = element('article',undefined,'plan');
      card.append(element('span',plan.business,'badge'),
        element('h3',plan.name), element('p',`${plan.carrier} · ${plan.year} · ${plan.county}, ${plan.state} · ZIP ${plan.zip}`),
        element('p',`Monthly premium: ${plan.premium || 'unverified'}`),
        element('p',plan.benefits || 'Benefits unverified'));
      source(card,plan.source_url,plan.verified_on);
      if (plan.document_excerpt) card.append(element('small','Excerpt from the Summary of Benefits; consult the complete document for conditions.'));
      for (const doc of plan.documents || []) {
        const section = element('details');
        section.append(element('summary', ({benefits:'Summary of Benefits',evidence:'Evidence of Coverage',formulary:'2027 Formulary'})[doc.kind]));
        source(section,doc.url,doc.retrieved_at.slice(0,10));
        const button = element('button','Read imported text'); button.type='button';
        button.addEventListener('click',async () => {
          button.disabled=true;
          try {
            const r = await fetch('/api/document?'+new URLSearchParams({url:doc.url}));
            if (!r.ok) throw new Error('Document unavailable');
            const d = await r.json(); section.append(element('pre',d.text,'document-text')); button.remove();
          } catch(e) { button.disabled=false; button.textContent='Retry loading text'; }
        });
        section.append(button); card.append(section);
      }
      for (const check of plan.checks) {
        const section = element('div',undefined,'check');
        section.append(element('strong',`${check.kind === 'medication' ? 'Medication' : 'Provider'}: ${check.query}`));
        if (!check.matches.length) section.append(element('p','Unverified — no matching coverage record.','badge unverified'));
        for (const match of check.matches) {
          section.append(element('p',`${match.name} · ${match.detail}`),
            element('span',match.status,'badge ' + match.status.replaceAll(' ','-')),
            element('p',match.restrictions || 'No restrictions recorded; confirm with the source.'));
          source(section,match.source_url,match.verified_on);
        }
        section.append(element('small',check.kind === 'medication' ? 'Up to five text excerpts shown; these may include index entries. Read the original formulary to confirm coverage.' : 'Confirm the exact provider identity and office.'));
        card.append(section);
      }
      results.append(card);
    }
  } catch (error) {
    if (error.name !== 'AbortError') results.replaceChildren(element('p',error.message || 'Search failed. Please retry.'));
  } finally { if (!signal.aborted) results.setAttribute('aria-busy','false'); }
});

form.elements.zip.addEventListener('input', () => { document.querySelector('#county').replaceChildren(element('option','Choose after ZIP lookup')); form.elements.county.firstChild.value=''; });
