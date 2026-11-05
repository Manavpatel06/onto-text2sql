# Work packages

One self-contained brief per member. Each lists the files you own, the exact
interface other modules expect, the steps, and how to check you're done.
Read `docs/ARCHITECTURE.md` first; it is the contract between modules.

| Member | Brief | Owns |
|---|---|---|
| Manav | [manav.md](manav.md) | Direct baseline (A), evaluation pipeline, result tables |
| Manas | [manas.md](manas.md) | Database selection, schema extraction, ontology spreadsheet, Turtle conversion |
| Vian | [vian.md](vian.md) | Ontology-grounded query planning, ambiguity detection |
| Saniya | [saniya.md](saniya.md) | Ambiguity Stress Set, clarification prompts, simulated user |
| Vatsal | [vatsal.md](vatsal.md) | Verification and repair, ablation runs, integration, demo |

## Dependencies

```
Manas (ontology .ttl) ──► Vian (planning, ambiguity) ──► Saniya (clarification) ──► Vatsal (verify, runs)
Saniya (stress set) ────────────────────────────────────────────────────────────► Manav (metrics) ──► everyone (report)
```

Manas's ontology and Saniya's stress set unblock everyone else, so they come first.

## Team conventions

* Branch per member (`manas/ontology`, `vian/ambiguity`, ...), pull request into `main`, one reviewer.
* `pytest` must pass before merging. Add tests for your module in `code/tests/test_<module>.py`
  that run without network (use `ontosql.llm.ScriptedModel` instead of a real model).
* Never commit `.env` or anything under `data/spider/`.
* Don't change `types.py` or another member's function signatures without telling the team.
