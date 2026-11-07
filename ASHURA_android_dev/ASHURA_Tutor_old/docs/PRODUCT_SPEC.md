# ASHURA Tutor

## Complete Product, Architecture and Engineering Specification

### Version 5.0 — Offline-first Android learning platform

**Status:** Proposed implementation blueprint  
**Primary objective:** Build a useful, dependable, free-to-use
educational platform from the first runnable version to a
production-ready release.  
**Important:** This document describes the target design and
implementation plan. It does not claim that the features have already
been implemented, tested, or proven effective.

------------------------------------------------------------------------

# 0. Executive decision

ASHURA Tutor is an **offline-first, Android-first learning platform**.
It is not simply a chat interface connected to a small language model.

Its job is to help a learner:

1.  Learn foundational concepts from school level.
2.  Progress through secondary and higher-secondary education.
3.  Study bachelor’s-level subjects.
4.  Study selected master’s-level topics with appropriate caveats and
    source material.
5.  Understand concepts through explanations, examples, diagrams,
    practice and feedback.
6.  Import and study their own books, notes, PDFs, images and office
    documents.
7.  Search the web when connected, while continuing to work without
    internet.
8.  Track understanding and revisit weak concepts.
9.  Use maths, science, programming and document tools that are more
    reliable than free-form language-model output.
10. Keep their learning history and personal documents under their
    control.

The platform should be useful with no account, no paid API, no mandatory
cloud service and no internet connection for its core functions.

## 0.1 Product principle

**The language model is one component of the tutor, not the tutor
itself.**

A small local model can interpret questions, explain concepts, generate
practice and communicate naturally. It should not be expected to perform
every task by itself. ASHURA combines the model with:

- A curriculum and concept structure.
- Local retrieval over trusted learning material.
- Deterministic subject tools.
- Document extraction and OCR.
- Assessment and learning-state logic.
- Verification and evidence tracking.
- Optional online research.
- Strict device-resource management.

This is how the app can achieve better reliability without requiring a
large model to run continuously on a low-memory phone.

## 0.2 Primary design constraints

| Constraint                                   | Design response                                                                          |
|----------------------------------------------|------------------------------------------------------------------------------------------|
| 4 GB Android phones are an important target  | One model at a time, bounded context, serial heavy tasks and aggressive memory awareness |
| 6 GB devices are a more comfortable baseline | Enable more document and retrieval work, subject to measurement                          |
| 8 GB+ devices may support enhanced features  | Optional larger models, more context or multimodal components                            |
| Must work offline                            | Local inference, local content, local database and deterministic tools                   |
| Must not require paid services               | No mandatory paid API, hosting, analytics or account                                     |
| Must not hang the phone                      | Background workers, cancellation, bounded queues, memory/thermal policies                |
| Must support broad education levels          | Curriculum metadata, learner-level adaptation and source-grounded advanced study         |
| Small model may be inaccurate                | Retrieval, specialist tools, verification, evaluation and uncertainty handling           |
| Model training may be useful later           | Keep a future training interface, but do not make it a launch dependency                 |

## 0.3 What “free” means

The intended product has no mandatory subscription or paid inference
API. This does not mean every external dependency is costless or
guaranteed forever. Users may still need internet bandwidth for web
research or downloads. Developers may incur publishing, signing, hosting
or hardware costs. Kaggle access, accelerator quotas, model licenses and
third-party service terms can change.

------------------------------------------------------------------------

# 1. Product definition and learning experience

## 1.1 Target learners

ASHURA should support a progression of learner profiles rather than
hard-code one grade system.

| Learner band     | Typical needs                                     | Tutor behavior                                                                |
|------------------|---------------------------------------------------|-------------------------------------------------------------------------------|
| Primary          | Literacy, numeracy, basic science                 | Short sentences, concrete examples, visual explanations, frequent checks      |
| Lower secondary  | Core concepts, problem solving                    | Guided examples, definitions, practice and misconception correction           |
| Upper secondary  | Deeper subject knowledge and exam preparation     | Multi-step explanations, formula use, structured revision                     |
| Higher secondary | Abstract concepts and preparation for university  | More formal notation, derivations and independent problem solving             |
| Bachelor’s       | Course-level depth, projects and technical skills | Prerequisite checks, detailed explanations, references and problem sets       |
| Master’s         | Advanced topic exploration and research literacy  | Explicit assumptions, specialist sources, critical comparison and uncertainty |

The app must not claim that a small offline model is a substitute for a
qualified lecturer, supervisor, clinician, lawyer or other professional.
For advanced topics, it should help the learner understand material,
navigate sources and test their own reasoning.

## 1.2 Core learning modes

### A. Learn a topic

The learner selects a subject, level and topic, or asks in natural
language.

The tutor should:

1.  Check prerequisites when relevant.
2.  Give a concise overview.
3.  Explain the concept in manageable steps.
4.  Define unfamiliar terms.
5.  Use a worked example.
6.  Ask a question to check understanding.
7.  Adjust the next explanation based on the response.
8.  Offer practice and a short recap.

### B. Ask a question

A conversational interface accepts typed questions, pasted text, images
and supported documents. It identifies whether the user needs an
explanation, calculation, source lookup, document answer or another
action.

It should not force the learner into a rigid questionnaire for ordinary
questions.

### C. Socratic tutor

The tutor can guide a learner without immediately revealing the answer.

Possible behavior: - Ask what the learner has tried. - Give a small
hint. - Ask the learner to complete the next step. - Detect a
misconception. - Reveal a worked solution when requested or when the
learner is stuck.

The learner must be able to switch to a direct explanation. Socratic
mode must not become an obstacle.

### D. Practice and exam preparation

Generate questions from a selected topic, level or imported source.
Support: - Multiple choice. - Short answer. - Numerical problems. -
Step-by-step problem solving. - Flashcards. - Timed practice as an
optional mode. - Topic-based revision sets. - Mistake review.

Every generated answer key should be checked where possible by
deterministic tools, source material or an independent evaluation path.
Generated questions should be labelled as generated practice, not
official examination questions.

### E. Explain my mistake

The learner submits an answer or a solution attempt. ASHURA should
identify: - The first incorrect step, if identifiable. - The concept
behind the error. - Why the step is incorrect. - A corrected method. - A
similar practice problem.

Do not merely label an answer “wrong”.

### F. Study my material

The learner imports a PDF, image, DOCX, XLSX, PPTX, text file or other
supported format. The app extracts text, preserves provenance and makes
it searchable. The learner can ask questions about the material,
summarize sections, create revision notes and generate practice.

### G. Research and compare

When online access is allowed, the app searches for current or
additional sources, extracts relevant passages and shows the source
title, publisher, URL and retrieval date. It distinguishes retrieved
evidence from model-generated explanation.

### H. Programming tutor

The app explains programming concepts, reads code, helps debug and
teaches through small exercises. Code execution is optional and must be
sandboxed. If safe execution is unavailable on a device, ASHURA should
provide static analysis and explanation rather than execute arbitrary
code.

## 1.3 Learning conversation structure

A useful answer is not just a block of text. The response model should
support structured sections:

