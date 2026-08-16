"""Turn an attributable English Wikipedia revision into research-ready evidence.

This adapter never turns narrative prose into canonical facts.  It splits a
stored revision into locatable passages, then stores explicitly curated answers
as *review-required* records which point to those passages.  The same evidence
layer can later be embedded; vector similarity remains a candidate generator,
never evidence by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalEntity,
    NarrativePassage,
    ResearchAnswer,
    ResearchAnswerEvidence,
    SourceAssertion,
    SourceSnapshot,
    RawIngestionRun,
    RawIngestionRunSnapshot,
)


EXTRACTION_VERSION = "enwiki-section-passages-v1"
ANSWER_VERSION = "deep-research-pilot-v1"
HEADING = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", re.MULTILINE)
REF_MARKER = re.compile(r"<ref(?:\s+name\s*=\s*[\"']?([^\s/>\"']+)[\"']?)?[^>]*?(?:/>|>.*?</ref>)", re.IGNORECASE | re.DOTALL)
SECTION_SLUG = re.compile(r"[^a-z0-9]+")
SKIP_TOP_LEVEL = {"notes", "references", "external links", "see also", "bibliography", "works cited"}


def section_slug(value: str) -> str:
    return SECTION_SLUG.sub("-", value.lower()).strip("-") or "section"


def clean_wikitext(value: str) -> str:
    """Produce readable, attributable passage text while retaining ref markers.

    This is intentionally conservative: raw wikitext remains in the immutable
    snapshot, and we only remove presentation markup from the derived passage.
    """
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    # Template nesting is uncommon in prose but can be shallowly stripped here;
    # the exact template data remains in the snapshot for future parser updates.
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", value)
    value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", value)
    value = re.sub(r"'{2,5}", "", value)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def split_sections(wikitext: str) -> list[dict[str, object]]:
    """Split wikitext into a lead and hierarchical non-reference sections."""
    matches = list(HEADING.finditer(wikitext))
    sections: list[dict[str, object]] = []
    lead = wikitext[: matches[0].start()] if matches else wikitext
    if clean_wikitext(lead):
        sections.append({"locator": "lead", "title": "Lead", "content": lead})

    hierarchy: dict[int, list[str]] = {}
    for index, heading in enumerate(matches):
        level = len(heading.group(1))
        title = re.sub(r"\s+", " ", heading.group(2)).strip()
        hierarchy[level] = hierarchy.get(level - 1, []) + [title]
        for deeper_level in list(hierarchy):
            if deeper_level > level:
                del hierarchy[deeper_level]
        parent_levels = [key for key in hierarchy if key < level]
        parent = hierarchy[max(parent_levels)] if parent_levels else []
        path = parent + [title]
        start = heading.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(wikitext)
        top_level = path[0].strip().lower()
        content = wikitext[start:end]
        if top_level not in SKIP_TOP_LEVEL and clean_wikitext(content):
            sections.append({
                "locator": "/".join(section_slug(part) for part in path),
                "title": " / ".join(path),
                "content": content,
            })
    return sections


def chunk_section(content: str, *, limit: int = 1500) -> Iterable[str]:
    """Chunk only at paragraph boundaries so each chunk retains its meaning."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if clean_wikitext(part)]
    buffer = ""
    for paragraph in paragraphs:
        if buffer and len(clean_wikitext(buffer)) + len(clean_wikitext(paragraph)) > limit:
            yield buffer
            buffer = paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}".strip()
    if buffer:
        yield buffer


def citation_markers(raw_content: str) -> list[str]:
    markers = [marker or "inline" for marker in REF_MARKER.findall(raw_content)]
    return list(dict.fromkeys(markers))


