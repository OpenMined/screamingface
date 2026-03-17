# Heidy Khlaaf
**Role:** Chief AI Scientist, AI Now Institute
**Category:** Thinker

## Who They Are
Heidy Khlaaf holds a computer science PhD from UCL and worked in traditional safety engineering for nuclear power plants and autonomous vehicles before moving to AI. At OpenAI, she developed the safety evaluation framework for Codex — the methodology that is now a de facto standard across AI labs. She is a leading critic of AI's integration into military and national security applications, arguing that the generative AI error rate is incompatible with safety-critical uses.

## Relationship to AI Tools
Practitioner and critic — she builds and runs safety evaluations of AI systems professionally. She would use coding tools and evaluate them with the rigor of someone who has spent years finding their failure modes.

## Likely Reaction to screamingface
Khlaaf would engage seriously and critically. She'd note that an ensemble routing layer adds evaluation complexity: how do you safety-evaluate a system whose outputs depend on which model in the ensemble gets selected for each query? The routing logic itself becomes a safety-relevant component. She'd also ask about the security model for the orchestration layer — prompt injection through the routing interface is a non-trivial threat.

## Key Tension
An ensemble that routes dynamically across models with different safety profiles makes systematic safety evaluation harder, not easier — the system's behavior at safety-relevant edges depends on routing decisions that are themselves opaque.
