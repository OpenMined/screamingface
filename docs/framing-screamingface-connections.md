# Framing screamingface

**Internal reference, screamingface team**
**March 2026**

---

## The connection (general)

screamingface is an AI ensemble tool that achieves state-of-the-art performance by combining multiple models. It runs on url4, an open protocol for AI task chains. url4 is designed as the grammar and protocol layer for Attribution-Based Control, which is the broader research agenda at OpenMined.

screamingface is the simplest, most straightforward implementation of federated AI on url4. It proves the concept with public models and public data. Other OpenMined initiatives are working on what comes next.

---

## The connection (internal, for OM team)

screamingface demonstrates that you can achieve SOTA performance without private data. That's the baseline. Other bets at OpenMined are working on how to bring private data onto the network, and those capabilities will integrate through url4 as they mature.

url4 is the protocol and grammar for ABC. screamingface happens to be the first and most visible application built on it, but the protocol is designed to extend across OpenMined's full mission: discovery, networking, private data access, attribution. screamingface solves the network bootstrapping problem. It gets people engaged. It builds the community. And it gives the other bets a platform to demonstrate their value as they come online.

The sequence: screamingface proves ensembling works and gets people in the door. Other bets plug in domain-specific private data and show improved performance in those domains. url4 extends to support richer attribution and control. The protocol grows. The network grows.

---

## What to say publicly vs. internally

**Say publicly (now):**
- screamingface combines multiple AI models and outperforms any single model
- The results are open source and reproducible
- It runs on url4, an open protocol
- Decentralization is structurally better (different labs, different data, uncorrelated errors)
- Built by OpenMined, a nonprofit

**Say on the /why page (Persona 2, now):**
- Decentralization itself is powerful. When models come from different labs with different data and different approaches, their errors are uncorrelated. That's why the ensemble wins.
- url4 is an open protocol designed for federated AI
- The ABC thesis is the intellectual foundation (link out)
- Open infrastructure matters (the window, civic institutions, governance)

**Say internally (OM team reveal, temporary callout):**
- screamingface is the first bet built on url4
- It achieves SOTA without private data. That's the baseline.
- Other bets (e.g., Network Source AI with news media data) are working on private data integration
- As those bets come online, they'll plug into this ecosystem and improve domain-specific performance
- url4 is the protocol layer for ABC, designed to extend across OpenMined's full mission
- screamingface solves the network bootstrapping problem

**Don't say publicly (yet):**
- Specific private data integration plans
- Credit sharing as a working feature
- Attribution as a working feature
- Anything that frames this as "against big tech"
- Specific timelines for when other bets will plug in

---

## For the OpenMined team

### Mission-down

screamingface is the thesis in action. An AI ensemble running on url4 that proves open, federated AI outperforms the proprietary alternative.

### Syft analogy

screamingface is to AI models what Syft is to data silos. Syft coordinates computation across data that can't move. screamingface coordinates inference across models that don't share weights.

### What it proves

First proof that open AI ensembles outperform closed single-provider systems, built on our own protocol. SOTA benchmarks, reproducible, open source.

---

## For people who know OpenMined but not screamingface

### New from OpenMined

screamingface combines multiple AI models into one system that outperforms any of them individually, running on url4, a new open protocol. First practical application of the attribution-based control research.

### Mission extension

OpenMined has always built infrastructure for AI that respects boundaries. screamingface extends that to inference, coordinated by url4, an open protocol for federated AI.

### Practical

Install screamingface today, get better AI results than any single model. Open source, built by OpenMined, runs on url4.

---

## For people seeing screamingface who don't know OpenMined

### Tool-first

screamingface combines AI models into an ensemble that outperforms any single model. Under the hood it runs on url4, an open protocol built by OpenMined, a nonprofit doing privacy-preserving AI since 2017.

### Problem-first

Most developers are locked into one AI provider at a time. screamingface breaks that by combining models into an ensemble that outperforms any of them, running on url4, an open protocol from OpenMined.

### Concentric

screamingface is the tool. url4 is the protocol. OpenMined is the org. ABC is the research. You only need screamingface to use it. The rest is there when you want it.

---

## All nine at a glance

| Audience | Approach | Framing |
|----------|----------|---------|
| OM team | Mission-down | The thesis in action, running on url4 to prove open AI beats closed. |
| OM team | Syft analogy | To AI models what Syft is to data silos. Both keep control distributed. |
| OM team | What it proves | First proof that open ensembles outperform single-provider systems, on our protocol. |
| Knows OM | New from OM | Combines AI models into an ensemble on url4, a new open protocol. First ABC application. |
| Knows OM | Mission extension | OpenMined extends distributed-AI work to inference. screamingface is the tool. url4 is the protocol. |
| Knows OM | Practical | Install it today, get better results. Open source, OpenMined, url4. |
| New to OM | Tool-first | Combines AI models, beats all of them. Runs on url4, built by OpenMined. |
| New to OM | Problem-first | Locked into one provider? Combine models, beat all of them. Open protocol, nonprofit. |
| New to OM | Concentric | The tool. The protocol. The org. The research. Start with the tool, explore outward. |

---

## Graphic iterations

### Mission-down (nested layers)

```
┌──────────────────────────────────────────────────────┐
│  OpenMined                                           │
│  "The public network for non-public information"     │
│                                                      │
│    ┌──────────────────────────────────────────┐      │
│    │  ABC thesis                              │      │
│    │  The case for attribution-based control  │      │
│    │                                          │      │
│    │    ┌──────────────────────────┐          │      │
│    │    │  url4 protocol           │          │      │
│    │    │  Makes ABC feasible      │          │      │
│    │    │                          │          │      │
│    │    │    ┌────────────────┐    │          │      │
│    │    │    │ 😱 screamingface│    │          │      │
│    │    │    │ First app      │    │          │      │
│    │    │    └────────────────┘    │          │      │
│    │    └──────────────────────────┘          │      │
│    └──────────────────────────────────────────┘      │
│                                                      │
│  Also: PySyft, Syft Network, BioVault, Subnets...   │
└──────────────────────────────────────────────────────┘
```