def _snapshot_payload(snapshot: SourceSnapshot) -> dict:
    if not snapshot.storage_uri:
        raise ValueError("The source snapshot has no retained payload URI.")
    path = Path(urlparse(snapshot.storage_uri).path)
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_for_qid(db: Session, qid: str) -> SourceSnapshot:
    snapshot = db.scalar(
        select(SourceSnapshot)
        .join(SourceAssertion, SourceAssertion.source_snapshot_id == SourceSnapshot.id)
        .where(
            SourceAssertion.source_property == "wikidata_item",
            SourceAssertion.raw_value["wikidata_id"].as_string() == qid,
        )
        .order_by(SourceSnapshot.retrieved_at.desc())
    )
    if not snapshot:
        raise ValueError(f"No retained English Wikipedia snapshot is resolved to {qid}.")
    return snapshot


def _entity_for_snapshot(db: Session, qid: str, payload: dict) -> CanonicalEntity:
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid))
    if entity:
        return entity
    entity = CanonicalEntity(
        entity_kind="film",
        canonical_label=str(payload["page"].get("title") or qid),
        wikidata_id=qid,
    )
    db.add(entity)
    db.flush()
    return entity


def extract_passages(db: Session, qid: str) -> dict[str, object]:
    """Persist all non-reference English Wikipedia sections for one film QID."""
    snapshot = _snapshot_for_qid(db, qid)
    if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
        raise ValueError("Narrative extraction requires an attributable CC BY-SA Wikipedia snapshot.")
    payload = _snapshot_payload(snapshot)
    wikitext = payload["page"]["revisions"][0]["slots"]["main"]["content"]
    entity = _entity_for_snapshot(db, qid, payload)
    existing_passages = {
        (item.section_locator, item.ordinal, item.content_hash): item
        for item in db.scalars(select(NarrativePassage).where(
            NarrativePassage.source_snapshot_id == snapshot.id,
        ))
    }
    to_store: list[NarrativePassage] = []
    by_locator: dict[str, list[NarrativePassage]] = {}
    for section in split_sections(wikitext):
        locator = str(section["locator"])
        title = str(section["title"])
        for ordinal, raw_chunk in enumerate(chunk_section(str(section["content"]))):
            content = clean_wikitext(raw_chunk)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            key = (locator, ordinal, digest)
            existing = existing_passages.get(key)
            if not existing:
                existing = NarrativePassage(
                    subject_entity_id=entity.id,
                    source_snapshot_id=snapshot.id,
                    section_locator=locator,
                    section_title=title,
                    ordinal=ordinal,
                    content=content,
                    content_hash=digest,
                    citation_markers=citation_markers(raw_chunk),
                    extraction_version=EXTRACTION_VERSION,
                )
                to_store.append(existing)
                existing_passages[key] = existing
            by_locator.setdefault(locator, []).append(existing)
    if to_store:
        db.add_all(to_store)
        db.flush()
    db.commit()
    return {"qid": qid, "entity_id": str(entity.id), "source_revision": snapshot.source_revision, "passages_created": len(to_store), "passages": by_locator}


def selected_qids_from_ingestion_manifests(db: Session, manifest_uris: list[str]) -> list[str]:
    """Return exactly the QIDs represented by completed vetted source runs.

    The function deliberately follows run-to-snapshot links. It does not infer
    membership from title search or from every Wikipedia page in the database.
    """
    runs = list(db.scalars(select(RawIngestionRun).where(
        RawIngestionRun.adapter_name == "wikipedia_api_revision_snapshot",
        RawIngestionRun.status == "complete",
        RawIngestionRun.manifest_uri.in_(manifest_uris),
    )))
    if not runs:
        raise ValueError("No completed Wikipedia ingestion runs match the supplied manifests.")
    snapshot_ids = list(db.scalars(select(RawIngestionRunSnapshot.source_snapshot_id).where(
        RawIngestionRunSnapshot.ingestion_run_id.in_([run.id for run in runs]),
    )))
    qids = list(db.scalars(select(SourceAssertion.raw_value["wikidata_id"].as_string()).where(
        SourceAssertion.source_snapshot_id.in_(snapshot_ids),
        SourceAssertion.source_property == "wikidata_item",
    )))
    return sorted({qid for qid in qids if qid})


