# Robert Schapire
**Role:** Partner Researcher, Microsoft Research, New York City
**Category:** ABC Citations — P23

## Who They Are
Robert Schapire co-invented AdaBoost with Yoav Freund, proving that any collection of weak learners can be combined into an arbitrarily accurate strong learner — one of the foundational results in machine learning. His 1990 PhD thesis at MIT (under Ron Rivest) gave the first mathematically rigorous proof that boosting is possible, and the subsequent work with Freund turned that proof into a practical algorithm that reshaped the field. After faculty positions at AT&T Labs and Princeton, he joined Microsoft Research in 2014. He was elected to both the National Academy of Sciences and the National Academy of Engineering — a rare dual membership that reflects a career spent building theory that actually ships. His research now spans boosting, online learning, game theory, and maximum entropy methods.

## Relationship to AI Tools
Schapire sits inside one of the largest AI research organizations in the world. At Microsoft Research, he has direct visibility into how ensemble and routing methods are being applied at scale — including in the commercial AI products that screamingface's users are routing queries to. He engages AI tools as both a theorist and an insider to the production systems that serve them. His perspective on any new ensemble system would be informed not just by the theory he co-created but by practical knowledge of what the component models can and cannot do, how they fail, and what routing across them actually costs in latency and coherence.

## Likely Reaction to screamingface
Schapire would approach screamingface with the precision of someone who literally wrote the book on boosting (he and Freund co-authored "Boosting: Foundations and Algorithms" for MIT Press). He'd immediately distinguish between what screamingface is doing — routing queries to whichever model is predicted to perform best — and what boosting actually does, which is training a weighted combination of learners with provable error reduction at each round. The distinction matters: boosting works because each weak learner is trained on the mistakes of the previous ones, creating a dependence structure that drives accuracy up. Model routing across pre-trained APIs doesn't have that feedback loop. He'd respect the empirical results if they're real, but he'd be precise about what the architecture is and isn't. From inside Microsoft, he'd also have a pragmatic read on the competitive dynamics — whether an open routing layer on top of proprietary models is sustainable, or whether the providers will eventually optimize it away.

## Key Tension
Is screamingface's model routing actually an ensemble method in the formal sense — where the combination is provably stronger than the parts — or is it adaptive model selection, which is a different problem with different guarantees and different failure modes?