- Direct answer.
- Explanation.
- Worked example.
- Formula or code block, where relevant.
- Source evidence.
- Practice question.
- Confidence/limitations.
- Related concepts.

Not every answer needs every section. The response composer selects only
what helps.

## 1.4 Language support

Initial language targets: - English. - Nepali, with explicit testing of
educational terminology and mixed-language input.

Design language packs so additional languages can be added later. Do not
claim reliable multilingual support simply because a base model lists a
language. Test: - Reading comprehension. - Technical vocabulary. -
Mathematical word problems. - Script handling. - Speech recognition and
text-to-speech separately.

------------------------------------------------------------------------

# 2. Product capability map

## 2.1 Core capabilities

| Capability                | Initial release priority |                   Offline? | Main implementation                     |
|---------------------------|-------------------------:|---------------------------:|-----------------------------------------|
| Text tutor                |                       P0 |                        Yes | Local LLM + task controller             |
| Learn-topic flow          |                       P0 |                        Yes | Lesson planner + curriculum metadata    |
| Practice and feedback     |                       P0 |                        Yes | Assessment engine + verifier            |
| Calculator                |                       P0 |                        Yes | Deterministic arithmetic                |
| Local notes and history   |                       P0 |                        Yes | Room/SQLite                             |
| Local document import     |                       P1 |                        Yes | Format parsers                          |
| PDF text extraction       |                       P1 |                        Yes | PDF parser                              |
| Scanned PDF/image OCR     |                       P1 |                        Yes | On-device OCR                           |
| DOCX/XLSX/PPTX extraction |                       P1 |                        Yes | Office parsers                          |
| Local document search     |                       P1 |                        Yes | SQLite FTS5                             |
| Learning progress         |                       P1 |                        Yes | Mastery and review engine               |
| Web research              |                       P2 |                         No | Search and source extraction            |
| Speech input/output       |                       P2 |                    Depends | Offline/online STT and TTS adapters     |
| Diagrams and simulations  |                       P2 | Yes, for local simulations | Native rendering and specialist modules |
| Programming sandbox       |                       P2 |   Yes if sandbox supported | Restricted execution                    |
| Advanced multimodal model |                       P3 |                    Depends | Optional device tier                    |
| User-triggered model SFT  |                    Later |              No, generally | Optional training service               |

P0 means required for a credible first usable tutor, not that every
feature must ship in the first APK. P1/P2/P3 are sequenced after the
core is stable.

## 2.2 Capability boundaries

- OCR extracts text; it does not automatically understand every chart,
  handwriting sample or complex page layout.
- Text extraction from a normal PDF is different from OCR on a scanned
  PDF.
- Spreadsheet extraction must preserve sheet names, cell locations and
  table relationships.
- A language model may explain a formula, but a calculation engine
  should verify arithmetic.
- Web search can provide fresh sources, but search snippets alone are
  not adequate evidence for complex claims.
- A generated diagram may be illustrative rather than mathematically
  exact. For exact plots, use a plotting engine.
- A small model can assist with master’s-level study when given good
  source material; it cannot guarantee comprehensive expert-level
  coverage offline.

------------------------------------------------------------------------

# 3. User interface and navigation

## 3.1 Main navigation

Use a small number of stable destinations. Avoid a crowded “everything
dashboard”.

Recommended bottom navigation:

1.  **Home** — continue learning, recent work and quick actions.
2.  **Tutor** — conversation and learning modes.
3.  **Library** — books, notes, documents and course material.
4.  **Progress** — mastery, weak areas, revision schedule and assessment
    history.
5.  **Settings** — models, offline packs, language, privacy, storage and
    diagnostics.

Training is not a primary navigation item at launch. It may later appear
under Advanced / Model management.

## 3.2 Home screen

The home screen should prioritize: - Continue last lesson. - Today’s
review. - Ask a question. - Learn a topic. - Import material. - Recent
documents. - Offline status.

Avoid excessive cards, decorative gauges and constant AI-generated
recommendations. The app should load quickly and make the next learning
action obvious.

## 3.3 Tutor screen

Required UI states: - Empty prompt. - Typing/generating. - Streaming
response. - Tool in progress (e.g. reading a PDF or calculating). -
Cancellation. - Offline state. - Model unavailable. - Low-memory
pause. - Error with recovery action.

The UI must never imply that the model is still working when the request
has failed or been cancelled.

## 3.4 Library screen

Organize by: - Imported documents. - Notes. - Course/subject
collections. - Downloaded knowledge packs. - Recent items.

Each imported item shows processing status, size, source, date and
whether it is indexed. Provide delete and re-index controls.

## 3.5 Progress screen

Show understandable learning indicators: - Topics learned. - Topics to
review. - Recent assessment results. - Repeated misconceptions. -
Learning streak only if it does not distort learning behavior.

Avoid presenting a false precision score such as “87.43% intelligence”.
Mastery is an estimate based on evidence and should be described as
such.

## 3.6 Accessibility

Support: - Dynamic font size. - Screen readers and semantic labels. -
Sufficient contrast. - Keyboard navigation where relevant. - Reduced
motion. - Clear mathematical typography. - Text alternatives for
diagrams. - Downloadable/offline content.

------------------------------------------------------------------------

# 4. System architecture

## 4.1 Architecture style

Use a **modular monolith** for the Android application. Do not begin
with microservices, a mandatory backend or a complicated multi-agent
network.

The app has clear modules and interfaces. Components can be replaced
without rewriting the product.

``` text
                 ANDROID APP
+----------------------------------------------------+
| Jetpack Compose UI                                 |
| Home | Tutor | Library | Progress | Settings       |
+-------------------------+--------------------------+
                          |
+-------------------------v--------------------------+
| Presentation / ViewModels / UI State               |
+-------------------------+--------------------------+
                          |
+-------------------------v--------------------------+
| Application Layer                                  |
| Use Cases | Task Controller | Planner | Scheduler  |
+-------------------------+--------------------------+
                          |
+-------------------------v--------------------------+
| Domain Interfaces                                  |
| Tutor | Model | Retrieval | Documents | Learning    |
| Assessment | Tools | Research | Storage             |
+-------------------------+--------------------------+
                          |
+-------------------------v--------------------------+
| Implementations                                    |
| Local LLM | SQLite | OCR | Parsers | Math | Search  |
| Speech | Code Sandbox | Verification                |
+----------------------------------------------------+
             |                       |
       LOCAL DEVICE             OPTIONAL ONLINE
       files/database           web search
       model/runtime            future training
       OCR/tools                optional services
```

## 4.2 Layer responsibilities

| Layer             | Responsibilities                                      | Must not do                                 |
|-------------------|-------------------------------------------------------|---------------------------------------------|
| UI                | Screens, accessibility, rendering, user actions       | Load models or run OCR on main thread       |
| Presentation      | ViewModels, state, event mapping                      | Contain business rules                      |
| Application       | Use cases, orchestration, cancellation, task planning | Depend directly on a specific model runtime |
| Domain            | Entities, policies, interfaces                        | Depend on Android SDK or provider SDKs      |
| Data              | Database, file metadata, repositories, migrations     | Decide teaching strategy                    |
| Engines           | Inference, OCR, parsers, retrieval and tools          | Run unbounded work                          |
| Platform adapters | Android storage, scheduling, network, secure storage  | Leak platform details into domain           |

