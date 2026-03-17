# Adi Shamir
**Role:** Paul and Estella Ollendorff Professor of Computer Science, Weizmann Institute of Science
**Category:** ABC Citations — P19

## Who They Are
Adi Shamir is one of the most influential cryptographers alive — the "S" in RSA, a 2002 Turing Award laureate, and the inventor of Shamir's Secret Sharing (1979), which remains the mathematical foundation for secure multi-party computation. His recent work has shifted to the intersection of cryptography and deep neural networks: extracting model weights from black-box neural networks using differential cryptanalysis (EUROCRYPT 2024), developing adversarial attack methods (NeurIPS 2024), and embedding cryptographic primitives inside DNNs (RWC 2025). He is a co-author of the Feige-Fiat-Shamir zero-knowledge identification protocol (1988), which underpins modern privacy-preserving authentication.

## Relationship to AI Tools
Shamir engages with AI systems as a security researcher, not as a user or builder. His lens is adversarial: he probes neural networks the same way he probes cryptosystems — looking for structural weaknesses that allow extraction, manipulation, or bypass. He demonstrated that ReLU-based DNN weights can be fully extracted in polynomial time from black-box access alone. He has expressed pessimism about training LLMs legally under European privacy law, signaling that he sees fundamental tension between data-hungry AI development and privacy rights. He is not building AI products; he is stress-testing the ones that exist.

## Likely Reaction to screamingface
Shamir would immediately zero in on the secret sharing layer. OpenMined's PySyft framework already uses his secret sharing scheme as a primitive for secure aggregation, so the mathematical lineage is direct and legible to him. He would likely appreciate that screamingface routes queries across multiple model providers without exposing the full prompt or response to any single party — this is structurally aligned with threshold cryptography. However, he would probe hard on the trust model: who holds the shares, what happens when a model provider is adversarial rather than semi-honest, and whether the ensemble routing itself leaks information about user intent through query patterns. His own work on neural network extraction would make him skeptical that black-box access to multiple models can be safely orchestrated without enabling side-channel inference about the system's internal routing logic.

## Key Tension
If you can extract the weights of a neural network from its outputs alone, what prevents an adversarial model provider in the ensemble from reverse-engineering the routing strategy — and by extension, the user's private intent — from the subset of queries it receives?
