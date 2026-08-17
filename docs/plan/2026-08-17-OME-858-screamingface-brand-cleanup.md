# OME-858 — Implementation plan

1. Inventory tracked `packages/screamingface` files for case-insensitive OpenMined spellings,
   standalone `OM`, and the verification field.
2. Rename the leaderboard field through domain models, strict wire decoding, UI consumption and
   tests without compatibility aliases.
3. Replace package metadata, notices, research references and changelog repository links with
   ScreamingFace branding while preserving their purpose.
4. Regenerate notebooks if their builder changes, then repeat the strict tracked-file search.
5. Run focused leaderboard tests and the complete `screamingface` gate suite.
