"""Read HealthSpring's two-column formulary without mixing neighboring drugs."""
import re


def parse_formulary(text):
    rows = []
    for page_number, page in enumerate(text.split('\f'), 1):
        lines = page.splitlines()
        header = next((line for line in lines if line.count('Drug Name') == 2
                       and line.count('Drug Tier') == 2), None)
        if not header:
            continue
        split = header.index('Drug Name', header.index('Drug Name') + 1)
        for start, end in [(0, split), (split, len(header) + 30)]:
            column_header = header[start:end]
            cells = [line[start:end].replace('\ufeff', '') for line in lines[lines.index(header) + 2:]]
            pattern = r'^(.*?)\s{2,}([1-5])(?:\s+(.*))?$'
            matches = [re.match(pattern, cell.rstrip()) for cell in cells]
            restriction_positions = [match.start(3) for match in matches if match and match[3]]
            restriction_start = min(restriction_positions) if restriction_positions else column_header.index('Requirements/')
            tier_start = min(match.start(2) for match in matches if match)
            current = None
            for line in lines[lines.index(header) + 2:]:
                if line.strip().startswith(('CAPITALIZED =', 'You can find information')):
                    break
                cell = line[start:end].replace('\ufeff', '')
                match = re.match(pattern, cell.rstrip())
                name = match[1].strip() if match else cell[:tier_start].strip()
                restriction = (match[3] or '').strip() if match else cell[restriction_start:].strip()
                if match:
                    if current:
                        rows.append(current)
                    current = {'name': name, 'tier': match[2], 'restrictions': restriction,
                               'page': page_number}
                elif current:
                    # Section headings have no tier; wrapped drug names stay with their row.
                    heading = name.isupper() and not re.search(
                        r'\d|ORAL|TABLET|CAPSULE|SOLUTION|SUSPENSION|INJECTION|RECON|TOPICAL|'
                        r'INHAL|PATCH|CREAM|OINTMENT|SYRUP|POWDER|SPRAY|SURECLICK', name)
                    if heading and not restriction:
                        rows.append(current)
                        current = None
                    else:
                        if name:
                            current['name'] = (current['name'] + ' ' + name).strip()
                        if restriction:
                            current['restrictions'] = (current['restrictions'] + ' ' + restriction).strip()
            if current:
                rows.append(current)
    return [row for row in rows if row['name']]
