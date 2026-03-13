# Shafi Goldwasser
**Role:** RSA Professor of Electrical Engineering and Computer Science, MIT; Professor of Mathematical Sciences, Weizmann Institute of Science; Co-founder and Chief Scientist, Duality Technologies
**Category:** ABC Citations — P18

## Who They Are
Shafi Goldwasser co-invented zero-knowledge proofs and interactive proof systems (Goldwasser, Micali, Rackoff 1989) — the theoretical primitives that make it possible to verify a computation without revealing the underlying data. She won the Turing Award in 2012 with Silvio Micali for laying the mathematical foundations of modern cryptography. More recently, she has turned her attention to AI trust and security, particularly backdoor vulnerabilities in ML models and the use of homomorphic encryption for privacy-preserving machine learning, arguing that verification must be baked into the training process rather than bolted on after the fact.

## Relationship to AI Tools
Goldwasser engages AI from the foundations up — not as a daily user of coding CLIs, but as someone building the cryptographic theory that determines whether privacy and verifiability claims in AI systems actually hold. Through Duality Technologies, she has direct experience commercializing privacy-preserving computation, bridging the gap between theoretical guarantees and deployed systems. Her recent work at the intersection of cryptography and ML (backdoor detection, homomorphic encryption for model training) makes her unusually well-positioned to evaluate whether an ensemble routing system can deliver on its security promises.

## Likely Reaction to screamingface
Goldwasser would zero in on the verification layer. The ABC thesis draws on interactive proof systems — her foundational contribution — to establish trust between AI agents and humans. She would find the theoretical lineage credible and would likely be genuinely interested in how those proof-theoretic ideas translate to a real system routing queries across multiple model providers. But she would immediately ask whether the verification is end-to-end: can a user cryptographically confirm that their query was routed correctly, that no provider saw more than it should, and that cached results haven't been tampered with? The ensemble architecture raises composition questions she has spent a career studying. If the attribution-based control framework handles these rigorously, she would view screamingface as a meaningful applied instance of ideas she helped originate. If the verification is informal or trust-based, she would see it as a missed opportunity to use the tools that already exist.

## Key Tension
If screamingface claims its ensemble routing preserves privacy and ensures correct attribution, where is the zero-knowledge proof — or is the system asking users to trust the orchestrator the same way they currently trust individual providers?
