# Project State

Current milestone: M0 — Architecture scaffold

Completed:
- Domain-first repository structure
- OCR engine contract, deterministic mock and lazy PaddleOCR adapter
- Human-in-the-loop workflow state machine
- Example onboarding document use case
- Initial schemas, policies and documentation

Next:
- Build authorized 30–50 page Ground Truth evaluation set
- Run PaddleOCR vs MinerU bake-off

Blockers:
- GitHub CLI session must be re-authenticated before publishing
- No verified real-document benchmark has been imported

Decisions:
- Business workflow is independent of OCR vendors
- Sensitive fields require provenance and review
- External side effects are dry-run by default

Important paths:
- `src/hcns_agent/domain/`
- `src/hcns_agent/application/`
- `src/hcns_agent/ports/`
- `docs/ARCHITECTURE.md`
- `docs/HUMAN_IN_THE_LOOP.md`
- `docs/EVALUATION.md`

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m hcns_agent.demo`
- `python scripts/check_repository.py`
