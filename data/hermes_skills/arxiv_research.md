---
name: arxiv_research
description: Search ArXiv preprints, download abstracts, parse LaTeX math equations, and summarize frontier machine learning research.
version: 1.0.0
author: nous_research
category: research
risk_level: low
metadata:
  skills: [arxiv_research, paper_search, literature_review, ml_research]
---

# ArXiv Research & Paper Synthesis Skill

Use this skill when tasked with literature reviews, discovering state-of-the-art papers, or extracting math formulations from ArXiv.

## Procedure

1. **Query Formulation**:
   Construct focused queries with authors, keywords, and publication categories (e.g. `cs.LG`, `cs.AI`, `cs.CL`).
   
2. **API Endpoint & Extraction**:
   Use `web_extract` or HTTP GET against the ArXiv API:
   ```bash
   http://export.arxiv.org/api/query?search_query=all:hermes+agent&start=0&max_results=5
   ```

3. **Synthesis & Extraction**:
   - Extract primary claims, key benchmark comparisons, and dataset details.
   - Summarize algorithmic innovations in bullet points.
   - Retain mathematical notation in LaTeX markdown format (`$E = mc^2$`).

4. **Output Format**:
   Deliver a structured executive summary with title, author list, ArXiv ID link, and core architecture diagram.