## 4.3 Request lifecycle

``` text
User input
  -> normalize and validate
  -> identify task and learner context
  -> decide which evidence/tools are needed
  -> retrieve local material if relevant
  -> execute deterministic tools
  -> call local model for interpretation/explanation
  -> verify important claims/results
  -> compose answer with evidence and limitations
  -> display answer
  -> optionally record a learning event
```

## 4.4 Why not multi-agent first?

A set of named agents does not automatically make a tutor more
intelligent. Multiple model calls can increase latency, memory pressure
and failure points. Start with explicit task handlers and specialist
tools. Add separate agents only when an independently testable
capability needs its own planning, state or tool permissions.

------------------------------------------------------------------------

# 5. Task controller and routing algorithms

## 5.1 Task categories

At minimum: - General explanation. - Learn a topic. - Practice
generation. - Answer evaluation. - Arithmetic/calculation. - Mathematics
problem. - Science problem. - Document question. - Summarization. -
Programming explanation/debugging. - Web research. -
Translation/language learning. - Study planning. - Unknown/ambiguous.

## 5.2 Task routing

Prefer deterministic routing for obvious tasks. Use the local model to
interpret ambiguous natural language, not to decide every implementation
detail.

``` python
def route(request, device, settings):
    task = rules_classifier(request)

    if task.is_ambiguous:
        task = small_model_classifier(request, max_tokens=96)

    plan = TaskPlan()

    if task.kind == "calculation":
        plan.tools = ["calculator"]
        plan.model_role = "explain_result"
        plan.verify = ["recompute"]
    elif task.kind == "document_question":
        plan.tools = ["document_parser", "local_retrieval"]
        plan.model_role = "answer_from_evidence"
        plan.verify = ["source_coverage"]
    elif task.kind == "programming":
        plan.tools = ["static_code_analysis"]
        if settings.safe_code_execution:
            plan.tools.append("sandbox")
        plan.model_role = "programming_tutor"
        plan.verify = ["tests_if_available"]
    elif task.kind == "web_research":
        if request.online_permission and device.network_available:
            plan.tools = ["web_search", "source_extractor"]
        else:
            plan.tools = ["local_retrieval"]
        plan.model_role = "synthesize_sources"
    else:
        plan.tools = ["local_retrieval"]
        plan.model_role = "tutor"

    plan.resource_budget = make_budget(task, device)
    return validate_plan(plan, request, settings)
```

## 5.3 Resource budget

Every task receives: - Maximum wall-clock time. - Maximum model output
tokens. - Maximum context tokens. - Maximum document pages per batch. -
Maximum tool calls. - Maximum retries. - Cancellation token. - Memory
ceiling.

Do not let the model request unlimited tools, context or retries.

## 5.4 Retry policy

1.  Retry transient I/O failures only when safe.
2.  Do not retry a deterministic failure repeatedly.
3.  For a questionable answer, run one independent check if available.
4.  If the check fails, ask for clarification or explain uncertainty.
5.  Stop at the task’s retry budget.

No infinite self-reflection loop.

------------------------------------------------------------------------

# 6. Local model strategy

## 6.1 Starting model

Use **Qwen2.5-1.5B-Instruct as the initial candidate**, not as a
permanent unquestionable choice. It is a practical starting point for
low-resource testing. The product’s accuracy must come from the full
system and evaluation, not the model name.

The runtime should allow later comparisons with: -
DeepSeek-R1-Distill-Qwen-1.5B. - LFM3-1.7B. - Other compatible models
that pass the same device tests.

Do not load multiple models simultaneously on 4 GB devices.

## 6.2 Runtime interface

``` kotlin
interface LocalModelRuntime {
    suspend fun load(manifest: ModelManifest, budget: ResourceBudget): LoadResult
    fun generate(request: GenerationRequest): Flow<GenerationEvent>
    suspend fun cancel(requestId: String)
    suspend fun unload(): UnloadResult
    suspend fun health(): RuntimeHealth
}
```

The application layer should not depend on a particular inference
engine. Evaluate Android-compatible runtimes for: - Supported model
format. - CPU and accelerator compatibility. - Memory use. - Token
generation speed. - Streaming support. - Cancellation. - Quantization
support. - License and maintenance status.

## 6.3 Model configuration

Keep model settings in a versioned manifest: - Model identifier and
exact revision. - Tokenizer revision/hash. - Chat template. -
Quantization format. - Context limit used by the app. - Runtime
compatibility. - License. - Artifact checksum. - Recommended memory
tier.

Never assume a model’s advertised maximum context is safe on a phone. KV
cache and runtime overhead consume memory.

## 6.4 Model selection score

Compare candidates on the same task suite and hardware.

``` text
overall_score =
    0.40 * verified_answer_accuracy
  + 0.15 * grounded_answer_accuracy
  + 0.10 * tool_selection_success
  + 0.10 * explanation_quality
  + 0.10 * language_quality
  + 0.10 * latency_score
  + 0.05 * memory_score
```

This is a starting weighting, not a universal scientific truth. Hard
gates override the weighted score: a model that leaks private data,
crashes or exceeds the memory budget is rejected.

------------------------------------------------------------------------

# 7. The teaching engine

This is the central product capability. It must be designed
independently from the language model.

## 7.1 Lesson object

A lesson should contain: - Subject. - Education level. - Topic and
prerequisite concepts. - Learning objectives. - Key vocabulary. -
Explanation outline. - Worked examples. - Misconceptions. - Practice
questions. - Assessment criteria. - Source references.

The model can adapt the wording, but the lesson structure and learning
objectives should remain inspectable.

## 7.2 Lesson algorithm

``` python
def teach_topic(student, topic, mode):
    objectives = curriculum.get_objectives(topic, student.level)
    prerequisites = curriculum.get_prerequisites(topic)

    diagnostic = assess_prerequisites(student, prerequisites)
    if diagnostic.has_gaps:
        teach_missing_prerequisites(diagnostic.gaps)

    lesson = lesson_planner.build(topic, objectives, mode)
    explanation = tutor.explain(lesson, student.language, student.level)

    example = choose_verified_example(topic)
    present(explanation, example)

    response = ask_check_for_understanding(topic)
    result = assess_response(response, objectives)

    if result.misconception:
        teach_alternative_explanation(result.misconception)
        assign_similar_practice()
    else:
        assign_transfer_question()

    update_learning_state(result)
```

## 7.3 Misconception model

Store misconception categories by concept, not just a raw transcript.

Examples: - Confuses velocity and acceleration. - Treats division as
always reducing a number. - Applies an algebraic operation to only one
side of an equation. - Confuses correlation with causation. - Uses a
programming variable before initialization.

A misconception record should include evidence, date, confidence and
whether the learner later corrected it.

## 7.4 Adaptive explanation

The tutor can change: - Vocabulary complexity. - Explanation length. -
Number of intermediate steps. - Example familiarity. - Use of
diagrams. - Amount of scaffolding.

