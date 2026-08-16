#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/data"
SKILLS_ROOT="${DATA_DIR}/skills"
mkdir -p "${SKILLS_ROOT}/research"

cat > "${SKILLS_ROOT}/research/web-research/SKILL.md" <<'SKILL'
---
name: web-research
description: General internet research using live web search and page retrieval, with source tracing and freshness awareness.
version: 1.0.0
category: research
tags: [web, search, research, sources, current-information]
platforms: [linux, macos, windows]
status: published
confidence: 0.95
source: imported
---

## When to Use
Use when the user asks for current information, investigation, fact checking, comparisons, unfamiliar topics, or information that may have changed since model training.

## Procedure
1. Translate the request into one or more focused search queries.
2. Use `web_search` for discovery rather than guessing URLs.
3. Prefer primary sources, official documentation, original datasets, regulators, professional bodies, and reputable reporting.
4. Use `web_fetch` on the strongest sources when the search result alone is insufficient.
5. Cross-check important claims against at least two independent sources when practical.
6. Track the URL/title for every substantive claim.
7. Clearly distinguish established facts, source-reported claims, inference, and uncertainty.
8. For time-sensitive questions, favour recent sources and explicitly state the relevant date.

## Pitfalls
- Do not treat search snippets as authoritative evidence when the underlying page can be fetched.
- Do not invent citations or URLs.
- Do not present stale information as current.
- Do not silently turn an inference into a sourced fact.

## Verification
- Every important factual claim has a traceable source.
- Time-sensitive claims have an appropriate publication/update date.
- Conflicting sources are identified rather than silently averaged.
SKILL

cat > "${SKILLS_ROOT}/research/academic-research/SKILL.md" <<'SKILL'
---
name: academic-research
description: Scholarly research across disciplines using academic indexes, publisher pages, repositories and primary literature.
version: 1.0.0
category: research
tags: [academic, scholarly, papers, literature, research]
platforms: [linux, macos, windows]
status: published
confidence: 0.98
source: imported
---

## When to Use
Use for questions asking what the academic literature says, research evidence, papers, mechanisms, theoretical debates, prevalence, efficacy, systematic reviews, meta-analyses, or scholarly consensus.

## Procedure
1. Identify the exact research question, population, intervention/exposure, comparator and outcome when applicable.
2. Search broadly first using `web_search`, then narrow with scholarly sources.
3. For biomedical/health topics, prioritise PubMed/Europe PMC and guideline bodies.
4. For broad multidisciplinary literature, use Semantic Scholar, Crossref, institutional repositories, and publisher pages where available.
5. Prefer systematic reviews and meta-analyses for broad efficacy/prevalence questions, then inspect important primary studies.
6. Retrieve abstracts/full text with `web_fetch` when legally accessible.
7. Extract study design, sample, intervention/exposure, comparator, measures, main results, limitations and publication year.
8. Separate peer-reviewed articles from preprints, conference material, theses and commentary.
9. Check whether newer studies materially change the conclusion.
10. Synthesize the evidence rather than listing papers without interpretation.
11. Give citations with DOI, PMID, publisher or repository URL where available.

## Pitfalls
- A single study is not a consensus.
- Correlation is not causation.
- Do not call a preprint peer-reviewed.
- Do not infer clinical effectiveness from mechanistic or feasibility work alone.
- Do not assume a paper's conclusion is supported without checking methods/results when those are available.

## Verification
- Each major conclusion maps to one or more identifiable scholarly sources.
- Study designs and evidence levels are correctly described.
- Publication dates and peer-review status are clear.
- Contradictory or low-quality evidence is explicitly noted.
SKILL

cat > "${SKILLS_ROOT}/research/pubmed-research/SKILL.md" <<'SKILL'
---
name: pubmed-research
description: Targeted biomedical and health research using PubMed and Europe PMC, including article metadata and accessible abstracts/full text.
version: 1.0.0
category: research
tags: [pubmed, europe-pmc, biomedical, health, medicine]
status: published
confidence: 0.98
source: imported
---

