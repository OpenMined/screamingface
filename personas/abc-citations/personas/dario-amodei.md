# Dario Amodei
**Role:** CEO and Co-Founder, Anthropic
**Category:** ABC Citations — P14

## Who They Are
Dario Amodei is the CEO of Anthropic and co-author of the 2016 paper "Concrete Problems in AI Safety," which formalized five categories of accident risk in machine learning systems and became foundational to the alignment research agenda. He left his role as VP of Research at OpenAI in 2021 to co-found Anthropic with his sister Daniela, driven by disagreements over safety priorities. His public writing -- including the 2024 essay "Machines of Loving Grace" and the 2026 essay "The Adolescence of Technology" -- argues that powerful AI is both transformative and concentrating, warning that it could create "personal fortunes well into the trillions" for a powerful few while insisting that democracies must maintain strategic advantage over the technology's trajectory.

## Relationship to AI Tools
Amodei is a builder and a gatekeeper simultaneously. Anthropic ships Claude as a commercial product while developing Constitutional AI and interpretability research meant to constrain what models can do. He views the open-source versus closed-source distinction as "a red herring" -- what matters is whether a model is good and whether its behavior can be understood and steered. He is skeptical that open weights provide the same benefits as open-source software, since "you can't see inside the model." His preferred infrastructure is cloud-hosted, centrally monitored, and interpretable at the activation level.

## Likely Reaction to screamingface
Amodei would see screamingface's ensemble routing as technically interesting but structurally concerning. The core value proposition -- routing prompts through multiple providers to beat any single model's SOTA -- directly undermines the business case for any one frontier lab, Anthropic included. He would likely acknowledge that multi-model ensembles can improve accuracy, but push back hard on the safety implications: if no single provider controls the inference pipeline, who enforces the constitutional constraints? Who monitors for harmful outputs when the routing layer sits outside every lab's safety stack? The credit-sharing mechanism would further alarm him -- it distributes access to powerful models beyond the billing relationships labs use to enforce acceptable use policies. He would be most engaged by the attribution and audit trail questions: can screamingface trace which model produced which output, and can that provenance be used for accountability?

## Key Tension
Screamingface decentralizes model access and routes around individual providers' safety layers -- but Amodei's entire thesis is that safety requires the model builder to maintain interpretability and control over how their system is used, which ensemble routing architecturally defeats.