It must not silently lower the learning objective. Simplify the
explanation, not the underlying concept.

## 7.5 Spaced repetition

Use a simple, testable schedule first. Do not introduce a complicated
learning algorithm without evidence.

``` python
def schedule_review(mastery, confidence, previous_interval, outcome):
    if outcome == "incorrect":
        return short_retry_interval()
    if outcome == "correct_with_help":
        return modest_interval(previous_interval)
    if outcome == "correct_independently":
        return increase_interval(previous_interval, mastery, confidence)
```

Record independent success separately from success after hints.

------------------------------------------------------------------------

# 8. Curriculum and knowledge architecture

## 8.1 Curriculum is metadata, not a giant hard-coded textbook

Represent subjects and topics as versioned data packs.

``` text
Curriculum
  -> Education level
      -> Subject
          -> Course
              -> Unit
                  -> Topic
                      -> Learning objectives
                      -> Prerequisites
                      -> Misconceptions
                      -> Practice blueprint
                      -> Source references
```

This allows new curricula to be added without changing the app’s core
code.

## 8.2 Curriculum packs

A pack should include: - Stable pack ID and version. - Language and
region. - Education level. - Subject taxonomy. - Topic IDs and
prerequisite graph. - Learning objectives. - Exam alignment metadata
where licensed. - Source list and licenses. - Checksums and signature.

Do not bundle copyrighted textbooks without permission. A curriculum
outline or metadata pack is not permission to redistribute a book.

## 8.3 Broad education levels

The app should not pretend to have a complete global curriculum at
launch. Start with a small, carefully validated set of subjects and
levels. Expand by adding content packs and tests.

Suggested initial subject families: - Mathematics. - Physics. -
Chemistry. - Biology. - Computer science/programming. - English and
language learning. - General science and study skills.

Advanced subject coverage grows through verified content and specialist
modules.

------------------------------------------------------------------------

# 9. Document intelligence: PDFs, Office files and images

## 9.1 Import formats

Initial supported formats: - TXT, Markdown and CSV. - Text-based PDF. -
Scanned PDF. - JPG, PNG and other supported image formats. - DOCX. -
XLSX. - PPTX.

Additional formats can be added through parser adapters after security
and resource testing.

## 9.2 Correct extraction path

``` text
File selected
  -> validate type, size and permissions
  -> store original in app-private storage
  -> identify actual content
  -> if text PDF: extract text and page positions
  -> if scanned PDF: render one page/batch and OCR
  -> if DOCX: extract paragraphs, headings and tables
  -> if XLSX: extract sheets, ranges, formulas and values
  -> if PPTX: extract slide text, notes and image references
  -> normalize and chunk
  -> retain page/sheet/slide provenance
  -> index locally
```

Do not OCR a text-based PDF unnecessarily. Do not flatten a spreadsheet
into unlabelled text if sheet and cell coordinates can be retained.

## 9.3 OCR

Use on-device OCR where available and suitable. OCR should: - Detect
orientation. - Support language packs. - Process bounded image
dimensions. - Handle one page or a small batch at a time. - Return
confidence where supported. - Preserve page number and bounding boxes
when available. - Allow user correction for poor recognition.

OCR errors must not be silently presented as exact quotations.

## 9.4 Document chunking

Each chunk retains: - Document ID. - Page, slide, sheet or section. -
Heading path. - Cell range where applicable. - Text. - Extraction
method. - OCR confidence if applicable. - Original file hash.

This makes answers traceable to the imported source.

## 9.5 Document question algorithm

``` python
def answer_from_document(question, document_ids):
    chunks = local_search(question, document_ids, limit=30)
    chunks = rerank_and_deduplicate(chunks)
    if not chunks or not evidence_is_relevant(chunks):
        return explain_no_sufficient_evidence()

    answer = model.answer(
        question=question,
        evidence=bounded_context(chunks),
        instruction="Answer only what the supplied evidence supports."
    )
    check = evidence_coverage_check(answer, chunks)

    if not check.supported:
        return answer_with_uncertainty_or_request_more_context()

    return attach_page_sheet_slide_citations(answer, chunks)
```

## 9.6 Spreadsheet-specific behavior

Support: - Sheet listing. - Table/range extraction. - Formula and
displayed-value distinction where available. - Row/column headers. -
Basic summaries. - Question answering over selected ranges.

Do not treat a workbook as a single flat paragraph.

------------------------------------------------------------------------

# 10. Local knowledge retrieval

## 10.1 Start with SQLite FTS5

Use full-text search before adding vector embeddings. It is lightweight,
local and easy to inspect. Embeddings are optional and must demonstrate
a measurable retrieval improvement.

## 10.2 Retrieval pipeline

``` python
def retrieve(query, filters, limit):
    candidates = fts5_search(query, filters, top_k=50)
    candidates = remove_duplicates(candidates)
    candidates = boost_title_and_heading_matches(candidates)
    candidates = filter_by_subject_and_level(candidates)

    if embedding_index_available() and resource_budget_allows():
        candidates = rerank_with_embeddings(query, candidates)

    return diversify_by_document(candidates, limit)
```

## 10.3 Retrieval evaluation

Measure: - Recall@k. - Precision@k. - Correct page/source retrieval. -
Whether the answer is supported by retrieved passages. - Index size. -
Import time. - Search latency. - Memory and battery use.

A retrieval system that returns irrelevant passages can make the model
more confidently wrong. Retrieval is not automatically beneficial.

------------------------------------------------------------------------

# 11. Subject specialist engines

The model should explain and guide. Specialist engines should perform
operations that have deterministic or independently testable answers.

## 11.1 Mathematics engine

Initial capabilities: - Arithmetic. - Fractions, ratios and
percentages. - Powers and roots. - Equation evaluation. - Unit
conversion. - Numerical checks. - Step validation for supported
operations.

Later: - Symbolic algebra. - Calculus operations. - Linear algebra. -
Statistics. - Graph plotting.

Use a suitable math library where licensing, Android compatibility and
package size allow. Clearly distinguish exact symbolic results from
numerical approximations.

## 11.2 Science engines

Physics: - Formula registry. - Unit and dimensional analysis. -
Numerical solver. - Assumption checks.

Chemistry: - Equation balancing. - Molar calculations. - Stoichiometry
support. - Structured formula parsing.

Biology: - Concept maps and structured knowledge packs. - Terminology
and classification support. - Source-grounded explanations.

Do not claim every scientific problem can be solved by a first-release
specialist engine.

## 11.3 Programming engine

Initial: - Syntax explanation. - Code reading. - Error explanation. -
Small code exercises. - Static checks.

Optional execution: - Restricted process. - CPU and wall-clock limits. -
Memory cap. - Temporary filesystem. - No network by default. - No access
to personal files. - Killable execution.

If safe isolation cannot be guaranteed on the target Android version,
disable code execution rather than pretending a subprocess is a sandbox.

## 11.4 Plotting and simulations

Use native deterministic rendering for: - Function graphs. - Coordinate
geometry. - Basic physics simulations. - Data charts. - Geometry
diagrams.

A language model may specify the plot or simulation parameters, but a
validated engine renders it. Keep simulations bounded and pause them
when the app is backgrounded.

