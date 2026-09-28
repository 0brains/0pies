# 0pi.es UI translation glossary

For the 12 target-language agents: pt fr de it pl tr ru hi zh ja ko vi.
You are translating `data/i18n/ui/<lang>.json`, `data/i18n/index/<lang>.json`,
and `data/i18n/labs/<lang>.json`, keyed off the English source (`en.json`)
using `es.json` and `ar.json` as worked precedent for tone and mechanics.
0pi.es is a playful-but-precise site of AI-governance/certification study games.

## 1. Protected terms — never translate

Keep verbatim, in Latin script, regardless of target language:
- **Cloud vendors & their AI services**: AWS, Azure, Google Cloud, Amazon Web
  Services, Microsoft, SageMaker, Bedrock, Azure AI Foundry, Copilot Studio,
  Project Foundry, Azure OpenAI, Assistants API — and any other vendor/service
  proper noun you encounter in the source strings. If a service name shows up
  that isn't listed here, still leave it untranslated — it's a product name,
  not prose.
- **Exam/cert codes and names**: AIGP, AIF-C01, AI-900, AI-901, CISSP, and any
  other exam code pattern you meet (letters+digits, or ALLCAPS acronym).
  "IAPP AIGP" stays as one unit.
- **Framework/standard names**: NIST AI RMF, ISO/IEC 42001, and other
  framework/standard names as encountered (GDPR/EU AI Act — see §2 for their
  localized short names).
- **Brand/product**: "0pi.es", AI assistant names used in `ai.open_in_label`
  (Claude, ChatGPT, Perplexity, etc.).
- Anything in `{placeholder}` braces is code, not text — never translate,
  reorder only if your grammar requires it and the token itself is untouched.

## 2. Statute names — official localized short names ARE allowed

Precedent: es uses "RGPD" and "Ley de IA de la UE"; ar pairs the Arabic name
with the Latin acronym, e.g. "اللائحة العامة لحماية البيانات (GDPR)".

Known official short forms — use these where confident, otherwise keep the
English/Latin acronym (GDPR / EU AI Act) and add the local acronym in
parentheses only if it's a real, established one you know:
- pt: RGPD (Regulamento Geral sobre a Proteção de Dados)
- fr: RGPD (Règlement général sur la protection des données)
- de: DSGVO (Datenschutz-Grundverordnung)
- it: GDPR (no separate Italian acronym in common use — keep GDPR)
- pl: RODO (Rozporządzenie o Ochronie Danych Osobowych)
- tr: GDPR (no established Turkish acronym — keep GDPR, may gloss as "Genel Veri Koruma Tüzüğü")
- ru: GDPR (regularly transliterated as ГОРД, but GDPR remains dominant — keep GDPR)
- hi: GDPR (no Hindi acronym in use — keep GDPR)
- zh: GDPR (通用数据保护条例, but keep "GDPR" as the working acronym)
- ja: GDPR (一般データ保護規則, but keep "GDPR" as the working acronym)
- ko: GDPR (일반 개인정보 보호법, but keep "GDPR" as the working acronym)
- vi: GDPR (no Vietnamese acronym in use — keep GDPR)

The "EU AI Act" has no widely-established localized acronym in any of these
12 languages yet — translate the descriptive name if natural (as es does:
"Ley de IA de la UE") but keep "EU AI Act" as a parenthetical anchor the
first time it appears in a given string set. **Never invent an official
short name or acronym that doesn't genuinely exist** — when unsure, default
to keeping "GDPR" / "EU AI Act" untranslated.

## 3. Tone

Playful-but-precise. `share.*` strings are jokes — three distinct comedic
registers (smug accidental expert / breathless discovery / disgusted-but-
hooked). Localize the humor natively; do not transliterate English jokes or
idioms word-for-word. `idx.cookie.*` and `idx.terms.*` are a running bit
(mock-legal cookie policy, "no pies" wordplay) — keep it funny in the target
language even if the literal pie pun doesn't translate; a different pun or a
straight joke is fine, losing the joke entirely is not.

Typography: preserve en.json's use of the typographic apostrophe (U+2019 ’,
never straight `'`) and em dash (U+2014 —, with surrounding spaces as in the
source) as house style, in every language that uses Latin/Cyrillic-adjacent
punctuation conventions. Don't introduce ASCII substitutes.

## 4. Formality per language (state your choice, stay consistent)

- pt: tu (informal, matching es's tú) — pick pt-PT "tu" register throughout, not "você"
- fr: tu
- de: du
- it: tu
- pl: informal 2nd person (potoczny, not "Pan/Pani")
- tr: sen
- ru: ты
- hi: तुम (informal-friendly, not आप) — matches the site's casual register
- zh: 你 (not 您)
- ja: です/ます polite-casual — friendly, not stiff keigo
- ko: 해요체 (not 하십시오체)
- vi: bạn

## 5. Mechanics

- Keys never change. Only translate values.
- `{placeholder}` tokens copied verbatim, same spelling/case, wherever your
  grammar places them.
- Plural keys: only `_one`/`_other` slots exist (e.g. `cards.count_one`,
  `cards.count_other`) — no more, no fewer, regardless of how many plural
  categories your language has.
  - ru, pl: have 3-4 grammatical plural categories natively, but only two
    slots are available — pick the natural best-fit mapping (typically the
    singular-context form for `_one`, the general/majority form for `_other`)
    rather than trying to encode every category.
  - zh, ja, ko, vi: mostly don't inflect for number — using the same string
    in both `_one` and `_other` is correct and expected, not a shortcut.
- No `<` immediately followed by a letter anywhere in any translated string
  — this is build-blocking (parsed as an HTML tag). Rewrite the sentence to
  avoid it if the source relies on it.
- UI space is tight: keep translated string length comparable to the English
  original — avoid inflating short button/badge labels.
- RTL is not applicable to any of these 12 languages — no directionality
  work needed (unlike ar.json).

## 6. Never-translate categories (site-wide rule, not just §1)

Beyond §1's protected terms: any in-game answer strings, multiple-choice
options, zone/region names on maps or boards, and legal/regulatory citations
embedded in card content stay in English — they are what the underlying
exam/reference material tests against. Only the UI chrome you're handed
(buttons, labels, hints, headings, toasts, share copy) is yours to translate.
