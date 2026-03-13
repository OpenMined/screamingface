# Craig Gentry
**Role:** Research Scientist, TripleBlind (formerly IBM Research)
**Category:** ABC Citations — P21

## Who They Are
Craig Gentry is the cryptographer who solved the decades-old open problem of fully homomorphic encryption (FHE) in his 2009 Stanford PhD thesis, enabling arbitrary computation on encrypted data without ever decrypting it. He spent over a decade at IBM Research advancing practical FHE schemes before moving to the private sector. His work is the theoretical foundation for any system claiming to process sensitive data without exposing it.

## Relationship to AI Tools
Gentry's work intersects AI at the point where model inference meets data privacy — FHE makes it theoretically possible to run AI models on encrypted inputs, so neither the model operator nor any intermediary ever sees the plaintext. He is likely tracking the emerging field of privacy-preserving machine learning closely, including efforts to make FHE fast enough for real-world AI workloads.

## Likely Reaction to screamingface
Gentry would zero in on the encryption claims. If screamingface routes prompts through multiple model providers — Claude, Gemini, Codex, Ollama — the question is what exactly is encrypted, at what layer, and whether the scheme is truly homomorphic or just transport-level TLS. He would want to know whether the "enclave" architecture uses FHE, secure enclaves (SGX/TDP), or something weaker. He would respect the ambition of Trask's attribution-based control framework but push hard on whether the cryptographic guarantees are formal or hand-waved. If the privacy story holds up under scrutiny, he would be genuinely interested; if it relies on trust assumptions rather than math, he would say so plainly.

## Key Tension
Are the privacy guarantees in screamingface's ensemble routing cryptographically enforced — computed on data you provably cannot see — or do they ultimately depend on trusting the orchestration layer not to look?
