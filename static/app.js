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
    const response = await fetch('/api/plans?' + params, {signal});
    if (!response.ok) throw new Error('Request failed');
    const data = await response.json();
    results.replaceChildren(element('h2', `${data.plans.length} plan results`), element('p',data.notice));
    if (!data.plans.length) results.append(element('p','No imported plans match this location and filters. This does not establish that no plans are available.'));
    if (data.truncated) results.append(element('p','Showing the first 200 results. Narrow your filters.'));
    for (const plan of data.plans) {
      const card = element('article',undefined,'plan');
      card.append(element('span',plan.business,'badge'),
        element('h3',plan.name), element('p',`${plan.carrier} · ${plan.year} · ${plan.county}, ${plan.state} · ZIP ${plan.zip}`),
        element('p',`Monthly premium: ${plan.premium || 'unverified'}`),
        element('p',plan.benefits || 'Benefits unverified'));
      source(card,plan.source_url,plan.verified_on);
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
        section.append(element('small','Confirm the exact medication strength/form or provider office.'));
        card.append(section);
      }
      results.append(card);
    }
  } catch (error) {
    if (error.name !== 'AbortError') results.replaceChildren(element('p','Search failed. Please retry.'));
  } finally { if (!signal.aborted) results.setAttribute('aria-busy','false'); }
});