DEEP_RESEARCH_PILOTS: dict[str, list[dict[str, object]]] = {
    "Q163872": [
        {
            "question_id": "story.civic-pressure-system",
            "question_text": "What civic pressure system drives the story?",
            "answer": "Batman, Gordon and Harvey Dent try to dismantle Gotham's organised crime, but the Joker escalates that campaign into tests of law, public trust and personal moral limits. Dent is positioned as the lawful public alternative to Batman.",
            "evidence_class": "narrative_extraction",
            "locators": ["plot", "production/writing"],
        },
        {
            "question_id": "story.choice-architecture",
            "question_text": "How does the film create escalating choice pressure?",
            "answer": "The antagonist repeatedly converts a forced choice into the next source of pressure: identity exposure, the separated Rachel and Dent rescue, and the ferry dilemma. The ending has Batman assume blame for Dent's crimes to preserve Dent as a civic symbol; analysis of that act remains attributed rather than treated as an objective moral verdict.",
            "evidence_class": "narrative_extraction",
            "locators": ["plot", "themes-and-analysis/morality-and-ethics"],
        },
        {
            "question_id": "creative.genre-frame",
            "question_text": "What creative frame distinguishes this comic adaptation?",
            "answer": "The writing account describes an intent to retain Batman Begins' grounded world while drawing on crime drama. Dent was developed as a central dramatic figure, and the Joker was intentionally denied a definitive origin story to preserve uncertainty.",
            "evidence_class": "source_fact",
            "locators": ["production/writing", "production/casting"],
        },
        {
            "question_id": "craft.image-and-spectacle",
            "question_text": "What production choices shape the film's spectacle?",
            "answer": "The production used high-resolution IMAX cameras for substantial sequences and preferred practical stunts and effects when they could achieve the shot. Its Chicago locations were selected to support the urban-crime frame, while the score assigns differentiated approaches to Batman, Dent and Joker.",
            "evidence_class": "source_fact",
            "locators": ["production/pre-production", "production/special-effects-and-design", "production/music"],
        },
        {
            "question_id": "career.ledger-award-chain",
            "question_text": "What is the evidence-backed career landmark around Heath Ledger's performance?",
            "answer": "Ledger played the Joker, died before the film's release, and received posthumous major acting recognition including the Academy Award for Best Supporting Actor. Critical and retrospective claims about the performance's standing must remain attributed to their named publications or awards bodies.",
            "evidence_class": "source_fact",
            "locators": ["production/post-production", "reception/accolades", "reception/critical-response"],
        },
        {
            "question_id": "impact.industry-and-culture",
            "question_text": "What cultural and industry impact is supportable without exaggeration?",
            "answer": "The article documents an interactive viral campaign, record-setting commercial performance and National Film Registry selection in 2020. It also records competing interpretations of the film as a modern-superhero blueprint: later commentary credits its influence but warns that imitators often copied darkness rather than its underlying construction.",
            "evidence_class": "attributed_interpretation",
            "locators": ["release/marketing-and-anti-piracy", "release/box-office", "legacy/cultural-influence"],
        },
        {
            "question_id": "theme.parallel-readings",
            "question_text": "Which thematic readings should be held in parallel?",
            "answer": "The page assembles distinct, attributed readings around escalation and terrorism, emergency surveillance and civil liberties, morality under coercion, and Harvey Dent as a civic symbol. These readings can be compared or retrieved, but should not be collapsed into one unqualified theme label.",
            "evidence_class": "attributed_interpretation",
            "locators": ["themes-and-analysis/terrorism-and-escalation", "themes-and-analysis/morality-and-ethics"],
        },
        {
            "question_id": "lineage.direct-trilogy-route",
            "question_text": "What direct story lineage is already proved?",
            "answer": "The film is the sequel to Batman Begins and the second installment of The Dark Knight trilogy; The Dark Knight Rises is its stated sequel. Those direct routes are factual lineage. Any comparison with other superhero films requires a declared lens and separate evidence.",
            "evidence_class": "source_fact",
            "locators": ["lead", "sequel"],
        },
    ],
}

