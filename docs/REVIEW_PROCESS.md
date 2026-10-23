# Integrated Split System: Composer ↔ GPT-6 review process

Every milestone is a separate feature branch and **draft pull request**. Avoid mixing unrelated milestones. Do not push implementation directly to `main`.

1. Composer reviews `docs/PRD.md` and `AGENTS.md` and proposes a concise design for the **next single milestone**.
2. Composer implements only that milestone with tests and documentation. No installation/deployment on the production HA host.
3. Composer pushes its branch and opens a draft PR with: goal, changed paths, architectural choices, exact test commands/results, risks, and open questions.
4. User sends PR URL or commit SHA to ChatGPT. GPT-6 reviews GitHub diff and relevant files, checks requirements, latest HA API compatibility, test coverage and physical-command safety, and returns **approve / changes required / blocked** with targeted feedback.
5. Changes are revised and reviewed until accepted; user approves merge and next milestone. GPT-6 does **not** review automatically between messages; request each review in chat.

## Required PR checklist

- [ ] Single PRD milestone; no unrelated work
- [ ] Includes tests and their real output
- [ ] HACS/HA API assumptions linked to docs or validated tests
- [ ] No invented room entity IDs or temperatures
- [ ] New physical services counted, rate-limited, testable and reviewed (when applicable)
- [ ] No production HA changes, restart, automation toggle or direct Sensibo calls
- [ ] Existing Lit card repo untouched unless an explicitly approved cross-repo milestone
- [ ] User-visible change/rollback risk documented

## Review template

```
Review PR: <URL>
Milestone: M<N>
Commit SHA: <full SHA>
What changed: <brief summary>
Tests run: <commands and output>
Known limitations: <list>
Request: Please review against docs/PRD.md and issue a gate decision.
```
