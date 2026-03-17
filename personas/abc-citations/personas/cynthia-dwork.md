# Cynthia Dwork
**Role:** Gordon McKay Professor of Computer Science, Harvard SEAS; Affiliate Faculty, Harvard Law School and Department of Statistics
**Category:** ABC Citations — P11

## Who They Are
Cynthia Dwork invented differential privacy — the mathematical framework that now underlies Apple's data collection practices, the 2020 US Census, and the privacy guarantees in countless ML systems. Awarded the National Medal of Science in 2025 and the 2026 Japan Prize, she is the closest thing the field has to a gold standard for privacy claims. Her work sits at the intersection of theoretical computer science, statistics, and increasingly, law and policy — her Harvard affiliation spans all three. She doesn't endorse things on vibes; her engagement with any privacy claim begins with asking whether the formal guarantees hold under composition and adversarial conditions.

## Relationship to AI Tools
A theoretical computer scientist who builds the mathematical foundations others build on. She engages AI tools as a researcher and, increasingly, as a policy voice — her work on algorithmic fairness and privacy has made her a sought-after expert in regulatory conversations. Not a practitioner in the sense of daily CLI use, but deeply attentive to how privacy properties degrade in real systems.

## Likely Reaction to screamingface
Dwork would want to see the formal privacy analysis before forming a view. The claim that distributing queries across multiple providers improves privacy is intuitively reasonable but technically non-trivial — privacy under composition can degrade in surprising ways, and the ensemble routing logic creates new data flows that need to be analyzed carefully. If the privacy math in the attribution-based control framework is correct and rigorously documented, her engagement would be a credibility anchor unlike anyone else on this list. If it's hand-wavy, she'd say so precisely and publicly. She's not a natural public-facing advocate for specific tools, but a technical seal of approval from her carries exceptional weight with the policy and research communities the project needs to reach.

## Key Tension
Do screamingface's privacy guarantees hold formally under composition — when queries are split, routed, and logged across multiple providers with different retention policies — or does the ensemble architecture introduce new privacy leakage that the current framework doesn't account for?
