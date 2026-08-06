# Azure architecture icons

These SVGs come from the official Azure Architecture Icons package, version V24.

- Source: https://learn.microsoft.com/en-us/azure/architecture/icons/
- Package: `Azure_Public_Service_Icons_V24.zip`
- Retrieved: July 31, 2026

Microsoft's icon terms (quoted verbatim from the download page and the
`Microsoft_Terms_of_Use.pdf` bundled inside the package):

> Microsoft permits the use of these icons in architectural diagrams, training
> materials, or documentation. You may copy, distribute, and display the icons
> only for the permitted use unless granted explicit permission by Microsoft.
> Microsoft reserves all other rights.

This site's Azure/AI-901 matching games are training/study materials for exam
preparation, which falls within the permitted use above. The files retain their
official package names and artwork (unmodified, not cropped/flipped/rotated, per
Microsoft's Do's and Don'ts on the same page).

Two more constraints from the same Do's/Don'ts guidance (and the bundled FAQ PDF)
apply directly to how Task 5 wires these icons into the matching games:

> Do's: the full Microsoft/Azure service name should always be labeled/displayed
> near the icon when it's shown.
>
> Don'ts: don't use a Microsoft product icon to represent a non-Microsoft product
> or service as if it were the Microsoft one.

In practice: every game screen that shows one of these icons must also display the
icon's real Azure service name, and an icon must never stand in for anything other
than the actual Microsoft/Azure service it depicts.

Icons were extracted from the package's `ai + machine learning` category (all 45
icons) plus the core categories likely to be referenced by the game decks:
`compute`, `storage`, `databases`, `security`, `analytics`, and `identity` —
mirroring how `gamification/assets/aws-icons/` holds more icons than strictly the
AWS decks need.

Fallback-icon mappings for catalogue entries without a dedicated icon in this
release: the game uses an official parent-service or category icon for those
entries.

- Azure AI Video Indexer, Azure Content Understanding, Audio and video content
  analysis, Face detection and tracking, and Scene and shot detection: Azure
  Applied AI Services (no dedicated Video Indexer/Content Understanding icon
  ships in this release; all five are Applied AI Services offerings)
- Automated ML (AutoML) and MLOps / pipelines and model registry: Azure Machine
  Learning
- Chat/completion model deployment, Custom models, DALL-E image generation,
  Embeddings models, and Fine-tuning: Azure OpenAI
- Code interpreter tool, File search tool, and Function calling / custom tools:
  Microsoft Foundry Agent Service
- Custom image classification and Custom object detection: Azure AI Custom
  Vision
- Designer (drag-and-drop pipelines): Machine Learning Studio Workspaces
- Document Translation and Text Translation: Translator Text
- Document field extraction, Layout model, and Prebuilt models: Form
  Recognizers (Azure AI Document Intelligence)
- Face Detection, Face Identification (1:N matching), and Face Verification
  (1:1 matching): Face APIs
- Foundry SDK (AIProjectClient) and Prompt flow and evaluation: AI Foundry
- Image Captioning, OCR / Read API, and Object Detection: Computer Vision
  (Azure AI Vision)
- Image moderation categories, Prompt Shields, and Text moderation categories:
  Content Safety
- Language Detection, Named Entity Recognition (NER), PII Detection and
  Redaction, and Text Summarization: Language (Azure AI Language)
- Multivariate anomaly detection and Univariate anomaly detection: Anomaly
  Detector
- Semantic ranking, Skillsets (AI enrichment), and Vector search: Cognitive
  Search (Azure AI Search)
- Speech Translation, Speech-to-text (speech recognition), Text-to-speech
  (speech synthesis), and Transcription with speaker diarization: Speech
  Services (Azure AI Speech)

Two additional entries use a close-fit icon rather than an exact name match:
Conversational Language Understanding (CLU) uses the Language Understanding
(LUIS) icon, and Model catalog uses the Foundry Models icon.

Any deck entry not covered by a dedicated or parent-service mapping above
falls back to the registry's generic `azure-service` fallback icon
(Cognitive Services), per `ICON_PROVIDERS` in `tools/templates/lab.html` — no
Microsoft/AI-901 entries in the current decks need it, but the registry
requires a default.

The product name remains visible and accessible wherever a fallback icon is
used, matching the AWS icon set's approach (see
`gamification/assets/aws-icons/README.md`).