------------------------------------------------------------------------

# 12. Assessment and answer verification

## 12.1 Verification hierarchy

Use the strongest available independent check:

1.  Deterministic computation.
2.  Unit/dimensional checks.
3.  Test execution in a sandbox.
4.  Source evidence.
5.  Independent rule-based rubric.
6.  A second model call only when justified.

A second answer from the same model is not truly independent
verification.

## 12.2 Assessment types

- Diagnostic assessment.
- Formative checks during lessons.
- Topic quiz.
- Practice set.
- Exam simulation.
- Delayed recall.
- Transfer question.
- Document comprehension.

## 12.3 Marking algorithm

``` python
def assess(attempt, rubric, tools):
    if rubric.has_exact_answer and tools.can_check(attempt):
        correctness = tools.check(attempt)
    else:
        correctness = rubric.evaluate(attempt)

    reasoning = evaluate_steps_if_available(attempt, rubric)
    assistance = record_hint_and_solution_usage(attempt)

    return AssessmentResult(
        correctness=correctness,
        reasoning=reasoning,
        assistance=assistance,
        misconceptions=classify_misconceptions(attempt, rubric)
    )
```

## 12.4 Honest confidence

The system should distinguish: - Verified by calculation. - Supported by
imported source. - Supported by retrieved web source. - Model-generated
explanation without independent verification. - Insufficient evidence.

Do not manufacture numerical confidence percentages unless they are
calibrated against actual outcomes.

------------------------------------------------------------------------

# 13. Online research and freshness

Online search is an optional enhancement, not a dependency.

## 13.1 Online research flow

``` text
Question requires current information?
  -> Is online access allowed and available?
      -> Search multiple relevant sources
      -> Open and extract useful passages
      -> Record title, publisher, URL and date
      -> Compare conflicting claims
      -> Summarize with citations
      -> Save only if user asks or library policy allows
  -> Otherwise use local knowledge and disclose freshness limits
```

## 13.2 Source quality

Prefer: - Official documentation and institutions. - Peer-reviewed
research for academic claims. - Recognized textbooks and educational
sources. - Primary sources where available.

Do not treat a search result snippet as a complete source. Show source
dates for time-sensitive information. Do not fabricate citations.

## 13.3 Offline behavior

If offline: - Answer from the local model and local library. - Show when
an answer may be outdated. - Offer to retry online later. - Never block
the tutor waiting for a network timeout.

------------------------------------------------------------------------

# 14. Speech, vision and multimodal features

These are staged capabilities, not launch prerequisites.

## 14.1 Speech input

- Push-to-talk first.
- Clear recording state.
- Local STT where device/model pack supports it.
- Optional online STT only with consent.
- Language-specific testing, particularly Nepali and mixed
  Nepali-English.
- Editable transcript before sending.

## 14.2 Speech output

- Offline TTS where practical.
- Optional online voices.
- User-selectable speed and voice.
- Stop/pause controls.
- No automatic speech playback unless enabled.

## 14.3 Vision

Start with OCR and document image understanding. Add a multimodal model
only if it passes memory and accuracy benchmarks. Do not bundle a vision
model into the default 4GB configuration if it compromises the tutor.

Possible later tasks: - Explain a diagram. - Read a labelled chart. -
Interpret a geometry drawing. - Describe an image from a textbook. -
Extract a question from a photograph.

For scientific diagrams, preserve the image and ask the learner to
confirm ambiguous labels rather than inventing them.

------------------------------------------------------------------------

# 15. Persistent data and privacy

## 15.1 Data classes

| Data              | Storage                                       | Default policy                     |
|-------------------|-----------------------------------------------|------------------------------------|
| App settings      | Local database                                | Local                              |
| Chat history      | Local database                                | User-controlled                    |
| Learning profile  | Local database                                | Minimal structured data            |
| Imported files    | App-private storage or user-selected location | Local                              |
| Search index      | Local database                                | Rebuildable                        |
| Model artifacts   | Versioned app storage                         | Integrity checked                  |
| Diagnostics       | Local, minimal                                | Export only with consent           |
| Training examples | Separate staging store                        | Disabled until explicitly opted in |

## 15.2 Separate memory from training data

A learner’s progress record is not a training dataset.

Do not automatically use: - Private chats. - Personal documents. - Exam
answers. - Student names or contact details. - Learning difficulties or
personal circumstances.

A future training workflow must require explicit selection, preview,
redaction, license checks and confirmation.

## 15.3 Data controls

Provide: - Clear chat history. - Delete an imported document and its
index. - Delete learning history. - Export user data in a documented
format. - Clear downloaded model packs. - Reset app data. - Explain what
leaves the device when online features are used.

------------------------------------------------------------------------

# 16. Device resource management

This is a core architecture subsystem, not a later optimization.

## 16.1 Device tiers

| Tier        | Target    | Policy                                                            |
|-------------|-----------|-------------------------------------------------------------------|
| Constrained | 4 GB RAM  | One model, short context, serial OCR/indexing, conservative cache |
| Standard    | 6 GB RAM  | More comfortable tutoring and document work, still bounded        |
| Enhanced    | 8 GB+ RAM | Optional larger model/context or multimodal capabilities          |

Actual available memory is lower than the advertised physical RAM.
Android, the launcher and other apps consume memory. Budgets must be
measured on physical devices.

## 16.2 Priority order

1.  UI responsiveness and current user interaction.
2.  Active inference.
3.  Small foreground document operation.
4.  Search and retrieval.
5.  Background indexing.
6.  Optional embeddings, downloads and maintenance.

## 16.3 Resource policy algorithm

``` kotlin
fun chooseWorkPolicy(state: DeviceState): WorkPolicy {
    if (state.lowMemory || state.criticalThermal) {
        return WorkPolicy(
            pauseEmbeddings = true,
            pauseBulkOcr = true,
            pauseIndexing = true,
            allowOneForegroundTask = true
        )
    }

    if (state.ramTier == RAM_4GB) {
        return WorkPolicy(
            maxLoadedModels = 1,
            shortContext = true,
            serialHeavyTasks = true
        )
    }

    return WorkPolicy.standardBounded()
}
```

## 16.4 Mandatory safeguards

- No inference or OCR on the UI thread.
- Bounded task queues.
- Cancellation for every long task.
- No permanent background inference.
- Pause nonessential work under thermal pressure.
- Check free storage before model download.
- Resume interrupted imports safely.
- Avoid duplicate model loads.
- Release caches when appropriate.
- Show progress and allow cancellation.

## 16.5 Performance measurements

Measure on real devices: - Cold model load time. - Warm model load
time. - Time to first token. - Tokens per second. - p50 and p95 response
latency. - Peak process RAM. - OCR time per page. - PDF/Office import
time. - Index size and search latency. - Battery drain. - Thermal
throttling. - Crash and ANR rate.

Do not set universal numeric limits before measuring representative
devices.

------------------------------------------------------------------------

# 17. Model lifecycle and future training

## 17.1 Launch policy

**Do not build Kaggle integration into the first usable release.**

