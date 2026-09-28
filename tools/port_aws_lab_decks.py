#!/usr/bin/env python3
"""Port the vendor-neutral teaching content out of the AWS lab into shared decks.

    python3 tools/port_aws_lab_decks.py

Reads `gamification/2026 AIF-C01.html`, lifts the JS data structures that carry
no AWS coupling, and writes them as decks under `data/decks/shared/`.

The structures are evaluated by node rather than parsed with regexes. The card
text is 200 KB of hand-authored teaching material and a silently mangled quote
or apostrophe would be indistinguishable from the real thing; evaluating the
literal that the browser itself evaluates cannot drift from it.

This is a one-off migration, kept in the repo so the port is reproducible and
reviewable rather than a pile of hand-edited JSON of unknown provenance.
Re-running it overwrites only the ported decks; authored decks (drift, risk)
live in separate files and are never touched.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "gamification" / "2026 AIF-C01.html"

# The AWS lab is now generated into that same path from a manifest, so once the
# migration has been built the working copy no longer contains the source this
# port reads. The hand-maintained original is the last committed version before
# the migration; read it from there rather than keeping a 200 KB duplicate in
# the tree.
PRE_MIGRATION_REV = "82da7d4"

OUT = REPO / "data" / "decks" / "shared"

WANTED = ["studyGames", "solutionScenarios", "modelDecisionCases", "genaiOpsCases",
          "pipelineStages", "industryPipelineStages", "ragPipelineStages",
          "foundationalTeachingNotes", "metricTeachingNotes", "studyCategoryGuidance"]

AWS_OUT = REPO / "data" / "decks" / "aws"

ASOF = "2026-07"
GUIDE = "AWS Certified AI Practitioner (AIF-C01) exam guide"

# Category -> (deck id, title, blurb, source, area, AIF-C01 domain).
CATEGORIES = {
    "terms":       ("terms", "AI Foundations", "Match each definition to the term it defines.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "concepts":    ("learning-methods", "Learning Methods",
                    "Supervised, unsupervised, self-supervised, reinforcement — and their relatives.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "data":        ("training-data", "Training Data",
                    "Splits, labelling, leakage, imbalance and augmentation.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "fit":         ("fit-tuning", "Fit & Tuning",
                    "Under- and overfitting, regularisation, and what actually moves them.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "metrics":     ("metrics", "Testing Metrics",
                    "Precision, recall, F1, AUC and friends — and when each one lies.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "inference":   ("inference", "Inference",
                    "Batch, real-time, streaming, and the knobs that shape a generation.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "algorithms":  ("algorithms", "ML Algorithms",
                    "Which algorithm family solves which shape of problem.",
                    f"{GUIDE} · Domain 1", "foundations"),
    "prompting":   ("prompting", "Prompting & Risks",
                    "Prompt patterns and the attacks that exploit them.",
                    f"{GUIDE} · Domain 3", "genai"),
    "rag":         ("rag", "RAG", "Retrieval-augmented generation, part by part.",
                    f"{GUIDE} · Domain 3", "genai"),
    "responsible": ("responsible", "Responsible AI",
                    "Fairness, transparency, explainability, safety and their measures.",
                    f"{GUIDE} · Domain 4", "risk"),
}

# The pipelines are authored in the AWS lab as bare ordered strings. A ladder
# reveal has to say why each step sits where it does, so the detail lines are
# written here rather than invented at build time.
STEP_DETAIL = {
    # pipelineStages — the ML lifecycle as the exam guide frames it
    "Business Goal Identification": "Everything downstream inherits this. Without a business goal there is no way to say whether the model is any good.",
    "ML Problem Framing": "Translate the goal into a learnable task: what is predicted, from what, and what counts as success.",
    "Data Collection": "Assemble the raw material, and establish its provenance and permitted use before it is relied on.",
    "Data Preprocessing": "Clean, join, de-duplicate and handle missing values, so the model learns signal rather than artefacts.",
    "Feature Engineering": "Shape inputs into representations the algorithm can use. Often the largest single lever on accuracy.",
    "Model Training": "Fit parameters on the training split. Cheap to repeat, so it comes after the expensive data work, not before.",
    "Hyperparameter Tuning": "Search the settings the model cannot learn for itself, evaluated on validation data rather than test.",
    "Model Evaluation": "Measure against held-out data and the business metric. This is the gate, not a formality.",
    "Model Deployment (Inference and Prediction)": "Serve predictions for real requests, with the same preprocessing as training or the results will not match.",
    "Model Monitoring": "Watch inputs, outputs and quality in production. This is where drift surfaces, and it never ends.",
    # ragPipelineStages
    "Ingest Trusted Source Documents": "Retrieval can only ever surface what was ingested. Source selection is a governance decision, not a plumbing one.",
    "Clean, Split, and Attach Metadata": "Chunking decides what a retrievable unit is; metadata is what later makes filtering and attribution possible.",
    "Create Embeddings for Each Chunk": "Text becomes vectors. The embedding model chosen here constrains everything the retriever can distinguish.",
    "Store Chunks and Vectors in an Index": "The index makes similarity search tractable. Access controls belong here, not only at the answer.",
    "Embed and Interpret the User Query": "The query is embedded by the same model as the chunks, or the two live in incomparable spaces.",
    "Retrieve, Filter, and Rerank Evidence": "Recall decides whether the right passage is available at all; ranking decides whether it survives the context budget.",
    "Build a Prompt with Evidence and Instructions": "The retrieved evidence is placed in the prompt with instructions on how to use it and when to refuse.",
    "Generate, Validate, and Cite the Grounded Answer": "The model answers from the supplied evidence and cites it, so a reader can check rather than trust.",
    # industryPipelineStages — the fuller lifecycle as it runs in practice
    "Understand the Business Problem and Stakeholders": "Who is affected, who decides, and what a good outcome is for them. Skipping this is how technically sound models get built for the wrong problem.",
    "Define the ML Task, Constraints, and Success Metrics": "Fix the target, the latency and cost budget, and the metric before any data is touched, so success cannot be redefined after the fact.",
    "Source Data and Establish Governance": "Establish lawful basis, licence, consent and retention up front. Data acquired without them is a liability that no later step removes.",
    "Ingest, Catalogue, and Version Data": "Land the data with a catalogue entry and a version. Without versioning no result is reproducible and no regression is explainable.",
    "Explore Data and Validate Quality": "Profile distributions, nulls, duplicates and outliers before modelling, because every one of them shows up later as unexplained error.",
    "Clean, Transform, and Label Data": "Repair what can be repaired and label what needs labels, with the labelling guidance itself treated as a versioned artefact.",
    "Engineer and Select Features": "Build the representations the model will use, and drop the ones that leak the target or will not exist at inference time.",
    "Create Training, Validation, and Test Splits": "Split before fitting anything, respecting time and group boundaries. A split made after preprocessing has already leaked.",
    "Build a Reproducible Baseline": "A simple model that runs end to end. It sets the bar every later candidate must clear and proves the pipeline works.",
    "Train Candidate Models and Track Experiments": "Fit alternatives with their configuration, data version and results recorded, so the winner can be rebuilt months later.",
    "Tune Hyperparameters with Validation Data": "Search settings against validation data only. Tuning against test data turns the final number into self-assessment.",
    "Evaluate Quality, Robustness, Fairness, and Security": "Test held-out quality, behaviour under perturbation, performance by subgroup, and adversarial exposure. One aggregate accuracy number hides all three of the others.",
    "Document, Approve, Package, and Register the Model": "Record intended use, limits and evaluation results, get the accountable approval, and register the artefact. This is what makes deployment reviewable.",
    "Deploy Gradually with Automated Tests and Rollback": "Shadow, canary or staged rollout with a tested path back. Gradual exposure is what makes a bad release survivable.",
    "Monitor Data, Model, System, and Business Performance": "Watch all four layers. Inputs drift, quality decays, infrastructure fails and business value erodes — and they are not the same signal.",
    "Collect Feedback, Retrain, Revalidate, or Retire": "Feed production reality back in, and decide deliberately between retraining, revalidating and retirement. A model with no retirement criterion never gets retired.",
}


def extract(src: str) -> dict:
    """Evaluate the wanted declarations with node and return them as data."""
    blocks = []
    for name in WANTED:
        m = re.search(r"(const %s = (?:\[|\{|`).*?\n    (?:\]|\}|`);)" % name, src, re.S)
        if not m:
            raise SystemExit(f"could not find declaration: {name}")
        blocks.append(m.group(1))
    script = "\n".join(blocks) + "\nconsole.log(JSON.stringify({%s}));\n" % ",".join(WANTED)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp = f.name
    try:
        out = subprocess.run([_node(), tmp], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"node failed to evaluate the extracted literals:\n{e.stderr}")
    finally:
        Path(tmp).unlink(missing_ok=True)
    return json.loads(out.stdout)


def extract_aws(src: str) -> dict:
    """Build the two AWS-only decks by running the lab's own matcher logic.

    `featureClue` is reused rather than reimplemented: it throws when a feature
    has no clue rule, and again when a clue would give its own answer away.
    Both guards are worth keeping, so the port fails loudly here exactly as the
    page would have failed in the browser.
    """
    # Each declaration gets its own terminator: a single permissive pattern
    # runs past the end of the template literal and swallows the declarations
    # that follow it.
    blocks = []
    for name, end in [("rawServices", r"`;"),
                      ("featureDisplayNames", r"\n    \}\)\);"),
                      ("featureClueRules", r"\n    \];")]:
        m = re.search(r"(const %s = .*?%s)" % (name, end), src, re.S)
        if not m:
            raise SystemExit(f"could not find declaration: {name}")
        blocks.append(m.group(1))
    for fn in ["featureName", "featureClue"]:
        m = re.search(r"(function %s\(.*?\n    \})" % fn, src, re.S)
        if not m:
            raise SystemExit(f"could not find function: {fn}")
        blocks.append(m.group(1))
    script = "\n".join(blocks) + """