# These are deliberately small editorial pilots, not machine-generated labels.
# Each answer was written against the retained article sections listed below and
# stays in review_required until a human editor accepts it.
DEEP_RESEARCH_PILOTS.update({
    "Q166262": [
        {"question_id": "story.origin-through-fear", "question_text": "What story engine establishes this Batman?", "answer": "Bruce Wayne's childhood fear and his parents' murder drive a journey from revenge toward a self-imposed symbol of justice. The League of Shadows offers fear and lethal punishment; Bruce rejects that solution and turns the fear of bats into Batman's public strategy.", "evidence_class": "narrative_extraction", "locators": ["plot", "themes"]},
        {"question_id": "creative.grounded-reinvention", "question_text": "What did the creators set out to reinvent?", "answer": "Nolan and David S. Goyer framed the film as a grounded, contemporary origin story designed to make both Bruce Wayne and Batman dramatically legible. The account contrasts this approach with a franchise driven chiefly by style.", "evidence_class": "source_fact", "locators": ["production/development"]},
        {"question_id": "impact.reboot-template", "question_text": "What influence is supportable from the source?", "answer": "Later commentary cited the film as a model for darker, character-grounded reboots and renewed attention to superhero origin stories. That is an attributed account of influence, not proof that every later reboot descends from it.", "evidence_class": "attributed_interpretation", "locators": ["impact", "reception/critical-response"]},
        {"question_id": "lineage.dark-knight-route", "question_text": "What direct route connects this to The Dark Knight?", "answer": "Batman Begins establishes the grounded Batman world and key relationships that The Dark Knight explicitly continues. This is a direct trilogy relation; escalation comparisons belong to an evidence-linked comparison, not a genre shortcut.", "evidence_class": "source_fact", "locators": ["lead", "production/development"]},
    ],
    "Q189330": [
        {"question_id": "story.return-and-consequence", "question_text": "What pressure brings Batman back in the trilogy finale?", "answer": "Eight years after Harvey Dent's death and Batman's disappearance, Bane exploits Gotham's hidden compromises and Bruce's isolation. The plot turns the earlier noble lie into the final film's civic and personal pressure point.", "evidence_class": "narrative_extraction", "locators": ["plot"]},
        {"question_id": "creative.trilogy-closure", "question_text": "How was the final installment approached?", "answer": "The development account records earlier sequel treatments, the change in plans after Ledger's death, and Nolan's reluctance to make a third film without a story that justified it. The resulting project was built as a conclusion, not an open-ended continuation.", "evidence_class": "source_fact", "locators": ["production/development", "proposed-sequel"]},
        {"question_id": "reading.political-disagreement", "question_text": "What reading should not be flattened into a theme label?", "answer": "The reception analysis preserves conflicting political readings of the film, including Occupy-related critiques and counterarguments; Nolan denied intending the trilogy as political commentary. The record should show this disagreement rather than declare one political meaning.", "evidence_class": "attributed_interpretation", "locators": ["reception/analysis"]},
        {"question_id": "lineage.dark-knight-conclusion", "question_text": "What direct lineage does the film complete?", "answer": "The source presents this film as the conclusion of Nolan's Batman trilogy, following Batman Begins and The Dark Knight. That route is factual; whether it resolves the trilogy better than another finale is a review question.", "evidence_class": "source_fact", "locators": ["lead", "proposed-sequel"]},
    ],
    "Q83495": [
        {"question_id": "story.reality-choice", "question_text": "What choice architecture drives The Matrix?", "answer": "Neo's investigation becomes a choice between remaining inside a designed reality and learning the truth about a machine-controlled world. The red/blue-pill decision then opens a conflict in which knowledge, agency and control are repeatedly tested.", "evidence_class": "narrative_extraction", "locators": ["plot"]},
        {"question_id": "craft.bullet-time-system", "question_text": "What formal innovation is specifically documented?", "answer": "The production account details the camera-array technique popularly known as bullet time, using it to make control over time and space visually legible. The legacy claim must be tied to this technical route, rather than calling the whole film innovative without evidence.", "evidence_class": "source_fact", "locators": ["production/visual-effects"]},
        {"question_id": "theme.many-traditions", "question_text": "How should its thematic material be stored?", "answer": "The article identifies intersecting religious, philosophical, mythological, literary and transgender readings. These are separate interpretive routes and should be retrieved as such, not reduced to a single generic 'AI film' tag.", "evidence_class": "attributed_interpretation", "locators": ["thematic-analysis", "thematic-analysis/philosophy", "thematic-analysis/transgender-themes"]},
        {"question_id": "impact.visual-language", "question_text": "What cultural influence is supported?", "answer": "The legacy account attributes broad influence to the film's slow-motion camera language and visual approach across film and games, including later superhero filmmaking. The cited effect is a precise comparison lens, not a claim of shared story meaning.", "evidence_class": "attributed_interpretation", "locators": ["legacy/filmmaking", "legacy/cultural-impact"]},
    ],
    "Q184843": [
        {"question_id": "story.humanity-through-memory", "question_text": "What narrative question makes Blade Runner comparison-ready?", "answer": "Deckard's work requires him to distinguish people from replicants, while Rachael's implanted memories unsettle that boundary. The story therefore creates a concrete route for comparing artificial-personhood narratives without assuming all AI stories mean the same thing.", "evidence_class": "narrative_extraction", "locators": ["plot"]},
        {"question_id": "creative.adaptation-shift", "question_text": "What adaptation choice shaped the film?", "answer": "The development account records a move away from a script focused on environmental issues toward concerns about humanity and religion, while the source novel remained the direct adaptation route. This is a specific adaptation change, not a blanket claim of fidelity or betrayal.", "evidence_class": "source_fact", "locators": ["production/pre-production-and-script"]},
        {"question_id": "theme.retrofitted-future", "question_text": "Which thematic and visual tensions are documented?", "answer": "The article's analysis links film-noir conventions, genetic engineering, religion and a retrofitted future in which advanced technology sits beside decay. These are attributed analytical readings that should remain distinct from production facts.", "evidence_class": "attributed_interpretation", "locators": ["themes"]},
        {"question_id": "impact.worldbuilding-benchmark", "question_text": "What durable influence does the article support?", "answer": "The legacy account describes the film's design as a benchmark for later science fiction and cinematic world-building, while also recording National Film Registry preservation and a direct sequel. Each is a different kind of relationship—reception, recognition and franchise lineage.", "evidence_class": "attributed_interpretation", "locators": ["legacy/cultural-impact", "sequel-and-related-media"]},
    ],
    "Q103474": [
        {"question_id": "story.cosmic-knowledge", "question_text": "What scale of story question drives 2001?", "answer": "The film connects an early encounter with a monolith, human technological development, a Jupiter mission and HAL's failure. It frames knowledge and human destiny at a cosmic scale while leaving decisive elements deliberately unresolved.", "evidence_class": "narrative_extraction", "locators": ["plot", "interpretations"]},
        {"question_id": "creative.kubrick-clarke-collaboration", "question_text": "What is the documented writing process?", "answer": "Kubrick and Arthur C. Clarke developed the film over years by combining material from Clarke's stories with new narrative segments, pursuing a work about humanity's relationship to the universe and emotions of wonder, awe and terror.", "evidence_class": "source_fact", "locators": ["production/writing"]},
        {"question_id": "craft.technology-match-cut", "question_text": "What formal technique gives the film a comparison route?", "answer": "The bone-to-satellite match cut links primitive and advanced tools, while the effects account documents front projection and other techniques. These are concrete craft routes for comparison, independent of whether another film shares its philosophy.", "evidence_class": "source_fact", "locators": ["design-and-special-effects/visual-effects"]},
        {"question_id": "interpretation.open-meaning", "question_text": "How should the film's meaning be represented?", "answer": "The source documents sharply different readings of the film's implications, monolith, HAL and ending. CineGraph should expose those interpretations and their sources instead of resolving ambiguity into a single plot explanation.", "evidence_class": "attributed_interpretation", "locators": ["interpretations", "influence"]},
    ],
    "Q1757288": [
        {"question_id": "story.escape-becomes-return", "question_text": "What action-story engine drives Fury Road?", "answer": "Furiosa's escape with Immortan Joe's wives triggers a pursuit, drawing Max into a moving alliance. The story's pressure is physical, but its destination also forces the group to reconsider whether escape or return can change the world they flee.", "evidence_class": "narrative_extraction", "locators": ["plot"]},
        {"question_id": "creative.visual-chase-design", "question_text": "What design principle shaped the filmmaking?", "answer": "George Miller developed the project through thousands of storyboard panels to make it almost a continuous chase with limited dialogue and visual priority. That is a usable form-and-process comparison lens for action writing and direction.", "evidence_class": "source_fact", "locators": ["production/development", "production/filming"]},
        {"question_id": "theme.furiosa-reading", "question_text": "What theme needs attribution rather than a simple label?", "answer": "Academic commentary identifies Furiosa as the dramatic centre and reads the rescue mission through feminism and a possible matriarchal alternative to the film's warlike order. This is an attributed reading, not a universal interpretation.", "evidence_class": "attributed_interpretation", "locators": ["themes/feminism"]},
        {"question_id": "impact.craft-recognition", "question_text": "What recognition is securely documented?", "answer": "The film received extensive critical acclaim and six Academy Awards, including editing, production design, costume, makeup and sound categories. This supports a craft-recognition profile, not a claim that awards prove artistic superiority.", "evidence_class": "source_fact", "locators": ["reception/critical-response", "accolades-and-recognition"]},
    ],
    "Q25136235": [
        {"question_id": "story.social-horror-engine", "question_text": "How does Get Out turn social discomfort into story pressure?", "answer": "Chris's visit to his White girlfriend's family moves from discomfort and microaggressions to coercion, hypnosis and bodily danger. The horror mechanism makes his social perception a survival tool rather than background exposition.", "evidence_class": "narrative_extraction", "locators": ["plot"]},
        {"question_id": "creative.comedy-to-horror", "question_text": "What creative background informed the film?", "answer": "As Jordan Peele's directorial debut, the film draws on his comedy experience: he identified shared mechanics of timing, rhythm and surprise between comedy and horror, while citing The Stepford Wives for the satirical premise.", "evidence_class": "source_fact", "locators": ["production/development"]},
        {"question_id": "story.ending-as-cultural-choice", "question_text": "What does the alternate ending reveal about the film's construction?", "answer": "The original ending led to Chris's arrest; Peele changed it after considering its cultural moment and test-screening reactions, preserving a moment of fear but choosing a more hopeful resolution. This is a rare, evidence-backed route to compare ending design with social context.", "evidence_class": "source_fact", "locators": ["production/filming/alternative-endings"]},
        {"question_id": "theme.post-racial-critique", "question_text": "How should the racial analysis be represented?", "answer": "The article assembles critics, Peele and scholars who read the film through post-racial liberalism, colorblindness, missing-person attention and Afro-pessimism. These interpretations must stay attributed and should never be downgraded to a generic 'race' keyword.", "evidence_class": "attributed_interpretation", "locators": ["themes-and-interpretations", "reception/accolades"]},
    ],
    "Q29588607": [
        {"question_id": "story.mantle-and-belonging", "question_text": "What story engine distinguishes Miles Morales's Spider-Man?", "answer": "Miles inherits a Spider-Man role while navigating family expectations, grief and uncertainty about whether he belongs among more experienced versions of the hero. The multiverse plot externalises that confidence problem rather than merely multiplying cameos.", "evidence_class": "narrative_extraction", "locators": ["plot", "themes"]},
        {"question_id": "creative.why-this-adaptation", "question_text": "What problem did the writers set out to solve?", "answer": "With several Spider-Man films already made, the creators identified Miles Morales—then absent from film—as the reason to make another. The subsequent writing process reshaped the story and third act around that focus.", "evidence_class": "source_fact", "locators": ["production/writing"]},
        {"question_id": "craft.comic-panel-language", "question_text": "What form did animation make possible?", "answer": "The animation team sought the sensation of entering a comic book, combining CGI with linework, painting, dots and other comic techniques. This supplies a precise visual-language comparison lens, not merely an 'animated' genre label.", "evidence_class": "source_fact", "locators": ["production/animation-and-design"]},
        {"question_id": "impact.franchise-route", "question_text": "What response and lineage are documented?", "answer": "The article preserves attributed industry praise and records the direct sequel route from Into the Spider-Verse to Across the Spider-Verse and the planned Beyond the Spider-Verse. Reception claims and franchise facts should remain separate records.", "evidence_class": "attributed_interpretation", "locators": ["reception/industry-response-and-legacy", "franchise/sequels"]},
    ],
    "Q104123": [
        {"question_id": "structure.circular-chronology", "question_text": "What makes Pulp Fiction's structure useful for comparison?", "answer": "The film distributes intersecting crime stories across a nonlinear order, with opening and closing diner sequences overlapping from different points of view. Analysts describe the structure as episodic and circular, offering a specific structural relation beyond shared genre.", "evidence_class": "narrative_extraction", "locators": ["narrative-structure"]},
        {"question_id": "creative.genre-chestnuts", "question_text": "How did the writers approach familiar crime material?", "answer": "The writing history traces the project from an anthology idea, while Tarantino described reworking familiar crime-story situations through intersecting characters. The source supports a claim about recombination of conventions, not a claim that originality means absence of influence.", "evidence_class": "source_fact", "locators": ["production/writing", "critical-analysis"]},
        {"question_id": "industry.independent-breakthrough", "question_text": "What production context matters to its industry story?", "answer": "The financing account records TriStar passing on the script and Miramax taking it on, giving the film a concrete independent-production and distribution route. This is a factual business context rather than an inferred explanation of success.", "evidence_class": "source_fact", "locators": ["production/financing"]},
        {"question_id": "impact.influence-with-disagreement", "question_text": "What legacy claim can be made carefully?", "answer": "The article documents intense contemporary acclaim and later accounts of influence, including a Travolta revival and an imitation wave. It also preserves disagreement around genre labels and the meaning of its violence, so legacy cannot be reduced to a single acclaim score.", "evidence_class": "attributed_interpretation", "locators": ["release-and-reception/critical-response", "legacy-and-influence"]},
    ],
})


