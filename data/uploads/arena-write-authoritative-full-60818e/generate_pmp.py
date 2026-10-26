import json
from pathlib import Path

# Paths
base_dir = Path(r'D:\projects\aiagent\data\uploads\arena-write-authoritative-full-60818e')
baseline_path = base_dir / 'baseline_project_parameters.json'
output_docx = base_dir / 'pmp.docx'
deliverables_json = base_dir / 'deliverables_table.json'
compliance_json = base_dir / 'compliance_matrix.json'

# Load baseline
with open(baseline_path, 'r', encoding='utf-8') as f:
    baseline = json.load(f)

# Generate deliverables table
milestones = baseline.get('ImplementationMilestones', [])
owner_map = {
    'Project charter': 'Product Owner',
    'Stakeholder register': 'Engineering Lead',
    'Requirements spec': 'Product Owner',
    'Architecture diagram': 'Engineering Lead',
    'Risk register': 'Compliance Manager',
    'Microservices': 'Engineering Lead',
    'CI/CD pipeline': 'Operations Manager',
    'Security baseline': 'Security Officer',
    'Compliance engine': 'Compliance Manager',
    'Audit logs': 'Security Officer',
    'DLP integration': 'Security Officer',
    'Unit/integration tests': 'Engineering Lead',
    'Penetration test report': 'Security Officer',
    'User acceptance testing': 'Product Owner',
    'Production rollout': 'Operations Manager',
    'Monitoring dashboards': 'Operations Manager',
    'Training materials': 'Product Owner'
}

deliverables = []
for m in milestones:
    phase = m.get('Phase')
    start = m.get('StartDate')
    end = m.get('EndDate')
    dlist_raw = m.get('Deliverables', '')
    # Split by comma or space
    if ',' in dlist_raw:
        dlist = [d.strip() for d in dlist_raw.split(',') if d.strip()]
    else:
        dlist = [d.strip() for d in dlist_raw.split(' ') if d.strip()]
    for d in dlist:
        owner = owner_map.get(d, 'Engineering Lead')
        acceptance = f"Deliverable {d} meets defined requirements and is approved by stakeholders"
        deliverables.append({
            'deliverable': d,
            'owner': owner,
            'due_date': end,
            'acceptance_criteria': acceptance,
            'status': 'Not Started'
        })

# Write JSON files
with open(deliverables_json, 'w', encoding='utf-8') as f:
    json.dump(deliverables, f, indent=2)

# Generate compliance matrix
domains = baseline.get('RegulatoryDomains', [])
controls = [
    'TLS 1.3 everywhere',
    'OAuth2 + OIDC authentication',
    'Hardware Security Module (HSM) for key storage',
    'Encrypted at rest using AES‑256',
    'Regular penetration testing',
    'Incident response plan with SANS guidelines',
    'Data loss prevention (DLP) integration'
]
control_to_deliverable = {
    'TLS 1.3 everywhere': ['Security baseline'],
    'OAuth2 + OIDC authentication': ['Security baseline'],
    'Hardware Security Module (HSM) for key storage': ['Compliance engine', 'Audit logs'],
    'Encrypted at rest using AES‑256': ['Microservices', 'Compliance engine'],
    'Regular penetration testing': ['Penetration test report'],
    'Incident response plan with SANS guidelines': ['Security baseline'],
    'Data loss prevention (DLP) integration': ['DLP integration']
}
control_to_section = {
    'TLS 1.3 everywhere': 'Security Controls',
    'OAuth2 + OIDC authentication': 'Security Controls',
    'Hardware Security Module (HSM) for key storage': 'Security Controls',
    'Encrypted at rest using AES‑256': 'Security Controls',
    'Regular penetration testing': 'Security & Compliance Strategy',
    'Incident response plan with SANS guidelines': 'Security & Compliance Strategy',
    'Data loss prevention (DLP) integration': 'Security & Compliance Strategy'
}

compliance_matrix = []
for domain in domains:
    for control in controls:
        deliverables_list = control_to_deliverable.get(control, [])
        section = control_to_section.get(control, '')
        compliance_matrix.append({
            'domain': domain,
            'control': control,
            'deliverables': ', '.join(deliverables_list) if deliverables_list else '',
            'pmp_section': section
        })

with open(compliance_json, 'w', encoding='utf-8') as f:
    json.dump(compliance_matrix, f, indent=2)

# Create Word document with tables using python-docx
try:
    from docx import Document
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'python-docx'])
    from docx import Document

# Create document
from docx.shared import Inches

doc = Document()
doc.add_heading('Project Management Plan', level=1)

# Deliverables Table section

doc.add_heading('Deliverables Table', level=2)
headers = ['Deliverable', 'Owner', 'Due Date', 'Acceptance Criteria', 'Status']
table = doc.add_table(rows=1, cols=len(headers))
hdr_cells = table.rows[0].cells
for i, h in enumerate(headers):
    hdr_cells[i].text = h
for d in deliverables:
    row_cells = table.add_row().cells
    row_cells[0].text = d['deliverable']
    row_cells[1].text = d['owner']
    row_cells[2].text = d['due_date']
    row_cells[3].text = d['acceptance_criteria']
    row_cells[4].text = d['status']

# Compliance Matrix section

doc.add_heading('Compliance Matrix', level=2)
headers_cm = ['Domain', 'Control', 'Deliverables', 'PMP Section']
table_cm = doc.add_table(rows=1, cols=len(headers_cm))
hdr_cells_cm = table_cm.rows[0].cells
for i, h in enumerate(headers_cm):
    hdr_cells_cm[i].text = h
for cm in compliance_matrix:
    row_cells = table_cm.add_row().cells
    row_cells[0].text = cm['domain']
    row_cells[1].text = cm['control']
    row_cells[2].text = cm['deliverables']
    row_cells[3].text = cm['pmp_section']

# Save document
output_docx.parent.mkdir(parents=True, exist_ok=True)
doc.save(output_docx)
print('Generated deliverables_table.json, compliance_matrix.json, and updated pmp.docx')