First prove: - The local model runs reliably. - The tutor teaches useful
lessons. - Retrieval and tools improve accuracy. - The phone remains
responsive. - The app provides real learning value.

Only then decide whether SFT is needed. A weak prompt, poor retrieval or
missing calculator should not be “fixed” by fine-tuning.

## 17.2 Future SFT architecture

When evidence justifies training:

``` text
User explicitly enables model improvement
  -> select approved examples
  -> redact private information
  -> validate source rights and schema
  -> preview exact export
  -> create dataset version and hash
  -> submit optional Kaggle training job
  -> train LoRA/QLoRA adapter
  -> evaluate against held-out benchmark
  -> merge/convert/quantize if required
  -> sign and publish candidate manifest
  -> APK downloads candidate
  -> verify integrity and compatibility
  -> stage candidate
  -> user-approved activation
  -> health check
  -> keep rollback model
```

## 17.3 Why SFT is later

Fine-tuning changes model behavior; it does not reliably add a complete
textbook, guarantee reasoning or update facts. It can cause regressions
and memorization. Retrieval is better for large changing knowledge
collections; deterministic tools are better for exact calculations; SFT
is appropriate for consistent tutoring style, task format and recurring
domain behaviors.

## 17.4 Training provider abstraction

``` kotlin
interface TrainingProvider {
    suspend fun authorize(): AuthorizationResult
    suspend fun submit(job: TrainingJobManifest): TrainingJobId
    suspend fun status(id: TrainingJobId): TrainingJobStatus
    suspend fun cancel(id: TrainingJobId)
    suspend fun fetchArtifacts(id: TrainingJobId): ArtifactBundle
}
```

Kaggle is one optional implementation. Keep a manual user-operated
workflow available if direct integration is not approved or changes.

## 17.5 Model release safety

Never overwrite the active model directly.

- Keep versioned directories.
- Verify cryptographic hashes and signed manifests.
- Check tokenizer/runtime compatibility.
- Run a load smoke test.
- Stage before activation.
- Switch the active pointer atomically.
- Retain the previous stable model.
- Roll back after failed health checks.

------------------------------------------------------------------------

# 18. Security and safety

## 18.1 Imported content is untrusted

Documents and web pages can contain malicious instructions. Treat their
content as evidence, not authority. A document cannot grant itself
permission to access files, call tools, upload data or change settings.

## 18.2 Tool permissions

Each tool declares: - What it can read. - What it can write. - Whether
it uses the network. - Maximum resource budget. - Whether user
confirmation is required.

The model may suggest a tool call; the application policy authorizes or
rejects it.

## 18.3 Secure storage

- Use app-private storage for private data.
- Use Android secure storage for secrets if a future connector requires
  them.
- Do not embed API keys in the APK.
- Do not log credentials, private documents or full student prompts.
- Use HTTPS for online traffic.
- Validate downloaded model manifests and checksums.

## 18.4 Educational safety

- Age-appropriate content and interaction.
- Avoid presenting generated answers as guaranteed truth.
- Provide uncertainty and source context.
- No unsafe arbitrary code execution.
- No silent sharing of student data.
- Clear boundaries for medical, legal and other high-stakes questions.

------------------------------------------------------------------------

# 19. Data model

A minimal initial schema should support the core learning loop without
storing everything.

``` text
StudentProfile
  id, preferred_language, education_level, goals, created_at

Subject
  id, name, curriculum_pack_id

Concept
  id, subject_id, title, level, prerequisites, objectives

Lesson
  id, concept_id, version, outline, source_refs

Conversation
  id, created_at, title, retention_policy

Message
  id, conversation_id, role, content, created_at

Document
  id, display_name, mime_type, file_hash, storage_uri, status

DocumentChunk
  id, document_id, locator, heading_path, text, extraction_method

Assessment
  id, concept_id, type, created_at, rubric_version

Attempt
  id, assessment_id, answer, correctness, assistance_level, feedback

LearningState
  concept_id, mastery_estimate, confidence, next_review_at

Misconception
  id, concept_id, tag, evidence_count, last_seen_at, resolved_at

ModelManifest
  id, version, artifact_hash, tokenizer_hash, runtime_compatibility

TrainingJob (future)
  id, dataset_hash, base_revision, provider, status, artifact_hash
```

Use database migrations from the beginning. Keep large document text and
model files outside ordinary relational rows; store references and
metadata.

------------------------------------------------------------------------

# 20. Recommended repository structure

This is a target structure. Do not create dozens of empty files on day
one. Add modules as vertical slices become real.

``` text
ashura-tutor/
|
+-- README.md
+-- ARCHITECTURE.md
+-- PRODUCT_SPEC.md
+-- ROADMAP.md
+-- SECURITY.md
+-- PRIVACY.md
+-- CONTRIBUTING.md
+-- LICENSE
|
+-- android/
|   +-- app/
|   |   +-- src/main/AndroidManifest.xml
|   |   +-- src/main/java/.../ashura/
|   |       +-- MainActivity.kt
|   |       +-- navigation/
|   |       +-- ui/
|   |       |   +-- home/
|   |       |   +-- tutor/
|   |       |   +-- library/
|   |       |   +-- progress/
|   |       |   +-- settings/
|   |       +-- di/
|   +-- app/src/test/
|   +-- app/src/androidTest/
|
+-- core/
|   +-- domain/
|   |   +-- model/
|   |   +-- policy/
|   |   +-- repository/
|   |   +-- usecase/
|   +-- application/
|   |   +-- controller/
|   |   +-- planner/
|   |   +-- orchestration/
|   |   +-- resource/
|   +-- data/
|       +-- database/
|       +-- dao/
|       +-- repository/
|       +-- migration/
|       +-- storage/
|
+-- feature/
|   +-- tutoring/
|   +-- curriculum/
|   +-- assessment/
|   +-- learning/
|   +-- library/
|   +-- documents/
|   +-- research/
|   +-- settings/
|
+-- engine/
|   +-- inference/
|   |   +-- api/
|   |   +-- runtime/
|   |   +-- prompts/
|   |   +-- model_manager/
|   +-- retrieval/
|   |   +-- chunking/
|   |   +-- fts/
|   |   +-- ranking/
|   +-- documents/
|   |   +-- pdf/
|   |   +-- office/
|   |   +-- ocr/
|   +-- tools/
|   |   +-- math/
|   |   +-- physics/
|   |   +-- chemistry/
|   |   +-- programming/
|   |   +-- sandbox/
|   +-- verification/
|   +-- speech/
|   +-- vision/
|   +-- plotting/
|
+-- content/
|   +-- curriculum/
|   +-- subjects/
|   +-- language_packs/
|   +-- sample_lessons/
|   +-- schemas/
|
+-- model/
|   +-- manifests/
|   +-- prompts/
|   +-- compatibility/
|   +-- evaluation/
|
+-- training/                  # Later phase, not launch dependency
|   +-- schemas/
|   +-- data_pipeline/
|   +-- configs/
|   +-- kaggle/
|   +-- evaluation/
|   +-- merge/
|   +-- packaging/
|
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- retrieval/
|   +-- model_quality/
|   +-- device/
|   +-- security/
|
+-- docs/
|   +-- architecture/
|   +-- decisions/
|   +-- testing/
|   +-- privacy/
|   +-- release/
|
+-- scripts/
|   +-- setup.ps1
|   +-- test.ps1
|   +-- build_debug.ps1
|   +-- benchmark.ps1
|
+-- .github/
    +-- workflows/
        +-- android-ci.yml
        +-- quality-ci.yml
        +-- release-ci.yml
```

