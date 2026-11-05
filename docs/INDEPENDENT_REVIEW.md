# Independent local review

Session date: 2026-11-05. All data used in these checks is original and synthetic. No model service was contacted and no cloud resource was created.

- Direct HTTP verification against the running FastAPI/PostgreSQL application: unauthenticated protected reads returned 401; authenticated reads succeeded; an explicitly hostile Origin on a mutation returned 403.
- Azure Bicep compiled successfully with CLI 0.48.1. This validates local template compilation, not Azure deployment, networking, identity, or runtime operation.
- The real Playwright screenshots in `screenshots/` were visually inspected. This is not an accessibility certification.

## Document evidence

Independently exercised PDF upload (201), background processing to ready, textual retrieval of a fragment on Page 2, authorized source access (200), byte-for-byte original file download, document deletion and subsequent inaccessible source (404). `tests/test_pdf_review.py` adds two passing checks for real two-page text extraction and encrypted-file rejection.

Review findings addressed by implementation: fixture answers bind to original document content; index retries preserve fragment identity; user/session access is mode-scoped; cross-organization direct object access is checked on the server. These checks do not measure semantic grounding of a LIVE model.