### Syft analogy (parallel tracks)

```
  Syft Network                    screamingface
  ────────────                    ──────────────
  Data stays where it lives       Models stay independent
  Computation travels to data     Prompts route to best model
  Insights flow, data doesn't     Results flow, control doesn't
  Built on PySyft                 Built on url4
       │                               │
       └───────────┐   ┌───────────────┘
                   │   │
             ┌─────▼───▼──────┐
             │   OpenMined     │
             │   Open protocol │
             │   infrastructure│
             └────────┬───────┘
                ┌─────▼─────┐
                │ ABC thesis │
                └───────────┘
```

### What it proves (three columns)

```
  BELIEVE                  BUILT                   PROVES
  ─────────────────        ─────────────────        ─────────────────
  AI should be open   ──>  url4 protocol       ──>  Open ensembles
  and distributed          (open spec for            beat closed
                           federated AI)             single models

  Attribution should  ──>  screamingface        ──>  Useful tools on
  be structural            (first app on url4)       open AI infra

  ABC                      github.com/OpenMined     SOTA benchmarks
```

### The sequence (internal story)

```
  NOW                          NEXT                        LATER
  ───                          ────                        ─────

  😱 screamingface             Other bets plug in          url4 extends to
  SOTA with public             private data via url4.      support full ABC.
  models + public data.        Domain-specific             Attribution,
  Network bootstrapping.       benchmarks improve.         compensation,
       │                            │                      governance.
       │                            │                        │
       └────────────┬───────────────┘────────────────────────┘
                    │
              ┌─────▼─────┐
              │    url4    │
              │  protocol  │
              │  (grows    │
              │  with the  │
              │  network)  │
              └─────┬─────┘
              ┌─────▼─────┐
              │  OpenMined │
              │  mission   │
              └───────────┘
```

### New from OpenMined (side by side)

```
  You know:                        Now there's also:
  ─────────────────────────        ──────────────────────────

  PySyft                           😱 screamingface
  (federated ML)                   (AI ensemble tool)
       │                                │
  Syft Network                     url4 protocol
  (computation                     (open spec for
   across silos)                    AI task chains)
       │                                │
       └────────────┬───────────────────┘
                    │
              ┌─────▼──────┐
              │  OpenMined  │
              │  mission    │
              └─────┬──────┘
              ┌─────▼──────┐
              │ ABC thesis  │
              └────────────┘
```

### Mission extension (timeline)

```
  AI that stays distributed
  ─────────────────────────────────────────────────────

  2017   PySyft ·········· federated learning framework
           │
  2020   Syft Network ···· secure computation across silos
           │
  2025   ABC thesis ······ why attribution matters for AI
           │
  2026   url4 ············ open protocol for AI task chains
           │
         screamingface ··· first app: open AI ensemble
           │
         ? ··············· other bets plug in via url4
```

### Practical (linear flow)

```
  Install screamingface   ──>   Better AI results (proven, open source)
        │
  Runs on url4            ──>   Open, auditable protocol
        │
  Built by OpenMined      ──>   8 years of open-source AI infra
        │
  Based on ABC thesis     ──>   The case for open AI as default
```

### Tool-first (depth ladder)

```
  😱 screamingface
  One command to install. Ensemble beats every model.
       │
       │  curious?
       ▼
  url4 protocol
  Open protocol for AI task chains. Transparent and auditable.
       │
       │  want the full picture?
       ▼
  OpenMined
  The nonprofit behind this. 8 years. Open source.
       │
       │  want the deep argument?
       ▼
  ABC thesis
  The intellectual case for why all of this matters.
```

### Problem-first (three columns)

```
  THE PROBLEM              THE TOOL               THE INFRASTRUCTURE
  ───────────              ────────               ──────────────────

  Locked into one     ──>  😱 screamingface  ──>   url4 protocol
  AI provider              Combine models.         Open spec. Anyone
  at a time                Beat all of them.       can build on it.
                                │                        │
                                └──────────┬─────────────┘
                                    ┌──────▼──────┐
                                    │  OpenMined   │
                                    │  nonprofit   │
                                    │  since 2017  │
                                    │              │
                                    │  ABC thesis  │
                                    │  (the why)   │
                                    └─────────────┘
```

### Concentric circles

```
                ┌─────────────────────────────┐
                │         OpenMined            │
                │    nonprofit, est. 2017      │
                │                              │
                │   ┌─────────────────────┐    │
                │   │    ABC thesis        │    │
                │   │  Why attribution     │    │
                │   │  matters for AI      │    │
                │   │                      │    │
                │   │  ┌───────────────┐   │    │
                │   │  │  url4 protocol │   │    │
                │   │  │  Open spec for │   │    │
                │   │  │  AI workflows  │   │    │
                │   │  │               │   │    │
                │   │  │  ┌─────────┐  │   │    │
                │   │  │  │   😱    │  │   │    │
                │   │  │  │  scream │  │   │    │
                │   │  │  │  face   │  │   │    │
                │   │  │  └─────────┘  │   │    │
                │   │  └───────────────┘   │    │
                │   └─────────────────────┘    │
                └─────────────────────────────┘

     You start here ──────────────────> You explore outward
          (the tool)                    (the mission)
```