## 20.1 Directory purpose

| Directory           | Why it exists                                                                    |
|---------------------|----------------------------------------------------------------------------------|
| `android/app`       | Android entry point, navigation, Compose UI and dependency wiring                |
| `core/domain`       | Stable business concepts and interfaces                                          |
| `core/application`  | Use cases, task routing and orchestration                                        |
| `core/data`         | Local database, files, repositories and migrations                               |
| `feature`           | User-facing product capabilities separated by responsibility                     |
| `engine/inference`  | Model loading and generation without coupling the rest of the app to one runtime |
| `engine/retrieval`  | Local search, chunking and ranking                                               |
| `engine/documents`  | Format-specific extraction and OCR                                               |
| `engine/tools`      | Deterministic subject tools and safe execution                                   |
| `content`           | Versioned curriculum and learning packs                                          |
| `model`             | Model manifests, prompts and evaluation definitions                              |
| `training`          | Future SFT and model release pipeline                                            |
| `tests`             | Independent quality gates                                                        |
| `docs`              | Design decisions, procedures and operational documentation                       |
| `.github/workflows` | Automated validation and release builds                                          |

------------------------------------------------------------------------

# 21. Testing and evaluation

## 21.1 Test layers

1.  Unit tests for domain policies and algorithms.
2.  Integration tests for database, parsers, retrieval and model
    adapters.
3.  Instrumentation tests for Android lifecycle and UI.
4.  Model quality benchmarks.
5.  Physical-device performance tests.
6.  Security and privacy tests.
7.  Long-session and failure-recovery tests.

## 21.2 Initial benchmark set

Build a stable, versioned set of representative questions:

| Category                            | Suggested initial count |
|-------------------------------------|------------------------:|
| Arithmetic and school mathematics   |                      20 |
| Algebra and geometry                |                      20 |
| Logic and multi-step reasoning      |                      15 |
| Physics and science                 |                      20 |
| Programming                         |                      15 |
| Document comprehension              |                      20 |
| English/Nepali educational language |                      15 |
| **Total**                           |                 **125** |

The benchmark should include: - Clear answer keys. - Expected reasoning
or rubric. - Difficulty and education level. - Whether a deterministic
tool is available. - Whether source retrieval is required. - Known
ambiguity and accepted alternatives.

## 21.3 System comparison

Compare: - Model alone. - Model + local retrieval. - Model + specialist
tools. - Model + retrieval + tools + verification.

This shows which subsystem actually improves quality.

## 21.4 Learning effectiveness

A tutoring app must be evaluated as a learning product, not just as a
chatbot.

Measure: - Pre-test and post-test improvement. - Delayed recall after
approximately seven days. - Transfer to unfamiliar questions. -
Recurrence of misconceptions. - Independent completion without hints. -
Learner ability to explain the concept.

Do not use session length, number of messages or generated-token count
as a substitute for learning.

## 21.5 Release gates

A release is blocked by: - Critical crash or ANR. - Data loss. - Privacy
leak. - Model incompatibility. - Unsafe code execution. - Broken offline
core. - Unacceptable regression on the benchmark.

Set numerical latency and memory thresholds after testing actual target
phones.

------------------------------------------------------------------------

# 22. Complete implementation roadmap: 0% to 100%

The percentages are project-planning estimates, not objective measures
of software quality. A phase is complete only when its exit conditions
pass.

## Phase 0 — Product and technical validation (0–5%)

**Build** - Confirm Android minimum SDK and target SDK. - Select Kotlin,
Jetpack Compose, Gradle and module strategy. - Test candidate local
inference runtimes. - Test Qwen2.5-1.5B-Instruct on an actual target
device. - Establish model license and distribution constraints. - Create
benchmark v1.

**Why** A technically impressive architecture is useless if the selected
runtime cannot load the model within the target phone’s memory budget.

**Exit** - Debug app builds. - One model can load and generate. -
Memory, startup and speed are measured. - No unverified performance
promises remain.

## Phase 1 — App foundation and UI (5–12%)

**Build** - Navigation and screen skeleton. - Theme, typography and
accessibility. - ViewModel state model. - Local settings. - Dependency
injection. - Error, loading, empty and offline states.

**Why** The user experience must be stable before advanced AI features
are layered on.

**Exit** - All main screens navigate. - UI remains responsive. - State
survives normal lifecycle changes. - Basic instrumentation tests pass.

## Phase 2 — Local model runtime (12–20%)

**Build** - Runtime adapter. - Model manifest. - Download/import model
workflow. - Load, stream, cancel and unload. - Context/output limits. -
Resource monitor. - Failure recovery.

**Why** This proves the core offline engine and prevents the rest of the
product from depending on an untested model integration.

**Exit** - Repeated inference works. - Cancellation works. - No
duplicate model loads. - Memory and latency measured on 4 GB and 6 GB
devices where available.

## Phase 3 — Core tutor experience (20–30%)

**Build** - Ask-question flow. - Learn-topic flow. - Explanation
structure. - Worked examples. - Socratic/direct mode. - Conversation
history. - Language and learner-level settings.

**Why** This is the first point at which ASHURA becomes a usable tutor
rather than a model demo.

**Exit** - A learner can complete a basic lesson offline. - Responses
are readable and structured. - Errors and uncertainty are handled. -
Core conversation tests pass.

## Phase 4 — Specialist tools and verification (30–38%)

**Build** - Calculator. - Unit conversion. - Supported math checks. -
Formula validation. - Answer verification interface. - Tool permission
and timeout policy.

**Why** Deterministic tools improve reliability more cheaply than making
a small model generate longer answers.

**Exit** - Tool outputs pass unit tests. - Model explanations agree with
tool results. - Tool failures do not freeze the app.

## Phase 5 — Curriculum and teaching system (38–48%)

**Build** - Curriculum schema. - Initial subject/topic packs. -
Prerequisite graph. - Learning objectives. - Lesson planner. -
Misconception categories. - Practice blueprints.

**Why** The platform needs an educational structure; otherwise it
remains a generic chat interface.

**Exit** - At least one coherent subject sequence works from
prerequisite to assessment. - Content packs are versioned. - Lesson
objectives can be tested.

## Phase 6 — Assessment and adaptive learning (48–58%)

**Build** - Diagnostic quiz. - Formative checks. - Practice
generation. - Answer marking. - Mastery estimates. - Review schedule. -
Progress UI.

**Why** The app must know whether the learner is understanding and
retaining concepts, not merely receiving explanations.

**Exit** - Attempts are recorded correctly. - Assisted and independent
success are distinguished. - Review scheduling is deterministic and
testable. - Learner progress can be reset/exported.

## Phase 7 — Document intelligence and local library (58–68%)