def curate_pilot_answers(db: Session, qid: str) -> int:
    """Store human-authored pilot answers only when their referenced passages exist."""
    definitions = DEEP_RESEARCH_PILOTS.get(qid)
    if not definitions:
        return 0
    snapshot = _snapshot_for_qid(db, qid)
    payload = _snapshot_payload(snapshot)
    entity = _entity_for_snapshot(db, qid, payload)
    created = 0
    for definition in definitions:
        answer = db.scalar(select(ResearchAnswer).where(
            ResearchAnswer.subject_entity_id == entity.id,
            ResearchAnswer.question_id == definition["question_id"],
            ResearchAnswer.answer_version == ANSWER_VERSION,
        ))
        if not answer:
            answer = ResearchAnswer(
                subject_entity_id=entity.id,
                question_id=str(definition["question_id"]),
                question_text=str(definition["question_text"]),
                answer=str(definition["answer"]),
                evidence_class=str(definition["evidence_class"]),
                answer_version=ANSWER_VERSION,
                confidence=0.85,
                review_status="review_required",
            )
            db.add(answer)
            db.flush()
            created += 1
        for locator in definition["locators"]:
            passages = list(db.scalars(select(NarrativePassage).where(
                NarrativePassage.subject_entity_id == entity.id,
                NarrativePassage.source_snapshot_id == snapshot.id,
                NarrativePassage.section_locator == locator,
            ).order_by(NarrativePassage.ordinal)))
            if not passages:
                raise ValueError(f"Research answer {definition['question_id']} requires absent section {locator}.")
            for passage in passages:
                exists = db.scalar(select(ResearchAnswerEvidence.id).where(
                    ResearchAnswerEvidence.research_answer_id == answer.id,
                    ResearchAnswerEvidence.narrative_passage_id == passage.id,
                ))
                if not exists:
                    db.add(ResearchAnswerEvidence(
                        research_answer_id=answer.id,
                        narrative_passage_id=passage.id,
                        evidence_locator=str(locator),
                    ))
    db.commit()
    return created