const services = rawServices.trim().split("\\n").map(row => {
  const [name, category, purpose, features] = row.split("|");
  return { name: name.trim(), category: category.trim(), purpose: purpose.trim(),
           features: features.split(";").map(v => v.trim()) };
});
const out = services.map(s => ({
  name: s.name, category: s.category, purpose: s.purpose,
  features: s.features.map(f => ({ name: featureName(f), clue: featureClue(f) })),
}));
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp = f.name
    try:
        res = subprocess.run([_node(), tmp], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"node rejected the AWS service data:\n{e.stderr}")
    finally:
        Path(tmp).unlink(missing_ok=True)
    return json.loads(res.stdout)


def _node() -> str:
    from shutil import which
    node = which("node")
    if not node:
        raise SystemExit("node is required to evaluate the AWS lab's JS literals")
    return node


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:44]


def write(deck: dict) -> None:
    path = OUT / f"{deck['id']}.json"
    path.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = len(deck.get("items") or deck.get("ladders") or deck.get("pairs") or [])
    print(f"  {path.relative_to(REPO)}  ({n})")


def read_source() -> str:
    """The hand-maintained AWS lab, from the working tree or from git."""
    if SRC.is_file():
        text = SRC.read_text(encoding="utf-8")
        if "const rawServices" in text:
            return text
    rel = SRC.relative_to(REPO).as_posix()
    res = subprocess.run(["git", "-C", str(REPO), "show", f"{PRE_MIGRATION_REV}:{rel}"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(
            f"the working copy of {rel} is the generated lab, and the pre-migration "
            f"original could not be read from {PRE_MIGRATION_REV}:\n{res.stderr.strip()}")
    return res.stdout


def main() -> int:
    src = read_source()
    d = extract(src)
    OUT.mkdir(parents=True, exist_ok=True)
    notes = {**d["foundationalTeachingNotes"], **d["metricTeachingNotes"]}
    print("porting vendor-neutral decks out of the AWS lab:")

    # 1. Ten term/definition matching decks.
    for cat, pairs in d["studyGames"].items():
        deck_id, title, blurb, source, area = CATEGORIES[cat]
        items = []
        for i, (term, definition) in enumerate(pairs, 1):
            items.append({
                "id": f"{deck_id}-{i:02d}",
                "label": definition,
                "answer": term,
                # A teaching note says something the definition does not; where
                # one exists it is strictly better as the reveal text.
                "why": notes.get(term, definition),
            })
        write({"id": deck_id, "runner": "board", "title": title, "blurb": blurb,
               "source": source, "asOf": ASOF, "area": area,
               "hint": d["studyCategoryGuidance"].get(cat,
                       "Drag each definition onto the term it defines."),
               "items": items})

    # 2. Scenario -> technique.
    write({"id": "solution-builder", "runner": "board",
           "title": "Solution Builder", "blurb": "Pick the technique the problem actually calls for.",
           "source": f"{GUIDE} · Domain 1", "asOf": ASOF, "area": "foundations",
           "hint": "Read the data and the desired output, then drag each scenario onto its technique.",
           "items": [{"id": f"sol-{i:02d}", "label": s["scenario"], "sub": s["title"],
                      "answer": s["technique"],
                      "why": f'{s["why"]} {s["outcome"]}'}
                     for i, s in enumerate(d["solutionScenarios"], 1)]})

    # 3. Decision decks. These were one-card-at-a-time option buttons; as boards
    #    they keep every word of their content but stop being a quiz.
    for key, deck_id, title, blurb, source, area in [
        ("modelDecisionCases", "model-decisions", "Model Decision Lab",
         "Choose the move that addresses the actual cause.", f"{GUIDE} · Domain 3", "genai"),
        ("genaiOpsCases", "genai-ops", "GenAI Evaluation & Ops",
         "Diagnose the failure, then pick the intervention that fits it.",
         f"{GUIDE} · Domain 3", "ops"),
    ]:
        items = []
        for i, c in enumerate(d[key], 1):
            # One drift card is deliberately dropped here: it is re-authored,
            # with the rest of drift, into the drift decks so the topic is
            # taught in exactly one place.
            if c["title"] == "Input Population Has Shifted":
                continue
            items.append({"id": f"{deck_id}-{i:02d}", "label": c["context"], "sub": c["title"],
                          "options": c["options"], "answer": c["options"][c["best"]],
                          "why": f'{c["explanation"]} Trade-off: {c["tradeoff"]}'})
        write({"id": deck_id, "runner": "board", "title": title, "blurb": blurb,
               "source": source, "asOf": ASOF, "area": area, "zoneMode": "options",
               "hint": "Drag each situation onto the response it calls for. "
                       "Some responses on the board are there to tempt you.",
               "items": items})

    # 4. Ladders.
    for key, deck_id, title, blurb, prompt, source, area in [
        ("pipelineStages", "ml-lifecycle", "ML Lifecycle",
         "Put the machine-learning lifecycle in order.",
         "Order the lifecycle from business goal to production monitoring.",
         f"{GUIDE} · Domain 1", "foundations"),
        ("industryPipelineStages", "industry-lifecycle", "Industry ML Pipeline",
         "The fuller lifecycle as it runs in practice.",
         "Order the pipeline as it actually runs in an organisation.",
         "Industry ML delivery practice", "ops"),
        ("ragPipelineStages", "rag-pipeline", "RAG Builder",
         "Assemble a retrieval-augmented generation pipeline.",
         "Order the stages from ingestion to a grounded, cited answer.",
         f"{GUIDE} · Domain 3", "genai"),
    ]:
        steps = [{"label": s, "detail": STEP_DETAIL.get(s, "")} for s in d[key]]
        missing = [s["label"] for s in steps if not s["detail"]]
        if missing:
            print(f"  ! {deck_id}: {len(missing)} steps have no detail line; "
                  f"add them to STEP_DETAIL", file=sys.stderr)
            for m in missing:
                print(f"      {m}", file=sys.stderr)
            return 1
        write({"id": deck_id, "runner": "ladders", "title": title, "blurb": blurb,
               "source": source, "asOf": ASOF, "area": area,
               "ladders": [{"id": deck_id, "title": title, "prompt": prompt, "steps": steps}]})

    # 5. The two genuinely AWS-specific decks.
    AWS_OUT.mkdir(parents=True, exist_ok=True)
    services = extract_aws(src)
    print("porting the AWS-only decks:")

    svc_items = [{"id": f"svc-{i:03d}", "label": s["purpose"], "answer": s["name"],
                  "why": f'{s["name"]} is the AWS offering designed to {s["purpose"][0].lower()}{s["purpose"][1:]}.'}
                 for i, s in enumerate(services, 1)]
    _write_aws({"id": "services", "runner": "board", "title": "Service to Purpose",
                "blurb": "Match each purpose to the AWS service built for it.",
                "source": f"{GUIDE} · in-scope AWS services", "asOf": ASOF, "area": "aws",
                "hint": "Drag each purpose onto the service that exists to do it.",
                "items": svc_items})

    # Feature cards carry their clue as the token and the capability as the
    # answer, matching the original panel. The owning service is deliberately
    # not shown on the token — with zones drawn from six different services it
    # would hand over the answer — so it appears only in the reveal.
    # Ids are positional rather than slugged. Feature names run long, and a
    # truncated slug would collide silently — the build's uniqueness check
    # would then report a duplicate id instead of the real problem.
    unique = []
    for si, s in enumerate(services):
        for fi, f in enumerate(s["features"]):
            unique.append({"id": f"feat-{si:03d}-{fi:02d}",
                           "label": f["clue"], "answer": f["name"],
                           "why": f'{f["name"]} belongs to {s["name"]}, and enables this job: {f["clue"]}'})
    _write_aws({"id": "features", "runner": "board", "title": "Feature to Function",
                "blurb": "Match each job to the capability that does it.",
                "source": f"{GUIDE} · in-scope AWS services", "asOf": ASOF, "area": "aws",
                "hint": "Drag each job onto the capability that performs it. The reveal names the service it belongs to.",
                "items": unique})
    return 0


def _write_aws(deck: dict) -> None:
    path = AWS_OUT / f"{deck['id']}.json"
    path.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {path.relative_to(REPO)}  ({len(deck['items'])})")


if __name__ == "__main__":
    sys.exit(main())
