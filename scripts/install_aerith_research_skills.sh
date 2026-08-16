#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT}/data"
SKILLS_ROOT="${DATA_DIR}/skills"
mkdir -p "${SKILLS_ROOT}/research"

make_skill() {
  local name="$1" description="$2" tags="$3" when="$4" procedure="$5" pitfalls="$6" verification="$7"
  local dir="${SKILLS_ROOT}/research/${name}"
  mkdir -p "$dir"
  cat > "${dir}/SKILL.md" <<SKILL
---
name: ${name}
description: ${description}
version: 1.0.0
category: research
tags: [${tags}]
status: published
confidence: 0.98
source: imported
---

## When to Use
${when}

## Procedure
${procedure}

## Pitfalls
${pitfalls}

## Verification
${verification}
SKILL
}

make_skill "web-research" "General internet research using live web search and page retrieval, with source tracing and freshness awareness." "web, search, research, sources, current-information" \
"Use when the user asks for current information, investigation, fact checking, comparisons, unfamiliar topics, or information that may have changed since model training." \
"1. Translate the request into focused search queries.
2. Use \`web_search\` for discovery rather than guessing URLs.
3. Prefer primary sources, official documentation, original datasets, regulators, professional bodies, and reputable reporting.
4. Use \`web_fetch\` on the strongest sources when search results alone are insufficient.
5. Cross-check important claims against independent sources when practical.
6. Track the URL/title for every substantive claim.
7. Distinguish facts, source-reported claims, inference, and uncertainty.
8. For time-sensitive questions, favour recent sources and state the relevant date." \
"- Do not treat search snippets as authoritative evidence when the underlying page can be fetched.
- Do not invent citations or URLs.
- Do not present stale information as current.
- Do not silently turn inference into sourced fact." \
"- Important factual claims have traceable sources.
- Time-sensitive claims have appropriate dates.
- Conflicting sources are identified rather than silently averaged."

make_skill "academic-research" "Scholarly research across disciplines using academic indexes, publisher pages, repositories and primary literature." "academic, scholarly, papers, literature, research" \
"Use for questions about academic evidence, papers, mechanisms, theoretical debates, prevalence, efficacy, systematic reviews, meta-analyses, or scholarly consensus." \
"1. Define the research question, population, intervention/exposure, comparator and outcome where applicable.
2. Search broadly with \`web_search\`, then narrow to scholarly sources.
3. For biomedical and health topics, prioritise PubMed/Europe PMC and guideline bodies.
4. For multidisciplinary work, use Semantic Scholar, Crossref, institutional repositories and publisher pages where available.
5. Prefer systematic reviews/meta-analyses for broad questions, then inspect important primary studies.
6. Retrieve abstracts/full text with \`web_fetch\` when legally accessible.
7. Extract design, sample, methods, measures, results, limitations and year.
8. Separate peer-reviewed articles from preprints, theses and commentary.
9. Check newer evidence for material changes.
10. Synthesize evidence rather than merely listing papers.
11. Give DOI, PMID, publisher or repository identifiers where available." \
"- A single study is not a consensus.
- Correlation is not causation.
- Do not call a preprint peer-reviewed.
- Do not infer clinical effectiveness from mechanistic or feasibility work alone.
- Do not assume a paper's conclusion is supported without checking methods/results when available." \
"- Major conclusions map to identifiable scholarly sources.
- Study designs and evidence levels are correct.
- Publication dates and peer-review status are clear.
- Contradictory or low-quality evidence is noted."

make_skill "pubmed-research" "Targeted biomedical and health research using PubMed and Europe PMC, including article metadata and accessible abstracts/full text." "pubmed, europe-pmc, biomedical, health, medicine" \
"Use for biomedical, psychological, psychiatric, clinical, public-health, neuroscience and health research." \
"1. Build focused queries from topic + population + intervention/exposure + outcome.
2. Search PubMed and Europe PMC through live web search.
3. Prefer systematic reviews, meta-analyses, RCTs and major cohort studies according to the question.
4. Record PMID, DOI, journal, year and study design.
5. Retrieve abstracts or accessible full text before making detailed claims.
6. Compare recent evidence with landmark studies where useful.
7. Report limitations, heterogeneity and applicability to the population." \
"- PubMed indexing does not imply high quality.
- Do not confuse an abstract conclusion with full study findings.
- Avoid unqualified extrapolation across populations." \
"- PMID/DOI or another stable identifier is captured where possible.
- Evidence level and population are stated."

make_skill "literature-review" "Structured literature review workflow from search strategy through screening, extraction, synthesis and gaps." "literature-review, systematic-review, scoping-review, synthesis" \
"Use for literature reviews, evidence landscapes, evidence maps and comprehensive academic overviews." \
"1. Define the review question and scope.
2. Generate synonyms and controlled-vocabulary terms.
3. Search multiple relevant academic sources.
4. Screen titles/abstracts for direct relevance.
5. Group studies by design, population, intervention/exposure and outcome.
6. Extract year, design, N, population, methods, findings and limitations.
7. Identify agreement, disagreement, weaknesses and gaps.
8. Distinguish narrative reviews from systematic/scoping reviews unless a formal protocol was followed.
9. Produce a synthesis with a source list." \
"- Do not claim systematic completeness without a reproducible systematic process.
- Avoid cherry-picking.
- Study count is not study quality." \
"- Scope is explicit.
- Inclusion logic is transparent.
- Conclusions reflect the evidence base."

make_skill "evidence-synthesis" "Evaluate and synthesise research evidence by study design, bias, consistency, precision and applicability." "evidence, synthesis, critical-appraisal, bias, causality" \
"Use when the user asks whether evidence supports a claim or how strong the evidence is." \
"1. Identify the claim.
2. Classify evidence by design and relevance.
3. Examine sample size, controls, measurement, confounding, attrition and analysis where reported.
4. Look for replication, consistency and precision.
5. Distinguish statistical from practical/clinical significance.
6. Identify publication, selection and reporting biases where relevant.
7. Synthesize direction and strength.
8. State uncertainty." \
"- Do not substitute prestige for appraisal.
- Do not treat p-values as effect size or clinical importance.
- Do not infer causality from observational associations without qualification." \
"- Evidence strength is justified by design and quality.
- Uncertainty is retained."

make_skill "guideline-research" "Find and compare current professional, clinical and governmental guidelines, recommendations and standards." "guidelines, nice, nhs, professional-bodies, standards" \
"Use when the user asks what clinicians, regulators, governments, professional bodies or standards organisations currently recommend." \
"1. Identify jurisdiction and professional context.
2. Search the issuing body's official site first.
3. Prefer the current guideline/version.
4. Record publication/update date and issuing organisation.
5. Retrieve recommendation and relevant evidence sections where accessible.
6. Compare bodies only when population/context are comparable.
7. Distinguish standards, guidance and expert consensus." \
"- Do not treat old guidance as current.
- Do not generalise across jurisdictions.
- Do not present guidance as law unless it has legal status." \
"- Issuing organisation and version/date are recorded.
- Recommendations link to official sources."

make_skill "source-verification" "Verify claims by tracing them to primary sources and checking dates, provenance, identifiers and corroboration." "fact-checking, provenance, verification, citations" \
"Use when a claim is important, disputed, surprising, highly specific, or likely to be repeated as fact." \
"1. Find the original source.
2. Open it rather than relying on a snippet.
3. Check author/organisation, date, context and exact wording.
4. For research claims, inspect the cited paper and study design.
5. Seek independent corroboration where practical.
6. Report discrepancies explicitly." \
"- Do not cite a source that does not support the sentence.
- Do not use search snippets as evidence itself.
- Do not silently repair contradictory evidence." \
"- Source provenance is clear.
- Claim and citation correspond."

make_skill "open-access-finder" "Locate legally accessible versions of scholarly work through repositories, PubMed Central, Europe PMC and author/institutional copies." "open-access, papers, repositories, full-text" \
"Use when a useful paper is found but the publisher page is paywalled or incomplete." \
"1. Record DOI/title/authors.
2. Search title/DOI in Europe PMC, PubMed Central and institutional repositories.
3. Search author/institution repositories when appropriate.
4. Prefer publisher OA versions or recognised repository copies.
5. Label preprints and accepted manuscripts clearly.
6. Never bypass paywalls, access controls or DRM." \
"- Do not pretend metadata is full text.
- Do not use pirated copies." \
"- Accessible copy provenance/version is identified."

make_skill "citation-manager" "Produce traceable citations and bibliographies from web and scholarly research without inventing references." "citations, bibliography, doi, references, academic-writing" \
"Use whenever research findings are presented, especially academic, clinical, scientific or policy claims." \
"1. Capture title, authors, year, journal/organisation and DOI/PMID/URL where available.
2. Keep source identity attached to claims during synthesis.
3. Prefer stable identifiers.
4. Format references in the requested style.
5. If a field cannot be verified, omit it or mark it unavailable rather than guessing." \
"- Never fabricate DOI, PMID, volume, pages or author lists.
- Do not cite a review as though it were the original study." \
"- Every reference resolves to a real source.
- No bibliographic field was invented."

printf '\n========================================\n'
printf 'AERITH INTERNET + ACADEMIC RESEARCH SKILLS INSTALLED\n'
printf '========================================\n'
find "${SKILLS_ROOT}/research" -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort
printf '\nRestart Odysseus after running this script so the skills index is refreshed.\n'
