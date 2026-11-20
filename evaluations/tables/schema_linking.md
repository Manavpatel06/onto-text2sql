| Questions | Method | n | R@1 | R@3 | R@5 | P | R | F1 |
|---|---|---|---|---|---|---|---|---|
| spider | TF-IDF, column names | 214 | 44.7 | 68.1 | 79.9 | 46.3 | 68.1 | 55.1 |
| spider | BM25, column names | 214 | 45.1 | 66.2 | 77.8 | 45.8 | 66.2 | 54.1 |
| spider | TF-IDF, names + ontology labels | 214 | 44.9 | 67.8 | 79.8 | 45.5 | 67.8 | 54.4 |
| spider | BM25, names + ontology labels | 214 | 46.3 | 68.1 | 77.1 | 45.6 | 68.1 | 54.7 |
| spider | Ontology matching (SKOS labels + context rules) | 214 | 44.0 | 64.5 | 68.2 | 67.6 | 68.3 | 68.0 |
| stress | TF-IDF, column names | 39 | 37.4 | 61.1 | 70.9 | 33.8 | 61.1 | 43.5 |
| stress | BM25, column names | 39 | 40.0 | 67.1 | 69.7 | 37.2 | 67.1 | 47.8 |
| stress | TF-IDF, names + ontology labels | 39 | 43.8 | 68.6 | 72.6 | 37.2 | 68.6 | 48.2 |
| stress | BM25, names + ontology labels | 39 | 46.4 | 70.3 | 74.4 | 38.0 | 70.3 | 49.4 |
| stress | Ontology matching (SKOS labels + context rules) | 39 | 55.8 | 76.3 | 78.4 | 61.4 | 78.4 | 68.9 |
| all | TF-IDF, column names | 253 | 43.6 | 67.0 | 78.5 | 44.3 | 67.0 | 53.4 |
| all | BM25, column names | 253 | 44.3 | 66.3 | 76.5 | 44.5 | 66.3 | 53.2 |
| all | TF-IDF, names + ontology labels | 253 | 44.7 | 67.9 | 78.7 | 44.2 | 67.9 | 53.6 |
| all | BM25, names + ontology labels | 253 | 46.3 | 68.4 | 76.7 | 44.5 | 68.4 | 53.9 |
| all | Ontology matching (SKOS labels + context rules) | 253 | 45.8 | 66.3 | 69.8 | 66.7 | 69.9 | 68.2 |

R@k: share of gold columns in the top k. P/R/F1: ranked methods use their top 3 columns; ontology matching uses the columns it links. Join keys used only in ON conditions are excluded from the gold columns.
