# Saifr.ai Interview Preparation — Mohd Ayyoob
> Data Scientist | Kotak Mahindra Bank → Saifr.ai (Fidelity Labs)

**Tag Legend:**
- `[GUARANTEED]` — Will definitely be asked
- `[VERY LIKELY]` — High probability follow-up
- `[DESIGN CHOICE]` — "Why X over Y" questions
- `[DEEP DIVE]` — Adversarial / curveball questions

---

## PROJECT: Address Reachability & Loss Prevention
*IndicBERT | LoRA Fine-tuning | NER | Geo-spatial Logic | 82% Token Accuracy*

Address Reachability & Loss Prevention Scoring
1. Engineered an Address Quality Scoring Engine using Bureau/KYC data to detect
unreachable applicants and reduce onboarding risk.
2. Fine-tuned IndicBERT via LoRA for NER ( entities like Landmark, Locality, etc.), achieving
82% token accuracy across regional dialects.
3.  Developed a Geo-spatial Logic Layer to bucket customers into 0/1/10km reachability zones.
Improved correct rejection accuracy from 34% to 64% while slashing wrongful rejections
from 20% to 7%, improving approval quality and genuine customer retention.

### A. Guaranteed Questions

1. `[GUARANTEED]` Walk me through how you fine-tuned IndicBERT with LoRA for NER. What was the training setup — dataset size, epochs, rank?
2. `[GUARANTEED]` You achieved 82% token accuracy across regional dialects. How did you define token accuracy — per token F1 or exact match?
3. `[GUARANTEED]` What does LoRA do mathematically? Why does low-rank decomposition work for fine-tuning?
4. `[GUARANTEED]` How did you go from NER entity extraction to a reachability score? What was the scoring function?
5. `[GUARANTEED]` Correct rejection accuracy improved from 34% to 64% — how is 'correct rejection' defined and measured?

### B. Very Likely Questions

1. `[VERY LIKELY]` How did you handle the lack of annotated NER data for regional Indian dialects? How did you build your training set?
2. `[VERY LIKELY]` What LoRA hyperparameters did you tune — rank r, alpha, target modules? How did you choose them?
3. `[VERY LIKELY]` How does your Geo-spatial Logic Layer bucket customers into 0/1/10km zones? What data source provides coordinates?
4. `[VERY LIKELY]` Wrongful rejections dropped from 20% to 7%. How did you balance recall vs precision in this high-stakes setting?
5. `[VERY LIKELY]` At Saifr, we use NER to identify compliance risk entities in financial documents. How is your IndicBERT NER approach applicable?

### C. Design Choice Questions

1. `[DESIGN CHOICE]` Why IndicBERT over multilingual BERT (mBERT) or XLM-R for Indian language NER?
2. `[DESIGN CHOICE]` Why LoRA over full fine-tuning or prefix tuning for this task?
3. `[DESIGN CHOICE]` How did you choose rank r for LoRA? What happens if rank is too high or too low?
4. `[DESIGN CHOICE]` Why a rule-based geo-spatial layer on top of the ML model instead of end-to-end ML?

### Resources — LoRA Fine-tuning & NER

| Resource | Type | Link |
|---|---|---|
| LoRA: Low-Rank Adaptation of Large Language Models | Paper | arxiv.org/abs/2106.09685 |
| QLoRA: Efficient Finetuning of Quantized LLMs | Paper | arxiv.org/abs/2305.14314 |
| IndicBERT: Multilingual Pre-training for Indian Languages | Paper | arxiv.org/abs/2212.05409 |
| Hugging Face PEFT Library Docs | Docs | huggingface.co/docs/peft |
| DeepLearning.AI — Finetuning LLMs | Course | deeplearning.ai/short-courses/finetuning-large-language-models/ |
| Named Entity Recognition — Survey (Li et al.) | Paper | arxiv.org/abs/2007.15328 |
| Hugging Face Token Classification Tutorial | Docs | huggingface.co/docs/transformers/tasks/token_classification |

---