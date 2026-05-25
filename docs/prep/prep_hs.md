# Saifr.ai Interview Preparation — Mohd Ayyoob
> Data Scientist | Kotak Mahindra Bank → Saifr.ai (Fidelity Labs)

**Tag Legend:**
- `[GUARANTEED]` — Will definitely be asked
- `[VERY LIKELY]` — High probability follow-up
- `[DESIGN CHOICE]` — "Why X over Y" questions
- `[DEEP DIVE]` — Adversarial / curveball questions

---

## PROJECT 1: Kotak Agentic Reader
*Credit Intelligence Agent | LangChain | Multi-Agent | Ollama | Pydantic | Streamlit*

### Project Description : 
Kotak Agentic Reader — Credit Intelligence Agent
1. Built a LangChain based agentic system for natural-language based credit decisioning over
banking transactions & CIBIL data, generating automated PDF/HTML/Excel reports.
2. Built a goal-conditioned agentic pipeline with dynamic tool selection across 25+ modular
analytics tools and zero human-in-the-loop intervention
3. Enabled dual-model on-device LLM orchestration (Mistral for intent extraction, DeepSeek
for synthesis) via Ollama for Hindsighting Team
4. Delivered multi-modal autonomous report generation with Pydantic-typed inter-agent
contracts and Streamlit streaming interface
5. Improved efficiency of Hindsighting team, enabling fast corrective measures over lending
Enhanced throughput of hindshighting team by ~400x on per day basis

### A. Guaranteed Questions

1. `[GUARANTEED]` Walk me through the end-to-end architecture of your Kotak Agentic Reader system.
2. `[GUARANTEED]` You claim 400x throughput improvement. How exactly did you measure this? What was the baseline?
3. `[GUARANTEED]` How did you implement dynamic tool selection across 25+ tools with zero human-in-the-loop? Walk me through the routing logic.
4. `[GUARANTEED]` You used Mistral for intent extraction and DeepSeek for synthesis. Why two models? Why not one?
5. `[GUARANTEED]` How did you handle failures or hallucinations in a zero human-in-the-loop pipeline? What were your fallback strategies?
6. `[GUARANTEED]` What are Pydantic-typed inter-agent contracts? Why did you use them and what problem did they solve?
7. `[GUARANTEED]` How did you run dual-model on-device LLM orchestration via Ollama? What were the latency and resource trade-offs?

### B. Very Likely Questions

1. `[VERY LIKELY]` How did you manage state across agents in a multi-step pipeline? Did you use LangGraph or plain LangChain?
2. `[VERY LIKELY]` What happens when a tool returns an unexpected result mid-pipeline? How does the next agent in the chain handle it?
3. `[VERY LIKELY]` How did you evaluate the quality of the agentic pipeline's output — especially for credit decisioning where errors are costly?
4. `[VERY LIKELY]` How did you handle the prompt engineering for the orchestrator agent? How did you define tool descriptions so the LLM could pick correctly?
5. `[VERY LIKELY]` What was the latency of the full pipeline end to end? How did you optimise it?
6. `[VERY LIKELY]` How did you stream the Streamlit interface while agents were still running? Did you use async or threading?
7. `[VERY LIKELY]` If you were to rebuild this today with access to GPT-4o or Claude, what would you change?
8. `[VERY LIKELY]` How did you handle confidential banking data in an on-device LLM setup? What data security measures were in place?

### C. Design Choice Deep-Dives

1. `[DESIGN CHOICE]` Why LangChain over building your own orchestration? What limitations did you hit with LangChain?
2. `[DESIGN CHOICE]` Why Ollama for on-device inference instead of a hosted API? What trade-offs did you make?
3. `[DESIGN CHOICE]` Why Pydantic for inter-agent contracts — could you have used plain Python dicts or JSON schemas?
4. `[DESIGN CHOICE]` You chose goal-conditioned pipeline architecture. What alternatives did you consider (e.g. ReAct loop, chain-of-thought only)?
5. `[DESIGN CHOICE]` Why Mistral for intent extraction specifically? Did you evaluate other small models like Phi-3 or Gemma?
6. `[DESIGN CHOICE]` How did you decide the boundaries between your 25+ modular tools? What was the decomposition principle?
7. `[DESIGN CHOICE]` How would you scale this pipeline if you needed to serve 1000 concurrent analysts instead of one team?
8. `[DESIGN CHOICE]` At Saifr, we build compliance agents. How would you adapt your credit decisioning agent architecture for detecting non-compliant financial text?

### D. Deep Dive / Adversarial Questions

1. `[DEEP DIVE]` How do you prevent prompt injection attacks in a pipeline that processes untrusted banking transaction text?
2. `[DEEP DIVE]` In a credit decisioning context, what happens if the LLM hallucinates a credit score or income figure? How did you guard against this?
3. `[DEEP DIVE]` What is the difference between an agent and a chain in LangChain? When would you use one over the other?
4. `[DEEP DIVE]` How would you add a human-in-the-loop checkpoint to your pipeline without destroying the 400x throughput gain?
5. `[DEEP DIVE]` What does 'goal-conditioned' mean precisely in your architecture? How does the goal propagate across agents?
6. `[DEEP DIVE]` How do you debug a failure in a 5-step agentic pipeline where the error only surfaces at step 4?

### Resources — Agentic Pipeline

| Resource | Type | Link |
|---|---|---|
| ReAct: Synergizing Reasoning and Acting in LLMs | Paper | arxiv.org/abs/2210.03629 |
| Toolformer: LMs Can Teach Themselves to Use Tools | Paper | arxiv.org/abs/2302.04761 |
| AgentBench: Evaluating LLMs as Agents | Paper | arxiv.org/abs/2308.03688 |
| LangGraph Official Docs | Docs | langchain-ai.github.io/langgraph/ |
| LangChain Expression Language (LCEL) | Docs | python.langchain.com/docs/expression_language/ |
| Ollama Docs | Docs | ollama.ai/docs |
| DeepLearning.AI — Functions, Tools, Agents with LangChain | Course | deeplearning.ai/short-courses/ |
| Andrej Karpathy — Intro to LLMs | Video | youtube.com/@AndrejKarpathy |
| Pydantic v2 Docs | Docs | docs.pydantic.dev |
| Self-Refine: Iterative Refinement with Self-Feedback | Paper | arxiv.org/abs/2303.17651 |

---