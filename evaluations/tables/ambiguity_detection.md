| Detector | P | R | F1 | TP | FP | FN | Flag rate on clear Spider dev |
|---|---|---|---|---|---|---|---|
| Ontology rule (SKOS labels + context) | 100.0 | 100.0 | 100.0 | 20 | 0 | 0 | 4.5 |
| BM25 score margin, tau=0.05 | 66.7 | 50.0 | 57.1 | 10 | 5 | 10 | 23.4 |
| BM25 score margin, tau=0.1 | 57.9 | 55.0 | 56.4 | 11 | 8 | 9 | 40.5 |
| BM25 score margin, tau=0.2 | 50.0 | 60.0 | 54.5 | 12 | 12 | 8 | 55.9 |
| BM25 score margin, tau=0.3 | 50.0 | 65.0 | 56.5 | 13 | 13 | 7 | 64.9 |

Stress set: 20 ambiguous, 20 clear. The last column is the share of the 222 Spider dev questions on the same databases (all clear) that each detector flags, i.e. unnecessary clarifications on unseen questions. The ontology rule was developed while building the stress set, so its stress-set scores are optimistic; the Spider column is the out-of-sample check.
