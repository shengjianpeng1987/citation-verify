# Citation verification report

**Source:** `/sessions/jolly-dreamy-bohr/mnt/citation verify/citation-verify/tests/smoke.docx`
**Total citations checked:** 4
**Summary:** hallucinated: 2, valid: 2

## At a glance

| # | Label | Citation (abbreviated) | Replacement |
|---|-------|------------------------|-------------|
| 1 | OK valid | Attention is all you need | — |
| 2 | OK valid | Highly accurate protein structure prediction with AlphaFold | — |
| 3 | FAKE hallucinated | Quantum-entangled attention for zero-shot generalization in Martian robotics | skipped |
| 4 | FAKE hallucinated | Consciousness-preserving large language models: a telepathic transformer | skipped |

## Per-citation detail

### [#1] OK valid

**Original:** [1] Vaswani, A; Shazeer, N; Parmar, N., et al. (2017). *Attention is all you need*. Advances in Neural Information Processing Systems, 30. doi:10.48550/arXiv.1706.03762

**Raw bibliography text:**

> [1] Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention is all you need. Advances in Neural Information Processing Systems, 30. doi:10.48550/arXiv.1706.03762

**Channel A (Crossref/OpenAlex/Semantic Scholar):** `valid` — confidence 0.9
- Matched via: **openalex**
- Match: Vaswani, Ashish; Shazeer, Noam; Parmar, Niki; Uszkoreit, Jakob et al. (+4). (2025). *Attention Is All You Need*. doi:10.65215/2q58a426
- crossref: DOI 10.48550/arXiv.1706.03762 does not resolve
- openalex: valid (title_sim=1.00, author_overlap=1.00, year_match=False)
- semantic_scholar: no results

**Channel B (Codex atomic verify):** `skipped` — confidence ?


### [#2] OK valid

**Original:** Jumper, J; Evans, R; Pritzel, A., et al. (2021). *Highly accurate protein structure prediction with AlphaFold*. Nature, 596(7873), 583-589. doi:10.1038/s41586-021-03819-2

**Raw bibliography text:**

> Jumper, J., Evans, R., Pritzel, A., et al. (2021). Highly accurate protein structure prediction with AlphaFold. Nature, 596(7873), 583-589. doi:10.1038/s41586-021-03819-2

**Channel A (Crossref/OpenAlex/Semantic Scholar):** `valid` — confidence 1.0
- Matched via: **crossref**
- Match: Jumper, John; Evans, Richard; Pritzel, Alexander; Green, Tim et al. (+30). (2021). *Highly accurate protein structure prediction with AlphaFold*. Nature. doi:10.1038/s41586-021-03819-2
- crossref: valid (title_sim=1.00, author_overlap=1.00, year_match=True)

**Channel B (Codex atomic verify):** `skipped` — confidence ?


### [#3] FAKE hallucinated

**Original:** Zhang, Q; Liu, M. (2023). *Quantum-entangled attention for zero-shot generalization in Martian robotics*. Journal of Fictional AI Studies, 42, 1-17. doi:10.1234/fake.2023.0001

**Raw bibliography text:**

> Zhang, Q., Liu, M. (2023). Quantum-entangled attention for zero-shot generalization in Martian robotics. Journal of Fictional AI Studies, 42, 1-17. doi:10.1234/fake.2023.0001

**Channel A (Crossref/OpenAlex/Semantic Scholar):** `not_found` — confidence 0.366
- Matched via: **openalex**
- Match: Bassi, Angelo; Cacciapuoti, L.; Capozzıello, Salvatore; Dell’Agnello, S. et al. (+11). (2022). *A way forward for fundamental physics in space*. npj Microgravity. doi:10.1038/s41526-022-00229-0
- crossref: DOI 10.1234/fake.2023.0001 does not resolve
- openalex: best candidate title_sim=0.44, author_overlap=0.00 — too weak to call a match
- openalex: not_found (title_sim=0.44, author_overlap=0.00, year_match=True)
- semantic_scholar: no results

**Channel B (Codex atomic verify):** `skipped` — confidence ?

**Replacement search:**
- Status: `skipped`
- Reason: codex not available — replacement search requires codex

### [#4] FAKE hallucinated

**Original:** Nakamura, T; Einstein, A. (2019). *Consciousness-preserving large language models: a telepathic transformer*. Proceedings of the Imaginary Conference on AI, 7, 12-24.

**Raw bibliography text:**

> Nakamura, T., Einstein, A. (2019). Consciousness-preserving large language models: a telepathic transformer. Proceedings of the Imaginary Conference on AI, 7, 12-24.

**Channel A (Crossref/OpenAlex/Semantic Scholar):** `not_found` — confidence 0.385
- Matched via: **crossref**
- Match: Rivera, Michael. (2025). *Emergent Sentience in Large Language Models Emergent Sentience in Large Language Models: Transformer Architecture and the Neurological Foundations of Consciousness*. doi:10.2139/ssrn.5205537
- crossref: best candidate title_sim=0.64, author_overlap=0.00 — too weak to call a match
- crossref: not_found (title_sim=0.64, author_overlap=0.00, year_match=False)
- openalex: best candidate title_sim=0.37, author_overlap=0.00 — too weak to call a match
- openalex: not_found (title_sim=0.37, author_overlap=0.00, year_match=False)
- semantic_scholar: no results

**Channel B (Codex atomic verify):** `skipped` — confidence ?

**Replacement search:**
- Status: `skipped`
- Reason: codex not available — replacement search requires codex

## Action items

### 2 hallucinated citation(s) — no suitable replacement found
- [#3] Quantum-entangled attention for zero-shot generalization in Martian robotics
- [#4] Consciousness-preserving large language models: a telepathic transformer