def quality_report(db: Session, qid: str) -> dict[str, object]:
    """Return auditable completeness figures for one structured research pilot."""
    snapshot = _snapshot_for_qid(db, qid)
    payload = _snapshot_payload(snapshot)
    entity = _entity_for_snapshot(db, qid, payload)
    passages = list(db.scalars(select(NarrativePassage).where(
        NarrativePassage.subject_entity_id == entity.id,
        NarrativePassage.source_snapshot_id == snapshot.id,
    )))
    answers = list(db.scalars(select(ResearchAnswer).where(
        ResearchAnswer.subject_entity_id == entity.id,
        ResearchAnswer.answer_version == ANSWER_VERSION,
    )))
    evidence_by_answer = {
        answer.id: list(db.scalars(select(ResearchAnswerEvidence).where(
            ResearchAnswerEvidence.research_answer_id == answer.id,
        )))
        for answer in answers
    }
    missing = [answer.question_id for answer in answers if not evidence_by_answer[answer.id]]
    return {
        "qid": qid,
        "title": entity.canonical_label,
        "source_revision": snapshot.source_revision,
        "license": snapshot.license,
        "attribution_url": snapshot.attribution_url,
        "passages": len(passages),
        "sections": len({passage.section_locator for passage in passages}),
        "citation_markers": sum(len(passage.citation_markers) for passage in passages),
        "research_answers": len(answers),
        "research_evidence_links": sum(len(items) for items in evidence_by_answer.values()),
        "answers_without_evidence": missing,
        "review_statuses": {
            status: sum(answer.review_status == status for answer in answers)
            for status in sorted({answer.review_status for answer in answers})
        },
        "pass": bool(passages) and bool(answers) and not missing,
    }


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Extract attributable Wikipedia passages and curate pilot research answers.")
    parser.add_argument("qid", nargs="*", help="Wikidata film IDs with retained English Wikipedia snapshots")
    parser.add_argument("--curate-pilot", action="store_true", help="Add checked pilot answers where a curation definition exists")
    parser.add_argument("--quality", action="store_true", help="Print evidence completeness after extraction")
    parser.add_argument(
        "--ingestion-manifest", action="append", default=[], metavar="PATH",
        help="Completed selection manifest used by the Wikipedia snapshot run; repeat to process a split selection.",
    )
    parser.add_argument("--progress-every", type=int, default=25, help="Commit-safe progress interval for a selection run")
    args = parser.parse_args()
    if not args.qid and not args.ingestion_manifest:
        parser.error("Provide one or more QIDs or --ingestion-manifest paths.")
    if args.progress_every < 1:
        parser.error("--progress-every must be positive.")
    run_migrations()
    with SessionLocal() as db:
        manifest_uris = [Path(value).resolve().as_uri() for value in args.ingestion_manifest]
        qids = sorted(set(args.qid) | set(selected_qids_from_ingestion_manifests(db, manifest_uris)))
        results = []
        for index, qid in enumerate(qids, start=1):
            result = extract_passages(db, qid)
            result.pop("passages")
            if args.curate_pilot:
                result["answers_created"] = curate_pilot_answers(db, qid)
            if args.quality:
                result["quality"] = quality_report(db, qid)
            results.append(result)
            if len(qids) > args.progress_every and (index % args.progress_every == 0 or index == len(qids)):
                print(json.dumps({
                    "progress": {"completed": index, "total": len(qids)},
                    "passages_created": sum(int(item["passages_created"]) for item in results),
                }), flush=True)
        if len(qids) <= args.progress_every:
            print(json.dumps(results, indent=2))
        else:
            print(json.dumps({
                "complete": {"films": len(qids), "passages_created": sum(int(item["passages_created"]) for item in results)},
            }))


if __name__ == "__main__":
    main()