## When to Use
Use for biomedical, psychological, psychiatric, clinical, public-health, neuroscience and health research where indexed scholarly literature is relevant.

## Procedure
1. Build a focused query from condition/topic + population + intervention/exposure + outcome.
2. Search PubMed and Europe PMC through live web search.
3. Prefer systematic reviews, meta-analyses, RCTs and major cohort studies according to the question.
4. Record PMID, DOI, journal, year and study design when available.
5. Retrieve the abstract or accessible full text before making detailed claims.
6. Compare recent evidence with landmark studies when the topic has a long history.
7. Report limitations, heterogeneity and applicability to the user's population.

## Pitfalls
- PubMed indexing does not mean an article is high quality.
- Do not confuse an abstract conclusion with the full study findings.
- Avoid extrapolating from animals, healthy volunteers or different populations without saying so.

## Verification
- PMID/DOI or another stable scholarly identifier is captured where possible.
- Evidence level and population are stated.
SKILL

cat > "${SKILLS_ROOT}/research/literature-review/SKILL.md" <<'SKILL'
---
name: literature-review
description: Structured literature review workflow that moves from search strategy through screening, extraction, synthesis and gaps.
version: 1.0.0
category: research
tags: [literature-review, systematic-review, scoping-review, synthesis]
status: published
confidence: 0.96
source: imported
---

## When to Use
Use when the user asks for a literature review, state of the evidence, research landscape, evidence map, or comprehensive academic overview.

## Procedure
1. Define the review question and scope.
2. Generate synonymous and controlled-vocabulary search terms.
3. Search multiple relevant academic sources rather than one index.
4. Screen titles/abstracts for direct relevance.
5. Group included studies by design, population, intervention/exposure and outcome.
6. Extract consistent fields: year, design, N, population, methods, findings, limitations.
7. Identify agreement, disagreement, methodological weaknesses and research gaps.
8. Distinguish a narrative review from a systematic/scoping review unless a formal protocol was actually followed.
9. Produce a concise evidence synthesis with a source list.

## Pitfalls
- Do not claim systematic-review completeness without a reproducible systematic search/screening process.
- Avoid cherry-picking studies that support the desired conclusion.
- Do not equate number of studies with quality of evidence.

## Verification
- Search scope is explicit.
- Inclusion logic is transparent.
- Major conclusions reflect the body of evidence rather than isolated findings.
SKILL

cat > "${SKILLS_ROOT}/research/evidence-synthesis/SKILL.md" <<'SKILL'
---
name: evidence-synthesis
description: Evaluate and synthesise research evidence by study design, bias, consistency, precision and applicability.
version: 1.0.0
category: research
tags: [evidence, synthesis, critical-appraisal, bias, causality]
status: published
confidence: 0.97
source: imported
---

## When to Use
Use when the user asks whether evidence supports a claim, how strong the evidence is, or what can reasonably be concluded from several studies.

## Procedure
1. Identify the claim being tested.
2. Classify the evidence by design and relevance.
3. Examine sample size, controls, measurement quality, confounding, attrition and analysis where reported.
4. Look for replication, consistency and precision.
5. Distinguish statistical significance from practical/clinical significance.
6. Identify publication, selection and reporting biases where relevant.
7. Synthesize the direction and strength of evidence.
8. State what remains uncertain.

## Pitfalls
- Do not use study prestige as a substitute for appraisal.
- Do not interpret p-values as effect size or clinical importance.
- Do not infer causality from observational associations without appropriate qualification.

## Verification
- Evidence strength is justified by design and methodological quality.
- Uncertainty is retained rather than hidden.
SKILL

cat > "${SKILLS_ROOT}/research/guideline-research/SKILL.md" <<'SKILL'
---
name: guideline-research
description: Find and compare current professional, clinical and governmental guidelines, recommendations and standards.
version: 1.0.0
category: research
tags: [guidelines, nice, nhs, professional-bodies, standards]
status: published
confidence: 0.98
source: imported
---

## When to Use
Use when the user asks what clinicians, regulators, governments, professional bodies or standards organisations currently recommend.

