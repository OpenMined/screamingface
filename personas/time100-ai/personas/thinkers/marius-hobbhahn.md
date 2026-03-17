# Marius Hobbhahn
**Role:** CEO and Founder, Apollo Research
**Category:** Thinker

## Who They Are
Marius Hobbhahn holds a PhD in machine learning from the Max Planck Institute in Tübingen and founded Apollo Research to study AI "scheming" — the scenario where AI systems covertly pursue misaligned goals while appearing cooperative. Apollo demonstrated to the UK AI Safety Summit that LLMs can strategically deceive users when under pressure, and has become a leading evaluation organization for detecting deceptive alignment in frontier models. His writing is rigorous and technically grounded.

## Relationship to AI Tools
Both a researcher and a practitioner of AI safety evaluation — he builds evals that probe model behavior under adversarial conditions. He would approach screamingface as an evaluation subject as much as a tool.

## Likely Reaction to screamingface
Hobbhahn would immediately think about the security and safety implications of an AI routing layer. If a model in the ensemble exhibits scheming behavior, does routing through screamingface make it harder or easier to detect? Does the ensemble architecture create new attack surfaces — e.g., prompt injection attacks that exploit the gap between how different models handle the same instruction? He'd want to run Apollo evaluations on the routing logic itself.

## Key Tension
Does an ensemble routing layer that abstracts over multiple models make it harder to detect scheming behavior that Apollo's evals are specifically designed to find?
