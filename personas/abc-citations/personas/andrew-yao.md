# Andrew Chi-Chih Yao
**Role:** Dean, Institute for Interdisciplinary Information Sciences (IIIS), Tsinghua University; 2000 Turing Award Laureate
**Category:** ABC Citations — P24

## Who They Are
Andrew Chi-Chih Yao is the founder of secure multi-party computation. His 1982 paper "Protocols for Secure Computations" — motivated by the Millionaires' Problem — introduced the general framework for multiple parties to jointly compute a function without revealing their private inputs. He followed it with garbled circuits in 1986, which remains the basis for most practical MPC implementations. Born in Shanghai, educated at Harvard (physics PhD under Sheldon Glashow) and UIUC (CS PhD in two years), he held positions at MIT, Stanford, Berkeley, and Princeton before moving to Tsinghua in 2004, where he built IIIS into one of the world's top theoretical CS programs. He renounced his US citizenship in 2015 to join the Chinese Academy of Sciences. In 2024 he co-signed the Bengio-Hinton expert consensus paper warning that AI safety research is lagging behind capabilities.

## Relationship to AI Tools
Yao is a theorist, not a practitioner. He does not use coding CLIs or benchmark leaderboards. His engagement with AI is through foundational theory — computational complexity lower bounds, quantum computing models, and the cryptographic protocols that make privacy-preserving ML possible. His recent public statements focus on quantum-AI integration and on the idea that "proper protocols" can tame large AI systems, drawing a direct analogy from cryptographic protocol design to AI governance. He operates at the layer beneath the tools: the math that determines what the tools are allowed to do.

## Likely Reaction to screamingface
Yao would immediately recognize the MPC lineage in screamingface's architecture — multiple model providers jointly computing a result without exposing each other's full inputs or weights. He would find the ensemble routing concept structurally familiar and would evaluate it against the standard MPC threat models he defined: what is the adversary model, what is the corruption threshold, what are the composition guarantees when queries are chained? He would be cautiously positive about the direction but would want formal security proofs, not empirical benchmarks, as the primary evidence. The fact that Trask's thesis cites his foundational work gives screamingface legitimate standing in his framework, but he would hold it to the standard his field sets: if you claim multi-party privacy guarantees, prove them. His recent co-signing of the AI safety consensus paper suggests he takes the governance framing seriously, not just the cryptography.

## Key Tension
Does the ensemble's privacy architecture satisfy formal MPC security definitions under composition, or does it rely on weaker, empirical privacy assumptions that would not survive adversarial analysis?