## Procedure
1. Identify the jurisdiction and professional context.
2. Search the issuing body's official site first.
3. Prefer the current guideline/version over archived pages.
4. Record publication/update date and issuing organisation.
5. Retrieve the recommendation text and relevant evidence sections when accessible.
6. Compare recommendations across bodies only after confirming they address the same population/context.
7. Distinguish mandatory standards from guidance and expert consensus.

## Pitfalls
- Do not treat an old guideline as current.
- Do not generalise one country's guidance to another jurisdiction.
- Do not present professional guidance as law unless it actually has legal status.

## Verification
- Issuing organisation and version/date are recorded.
- Recommendations are linked to official sources.
SKILL

cat > "${SKILLS_ROOT}/research/source-verification/SKILL.md" <<'SKILL'
---
name: source-verification
description: Verify claims by tracing them to primary sources and checking dates, provenance, identifiers and corroboration.
version: 1.0.0
category: research
tags: [fact-checking, provenance, verification, citations]
status: published
confidence: 0.98
source: imported
---

## When to Use
Use when a claim is important, disputed, surprising, highly specific, or likely to be repeated as fact.

## Procedure
1. Find the original source behind the claim.
2. Open the source rather than relying on a snippet or secondary summary.
3. Check author/organisation, date, context and exact wording.
4. For research claims, inspect the cited paper and its study design.
5. Seek an independent corroborating source where practical.
6. Report discrepancies explicitly.

## Pitfalls
- Do not cite a source that does not actually support the sentence.
- Do not use search-engine snippets as the evidence itself.
- Do not silently repair contradictory evidence.

## Verification
- Source provenance is clear.
- Claim and citation actually correspond.
SKILL

cat > "${SKILLS_ROOT}/research/open-access-finder/SKILL.md" <<'SKILL'
---
name: open-access-finder
description: Locate legally accessible versions of scholarly work through repositories, PubMed Central, Europe PMC and author/institutional copies.
version: 1.0.0
category: research
tags: [open-access, papers, repositories, full-text]
status: published
confidence: 0.97
source: imported
---

## When to Use
Use when a useful paper is found but the publisher page is paywalled or incomplete.

## Procedure
1. Record the DOI/title/authors.
2. Search the title/DOI in Europe PMC, PubMed Central and institutional repositories.
3. Search the author's or institution's repository when appropriate.
4. Prefer the publisher's open-access version or recognised repository copy.
5. Clearly label preprints and accepted manuscripts when they are not the final published version.
6. Do not bypass paywalls, access controls or DRM.

## Pitfalls
- Do not pretend a search result is full text when only metadata is accessible.
- Do not use pirated copies.

## Verification
- The accessible copy's provenance/version is identified.
SKILL

cat > "${SKILLS_ROOT}/research/citation-manager/SKILL.md" <<'SKILL'
---
name: citation-manager
description: Produce traceable citations and bibliographies from web and scholarly research without inventing references.
version: 1.0.0
category: research
tags: [citations, bibliography, doi, references, academic-writing]
status: published
confidence: 0.98
source: imported
---

## When to Use
Use whenever research findings are presented, especially academic, clinical, scientific or policy claims.

## Procedure
1. Capture title, authors, year, journal/organisation and DOI/PMID/URL where available.
2. Keep source identity attached to the claim during synthesis.
3. Prefer stable identifiers over fragile search-result URLs.
4. Format references in the style requested by the user.
5. If a bibliographic field cannot be verified, omit it or mark it unavailable rather than guessing.

## Pitfalls
- Never fabricate DOI, PMID, volume, pages or author lists.
- Do not cite a review as though it were the original study.

## Verification
- Every reference resolves to a real source.
- No bibliographic field was invented.
SKILL

printf '\n========================================\n'
printf 'AERITH INTERNET + ACADEMIC RESEARCH SKILLS INSTALLED\n'
printf '========================================\n'
find "${SKILLS_ROOT}/research" -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort
printf '\nRestart Odysseus after running this script so the skills index is refreshed.\n'