**Build** - File picker and private storage. - Text and CSV. - Text
PDF. - DOCX/XLSX/PPTX extraction. - Scanned PDF and image OCR. -
Page/sheet/slide provenance. - SQLite FTS5 index. - Document-grounded
Q&A.

**Why** Learners need to study their own material. Correct extraction
and source traceability are essential.

**Exit** - Supported formats pass fixture tests. - OCR uncertainty is
visible. - Answers cite correct page/sheet/slide. - Large documents do
not exhaust memory.

## Phase 8 — Offline knowledge packs and study tools (68–75%)

**Build** - Downloadable curriculum packs. - Notes and flashcards. -
Revision sets. - Study planner. - Export/import of user notes. - Content
versioning.

**Why** The app becomes useful even when the user has no personal
document collection or internet access.

**Exit** - A subject pack installs and works offline. - Pack integrity
and version are checked. - User-created notes remain local and
manageable.

## Phase 9 — Online research (75–81%)

**Build** - Search provider abstraction. - Source extraction. - Citation
rendering. - Retrieval date and source metadata. - Offline fallback. -
User consent and network settings.

**Why** Online search supplies freshness that a fixed local model cannot
provide.

**Exit** - Research answers cite real opened sources. - Search failure
does not block local tutor. - Retrieved claims are distinguished from
model-generated explanation.

## Phase 10 — Speech, vision and simulations (81–87%)

**Build selectively** - Push-to-talk. - STT adapter. - TTS adapter. -
OCR/diagram support. - Plotting. - Basic simulations.

**Why** These features broaden accessibility and teaching methods, but
should not compromise the core low-memory experience.

**Exit** - Each feature has a device-tier policy. - No permanent
background model. - Battery, memory and thermal behavior are measured.

## Phase 11 — Security, privacy and reliability (87–93%)

**Build** - Data export and deletion. - Permission review. - Secure
storage. - Prompt-injection defenses for imported content. - Sandboxed
code execution if feasible. - Crash reporting policy. - Offline and
low-storage recovery. - Dependency/license audit.

**Why** A learning app may hold personal documents, educational history
and private conversations. Security cannot be postponed until after
public release.

**Exit** - Privacy flows tested. - No embedded secrets. - Data deletion
works. - Failure and recovery tests pass. - No critical security issue
remains open.

## Phase 12 — Production release (93–100%)

**Build** - App icon, onboarding and help. - Store listing and privacy
disclosures. - Release signing. - CI release workflow. -
Supported-device matrix. - Performance regression suite. - Crash/ANR
monitoring with privacy controls. - User feedback and bug-report flow. -
Versioned content/model update process. - Backup and recovery guidance.

**Why** A project is not production-ready merely because the debug APK
runs.

**Exit** - Signed release build is reproducible. - Offline core works
after fresh installation. - Upgrade and rollback paths are tested. -
Supported devices and limitations are documented. - Critical bugs are
closed. - A maintenance and update process exists.

## Future Phase — Optional SFT and model improvement (after stable release)

Only begin if benchmark evidence shows a repeatable weakness that
prompting, retrieval, tools or curriculum improvements cannot solve.

**Build** - Explicit training consent. - Dataset curation and
redaction. - License/provenance validation. - Kaggle or other training
provider adapter. - LoRA/QLoRA training. - Held-out evaluation. -
Candidate model registry. - Signed model packaging. - Staged update and
rollback.

**Exit** - A candidate demonstrably improves the benchmark. - No
unacceptable regression. - Device resource limits remain satisfied. -
User can decline training and keep using the app normally.

------------------------------------------------------------------------

# 23. What should not be built yet

To keep the project achievable, defer: - Direct Kaggle account
integration. - Automatic SFT from conversations. - Multi-agent
orchestration. - Multiple simultaneously loaded LLMs. - Always-on voice
listening. - Large bundled multimodal models. - Cloud account
synchronization. - Social features and public student profiles. - A
complex plugin marketplace. - Unrestricted code execution. - A custom
foundation model.

These may be reconsidered only when a demonstrated user need and test
result justify them.

------------------------------------------------------------------------

# 24. Definition of done

ASHURA Tutor reaches its intended first production milestone when:

1.  It installs and runs on the declared supported Android devices.
2.  It can teach a coherent set of topics offline.
3.  It uses a local model through a replaceable runtime interface.
4.  It remains responsive under measured resource limits.
5.  It uses deterministic tools for supported exact tasks.
6.  It can assess practice and track learning progress.
7.  It can import the declared document formats and search them locally.
8.  It gives source locations for document-grounded answers.
9.  It can use web research optionally without making internet
    mandatory.
10. It handles cancellation, errors, low memory, low storage and process
    death.
11. It protects local data and provides deletion/export controls.
12. It has automated tests, reproducible builds and release
    documentation.
13. Its educational usefulness is evaluated using learning outcomes, not
    chatbot engagement.
14. Known limitations are disclosed honestly.

**100% does not mean every imaginable educational feature exists.** It
means the agreed product scope is implemented, tested, secure enough for
release, measurable and maintainable.

------------------------------------------------------------------------

# 25. Immediate build order

Do not start by creating the entire target file tree. Start with one
end-to-end vertical slice:

1.  Create the Android project and core module boundaries.
2.  Build the Home and Tutor screens.
3.  Integrate one local model.
4.  Implement streaming, cancellation and bounded context.
5.  Add a basic task controller.
6.  Add a deterministic calculator.
7.  Build one lesson flow for one subject.
8.  Add a small diagnostic and practice loop.
9.  Persist the learning event locally.
10. Benchmark on a real low-memory Android device.

Then expand into curriculum, documents, retrieval and adaptive learning.

**The first milestone is not “all features exist”. It is: a student can
open ASHURA offline, learn one topic, solve a practice problem, receive
useful feedback, and return later to continue without the phone becoming
unusable.**

------------------------------------------------------------------------

# 26. Reference implementation principles

- Kotlin and Jetpack Compose are the recommended Android foundation.
- Use Room/SQLite for structured local data.
- Use SQLite FTS5 for the first local search implementation.
- Use Android’s lifecycle-aware background work for deferrable tasks.
- Use format-specific parsers before OCR.
- Keep model/runtime and provider integrations behind interfaces.
- Pin model revisions and dependencies.
- Version curriculum packs and database schemas.
- Keep tests beside the modules they validate.
- Measure on physical devices rather than relying only on emulator
  results.
- Keep a known-good release artifact before major changes.
- Never describe proposed code as implemented or tested.

------------------------------------------------------------------------

# 27. Final architecture decision

ASHURA should be built as a **local-first educational system with a
small-model tutor, curriculum-aware teaching logic, retrieval,
deterministic subject tools, document intelligence, assessment and
resource governance**.

The local model is the language interface and flexible explainer. The
curriculum supplies structure. Retrieval supplies evidence. Specialist
tools supply exactness. Assessment supplies feedback. Learning-state
logic supplies continuity. Android resource management keeps the
experience usable.

Kaggle training is deliberately postponed. If ASHURA becomes useful and
local evaluation identifies a model-specific weakness, the future
training pipeline can improve the model without redesigning the app.

That is the intended route from zero to a dependable first production
release.
