"""Curated, reproducible 200-question CineGraph retrieval benchmark.

This module contains questions and evidence locators, not copied source prose.
``build_benchmark_v1`` resolves every locator to an immutable local snapshot
revision and content hash before producing the benchmark manifest.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assertion,
    CanonicalEntity,
    EvidenceChunk,
    EvidenceChunkRun,
    NarrativePassage,
    SourceSnapshot,
)
from app.services.retrieval_benchmark import (
    BenchmarkCase,
    BenchmarkTarget,
    RetrievalBenchmark,
    validate_benchmark,
)


# qid, title, plot locator, plot question, production locator, production
# question, reception locator, reception question. Questions were written from
# the cited passage and reviewed against the retained local source revision.
FILMS = (
    ("Q103474", "2001: A Space Odyssey", "plot", "How does Bowman overcome HAL after the computer locks him outside Discovery One?", "production/writing", "How did Kubrick and Clarke develop the screenplay and novel together while settling on the film's title?", "reception-and-legacy/critical-response", "Why did some early critics find 2001 baffling or dull while others treated it as a major cinematic achievement?"),
    ("Q103569", "Alien", "plot", "How does the quarantine breach bring the creature aboard the Nostromo and turn the return journey into a survival trap?", "production/writing", "How did Dan O'Bannon's failed Dune work connect him with artists who later shaped Alien?", "legacy/critical-reassessment", "How did Alien's reputation change after reviews initially dismissed it as an expensive haunted-house movie?"),
    ("Q104123", "Pulp Fiction", "narrative-structure", "How does Pulp Fiction reorder its intersecting crime stories into a circular rather than chronological narrative?", "production/filming", "How did the production use film stock, lenses, and a modest budget to create a larger visual scale?", "legacy-and-influence", "Which aspects of Pulp Fiction's dialogue, structure, and genre mixture became influential after release?"),
    ("Q104905", "WALL-E", "plot", "Why does the discovery of a living plant make AUTO an obstacle to WALL-E and EVE's attempt to return humanity to Earth?", "production/writing", "What research changed Pixar's original idea for explaining the passengers' physical decline aboard the Axiom?", "reception/critical-response", "How did critics interpret WALL-E as both an accessible romance and a warning about consumption and environmental neglect?"),
    ("Q105598", "Die Hard", "plot", "How does Hans Gruber exploit John McClane's incomplete knowledge when they first meet face to face?", "production/re-write", "Why did Alan Rickman's American accent enable the writers to add an encounter between McClane and Gruber before the finale?", "legacy/critical-reassessment", "Why did Die Hard's vulnerable everyman hero become a template for later action films?"),
    ("Q11621", "E.T. the Extra-Terrestrial", "plot", "How does Elliott protect a stranded visitor while government agents close in on his family?", "production/filming", "How did shooting E.T. largely in chronological order affect the child actors and the emotional farewell?", "reception/home-media", "Why was E.T.'s low-priced VHS release considered unusual, and what sales result followed?"),
    ("Q13417189", "Interstellar", "plot", "How does the time dilation on Miller's planet raise the human cost of Cooper's exploration mission?", "production/principal-photography", "How did Nolan and Hoytema combine IMAX photography, practical sets, and on-location work for Interstellar?", "reception/box-office", "What made Interstellar's South Korean box-office performance especially notable?"),
    ("Q155653", "Spirited Away", "plot", "What forces Chihiro to act after her parents are transformed and she becomes trapped in the spirit world?", "production/development-and-inspiration", "Which real places, folklore, and personal observations informed Miyazaki's development of Spirited Away?", "reception/critical-response", "How did critics and later polls establish Spirited Away's international reputation?"),
    ("Q163038", "Psycho", "plot", "How does Marion Crane's theft and detour place her inside Norman Bates's private trap?", "production/pre-production", "How did Hitchcock use a television crew and cost-conscious production methods to make Psycho?", "legacy", "How did Psycho's editing, shower scene, and audience manipulation influence later horror filmmaking?"),
    ("Q163872", "The Dark Knight", "plot", "How does the alliance against organized crime provoke the Joker's campaign of escalation in Gotham?", "production/special-effects-and-design", "How did the designers balance realism, mobility, and menace in the Batsuit, Joker, and Two-Face effects?", "reception/accolades", "Why were Heath Ledger's posthumous acting awards a landmark for comic-book films?"),
    ("Q165817", "Saving Private Ryan", "plot", "Why does Ryan refuse immediate rescue, and how does Miller turn that refusal into a final defensive mission?", "production/pre-production", "Why was Ireland chosen to recreate the Normandy landings, and what preparation did the production undertake?", "legacy/cultural-influence", "How did Saving Private Ryan's opening battle reshape later depictions of combat on film and television?"),
    ("Q167726", "Jurassic Park", "plot", "How do the cloning debate and failed park tour establish the conflict before the dinosaurs escape?", "production/dinosaurs-on-screen/list", "How did Jurassic Park divide dinosaur work between animatronics, puppetry, and computer-generated imagery?", "legacy/impact", "Why is Jurassic Park's use of computer-generated dinosaurs regarded as a filmmaking landmark?"),
    ("Q170564", "Terminator 2: Judgment Day", "plot", "How does Sarah Connor's attempt to kill Miles Dyson challenge the heroes' effort to prevent Judgment Day?", "production/casting", "Why did James Cameron describe Robert Patrick's T-1000 as a Porsche-like contrast to Schwarzenegger's Terminator?", "legacy/cultural-influence", "How did Terminator 2's digital effects change expectations for computer-generated characters?"),
    ("Q171048", "Toy Story", "plot", "Why does Buzz Lightyear's arrival trigger Woody's fear of replacement and the story's central rivalry?", "production/writing", "How did the McKee seminar and Joss Whedon's revisions influence Toy Story's character-driven obstacles?", "reception/accolades", "Why was Toy Story's Academy Special Achievement Award historically significant?"),
    ("Q172241", "The Shawshank Redemption", "plot", "How does Brooks's institutionalization contrast with Andy's insistence on hope beyond prison?", "production/filming", "How was Andy's sewer escape created as a practical production sequence?", "legacy/cultural-influence", "How did The Shawshank Redemption grow from an underperforming release into an enduring audience favorite?"),
    ("Q174284", "Raiders of the Lost Ark", "plot", "How does the Nazis' incomplete medallion information allow Indiana Jones to locate the Ark first?", "production/conception", "How did the filmmakers turn a modern adventure idea into a quest built from old serial conventions and the Ark?", "reception/critical-response", "How did critics evaluate Raiders as both a modern blockbuster and a revival of adventure serials?"),
    ("Q1757288", "Mad Max: Fury Road", "plot", "Why does Max join Furiosa after first trying to steal the War Rig for himself?", "production/development", "Why did Fury Road spend years in development before its vehicles, route, and production plan became feasible?", "reception/critical-response", "What qualities led critics to treat Fury Road as an unusually accomplished action film?"),
    ("Q17738", "Star Wars", "plot", "How does the murder of Luke's family turn his refusal to leave Tatooine into commitment to the rebellion?", "production/filming", "How did weather, malfunctioning props, and the Tunisia location complicate the filming of Star Wars?", "reception/accolades", "Which technical achievements were recognized when Star Wars dominated its Academy Awards categories?"),
    ("Q181795", "The Empire Strikes Back", "plot", "How do Luke's Dagobah training and his friends' Cloud City flight converge in Vader's trap?", "production/writing", "How did the screenplay pass through Leigh Brackett, George Lucas, and Lawrence Kasdan during development?", "reception/accolades", "How was The Empire Strikes Back recognized by major award bodies after release?"),
    ("Q182692", "Apocalypse Now", "plot", "How does Willard's upriver assignment become a confrontation with Kurtz and the morality of the war itself?", "production/post-production-and-audio", "Why were editing and audio construction unusually demanding during Apocalypse Now's post-production?", "legacy", "How did later critics and audience polls establish Apocalypse Now as a defining war film?"),
    ("Q183081", "No Country for Old Men", "plot", "How does Llewelyn Moss's discovery of the money connect him, Chigurh, and Bell in a three-way pursuit?", "production/writing/differences-from-the-novel", "What did the Coens preserve or alter when adapting No Country for Old Men from the novel?", "reception-and-legacy/accolades", "How did No Country for Old Men's awards distinguish its writing, direction, and performances?"),
    ("Q184843", "Blade Runner", "plot", "How does Roy Batty's demand for more life connect his confrontation with Tyrell to his final encounter with Deckard?", "production/casting", "Why was Rutger Hauer cast as Roy Batty before Ridley Scott had met him?", "reception/awards-and-nominations", "Which aspects of Blade Runner's design and cinematography received formal awards recognition?"),
    ("Q189505", "Jaws", "plot", "How does Mayor Vaughn's refusal to close the beaches enlarge Brody's conflict beyond the shark itself?", "production/filming", "How did the three mechanical sharks nicknamed Bruce reshape the filming of Jaws when they repeatedly failed?", "reception/critical-reception", "What did critics praise and criticize about Jaws when it first opened?"),
    ("Q189540", "Seven Samurai", "plot", "How does Kikuchiyo's revelation about farmers change the samurai's understanding of the village alliance?", "production/filming", "How did weather, locations, horses, and Kurosawa's methods make Seven Samurai's filming unusually difficult?", "reception/accolades", "How did international festival and award recognition help establish Seven Samurai's reputation?"),
    ("Q210756", "The Thing", "plot", "How does the Norwegian dog introduce a hidden threat that makes the Antarctic crew distrust one another?", "production/writing", "Why did the writers return to the original novella instead of simply remaking the earlier film adaptation?", "reception/critical-reception", "Why were The Thing's creature effects praised by some reviewers and reviled by others?"),
    ("Q24871", "Avatar", "plot", "How does Jake's divided loyalty collapse after the destruction of Hometree?", "production/casting", "Why was the relatively unknown Sam Worthington selected to lead Avatar?", "reception/thematic-analysis", "How did commentators reach conflicting political, religious, and racial readings of Avatar?"),
    ("Q25136235", "Get Out", "plot", "How does Chris turn the Armitage family's coercive methods against them during his escape?", "production/filming", "How did filming locations and practical production choices create the Armitage estate and the Sunken Place?", "reception/accolades", "Why did Get Out's awards campaign and genre classification become part of its reception story?"),
    ("Q29588607", "Spider-Man: Into the Spider-Verse", "plot", "How does Aaron Davis's identity as the Prowler turn Miles's refusal to surrender into a personal loss?", "production/development", "How did the filmmakers keep Miles Morales central while developing a story with several Spider-people?", "reception/industry-response-and-legacy", "How did animation professionals describe Spider-Verse's influence on later studio animation?"),
    ("Q44578", "Titanic", "plot", "How does the search for the Heart of the Ocean frame Rose's account of the disaster and her relationship with Jack?", "production/filming", "How did the large water sets and ship reconstruction shape Titanic's filming process?", "reception/box-office", "Which box-office milestones made Titanic an unprecedented global theatrical success?"),
    ("Q47221", "Taxi Driver", "plot", "How does Travis Bickle's isolation develop into preparation for public violence?", "production/development", "How did Paul Schrader's insomnia, isolation, and personal crisis inform the Taxi Driver screenplay?", "reception/accolades", "How did festival and awards recognition contribute to Taxi Driver's standing?"),
    ("Q47703", "The Godfather", "plot", "How does the attack on Vito Corleone pull Michael from family outsider into the center of the crime war?", "production/casting", "Why did Paramount resist the casting of Marlon Brando and Al Pacino, and how were those decisions overcome?", "reception/box-office", "How did The Godfather's theatrical earnings and reissues establish its blockbuster status?"),
    ("Q483941", "Schindler's List", "plot", "How does witnessing the ghetto liquidation change Schindler from war profiteer into rescuer?", "production/cinematography", "How did handheld camerawork, black-and-white photography, and limited storyboarding create the film's documentary quality?", "reception/accolades", "Which major awards confirmed Schindler's List's critical standing?"),
    ("Q488655", "Groundhog Day", "plot", "How does repeated confinement in the same day force Phil to change what he values?", "production/preproduction", "Why did scouting more than sixty towns lead the filmmakers to choose Woodstock instead of Punxsutawney?", "legacy/cultural-impact", "How did Groundhog Day become a cultural shorthand for repetitive situations?"),
    ("Q499152", "The Breakfast Club", "plot", "How does detention expose the home pressures hidden beneath the students' school stereotypes?", "production/casting", "How did casting changes involving Emilio Estevez and Judd Nelson shape the final ensemble?", "reception/critical-response", "Why did some original reviews criticize The Breakfast Club even while praising parts of its cast?"),
    ("Q57982486", "Knives Out", "plot", "How does the toxicology result reverse the apparent cause of Harlan's death and expose Ransom's plan?", "production/set-design", "How did the filmmakers source and integrate the mansion's automata and decorative objects?", "reception/accolades", "Which nominations recognized Knives Out's screenplay and ensemble?"),
    ("Q61448040", "Parasite", "plot", "How does Ki-woo's forged tutoring role open the Park household to the rest of the Kim family?", "production/filming", "How was the Park house designed and built to control blocking, class perspective, and camera movement?", "reception/critical-response", "How did critics connect Parasite's genre shifts to its critique of class inequality?"),
    ("Q788822", "Her", "plot", "How does Theodore's relationship with Samantha deepen while their human and artificial forms of growth diverge?", "production/development", "How did Spike Jonze's personal experiences and script development shape Her?", "legacy", "Why have retrospective writers found Her's comparatively optimistic human-AI relationship newly relevant?"),
    ("Q83495", "The Matrix", "plot", "How does Neo's search for the truth place the Agents' control against Morpheus's guidance?", "production/sound-effects-and-music", "How were layered sound design and music used to distinguish the Matrix's action and virtual world?", "legacy/filmmaking", "How did bullet time and The Matrix's visual grammar influence later filmmaking?"),
    ("Q867283", "The Iron Giant", "plot", "How does Hogarth teach the Giant that he can choose to be a hero rather than the weapon others expect?", "production/animation", "How did animating the Giant with computer graphics on twos help it fit the hand-drawn world?", "reception/visible-anchor-awards-accolades-text-accolades", "Which animation awards recognized The Iron Giant despite its weak theatrical performance?"),
    ("Q91540", "Back to the Future", "plot", "How does Marty's attempt to save George in 1955 endanger Marty's own existence?", "production/casting", "Why did replacing Eric Stoltz with Michael J. Fox require the production to restart major scenes?", "legacy/modern-reception", "How has Back to the Future's reputation held up in modern critical and audience rankings?"),
)


CROSS_FILM_QUESTIONS = (
    ("Q788822", "Q170564", "How do Her and Terminator 2 imagine different kinds of learning relationship between humans and artificial intelligence?"),
    ("Q184843", "Q867283", "How do Blade Runner and The Iron Giant let artificial beings define humanity beyond their assigned purpose?"),
    ("Q83495", "Q104905", "How do The Matrix and WALL-E portray automated systems maintaining control over passive human populations?"),
    ("Q189505", "Q167726", "How do Jaws and Jurassic Park turn an official's ignored warning into a wider public disaster?"),
    ("Q163872", "Q183081", "How do The Dark Knight and No Country for Old Men use an antagonist to pressure an existing moral and legal order?"),
    ("Q47703", "Q61448040", "How do The Godfather and Parasite make family advancement depend on entry into a more powerful household or institution?"),
    ("Q17738", "Q91540", "How does a threat to family change the young protagonist's commitment in Star Wars and Back to the Future?"),
    ("Q11621", "Q867283", "How do E.T. and The Iron Giant build drama around a child protecting a misunderstood nonhuman visitor?"),
    ("Q172241", "Q488655", "How do The Shawshank Redemption and Groundhog Day use repeated confinement to test whether a person can transform?"),
    ("Q163038", "Q25136235", "How do Psycho and Get Out turn an apparently hospitable private home into a trap?"),
    ("Q174284", "Q103474", "How do Raiders of the Lost Ark and 2001 connect a dangerous quest with knowledge humanity may not control?"),
    ("Q189540", "Q165817", "How do Seven Samurai and Saving Private Ryan put group duty in conflict with individual survival?"),
    ("Q1757288", "Q24871", "How does a divided outsider join a resistance movement in Fury Road and Avatar?"),
    ("Q44578", "Q13417189", "How do Titanic and Interstellar test personal bonds through extreme separation and lost time?"),
    ("Q104123", "Q57982486", "How do Pulp Fiction and Knives Out use reordered revelation to reframe a crime story?"),
    ("Q103569", "Q210756", "How do Alien and The Thing turn a confined crew against a disguised extraterrestrial threat?"),
    ("Q105598", "Q163872", "How do Die Hard and The Dark Knight pit a hero with incomplete information against a planning mastermind?"),
    ("Q499152", "Q171048", "How do The Breakfast Club and Toy Story build ensemble conflict from fear of social replacement?"),
    ("Q483941", "Q165817", "How do Schindler's List and Saving Private Ryan frame rescue as a moral duty rather than a simple victory?"),
    ("Q170564", "Q83495", "How do Terminator 2 and The Matrix use a machine or guide to resist a future-controlling system?"),
    ("Q182692", "Q47221", "How do Apocalypse Now and Taxi Driver turn an outward mission into an inward descent?"),
    ("Q29588607", "Q17738", "How does mentor loss force a young hero to accept a larger role in Spider-Verse and Star Wars?"),
    ("Q155653", "Q25136235", "How do Spirited Away and Get Out trap an outsider under the rules of an unfamiliar household or world?"),
    ("Q24871", "Q61448040", "How do Avatar and Parasite use physical space to make hierarchy visible?"),
    ("Q104905", "Q13417189", "How do WALL-E and Interstellar make ecological collapse the pressure behind survival beyond Earth?"),
    ("Q189505", "Q210756", "How do Jaws and The Thing let uncertainty about a threat fracture collective trust?"),
    ("Q47703", "Q163872", "How do The Godfather and The Dark Knight blur legitimacy while institutions bargain with crime?"),
    ("Q184843", "Q788822", "How do Blade Runner and Her approach artificial personhood through memory and emotional growth?"),
    ("Q488655", "Q91540", "How does altered time force personal responsibility in Groundhog Day and Back to the Future?"),
    ("Q167726", "Q103569", "How do Jurassic Park and Alien show corporate or scientific ambition unleashing a creature threat?"),
    ("Q1757288", "Q189540", "How do Fury Road and Seven Samurai form reluctant alliances to protect a vulnerable group?"),
    ("Q44578", "Q483941", "How does an individual moral awakening unfold inside historical catastrophe in Titanic and Schindler's List?"),
    ("Q163038", "Q183081", "How do Psycho and No Country for Old Men destabilize the audience's expectation of a secure protagonist?"),
    ("Q174284", "Q17738", "How do Raiders and Star Wars turn personal pressure into commitment to a serial-style quest?"),
    ("Q104123", "Q499152", "How do Pulp Fiction and The Breakfast Club organize several character perspectives into one connected structure?"),
    ("Q57982486", "Q25136235", "How do Knives Out and Get Out hide a coercive system inside a wealthy household?"),
    ("Q11621", "Q104905", "How do E.T. and WALL-E use a small signal and a mostly nonverbal bond to drive a journey home?"),
    ("Q171048", "Q867283", "How do Toy Story and The Iron Giant let a nonhuman protagonist choose an identity beyond an assigned role?"),
    ("Q103474", "Q13417189", "How do 2001 and Interstellar combine cosmic travel, artificial intelligence, and human survival?"),
    ("Q182692", "Q165817", "How does a wartime mission become a moral test rather than only a tactical objective in Apocalypse Now and Saving Private Ryan?"),
)


DIRECTOR_FACTS = (
    ("Q103474", "2001: A Space Odyssey", "Q2001"), ("Q214013", "Birdman", "Q55215"),
    ("Q218458", "BlacKkKlansman", "Q51566"), ("Q103569", "Alien", "Q56005"),
    ("Q104814", "Aliens", "Q42574"), ("Q200299", "All About Eve", "Q51583"),
    ("Q466781", "All the President's Men", "Q51519"), ("Q190956", "Amadeus", "Q51525"),
    ("Q218999", "A Man for All Seasons", "Q55420"), ("Q106428", "A Beautiful Mind", "Q103646"),
    ("Q59653", "Argo", "Q483118"), ("Q212129", "A Streetcar Named Desire", "Q72717"),
    ("Q24871", "Avatar", "Q42574"), ("Q91540", "Back to the Future", "Q187364"),
    ("Q221384", "Black Hawk Down", "Q56005"), ("Q74958", "Blood Diamond", "Q314142"),
    ("Q193066", "Breakfast at Tiffany's", "Q56093"), ("Q86427", "Breathless", "Q53001"),
    ("Q213411", "Cast Away", "Q187364"), ("Q219155", "Dawn of the Dead", "Q51511"),
    ("Q39975", "Dazed and Confused", "Q40035"), ("Q106316", "Dead Poets Society", "Q55424"),
    ("Q814778", "Deliverance", "Q55277"), ("Q105598", "Die Hard", "Q270639"),
    ("Q106871", "Die Hard with a Vengeance", "Q270639"), ("Q201819", "District 9", "Q715838"),
    ("Q458656", "Dog Day Afternoon", "Q51559"), ("Q192409", "Down by Law", "Q191755"),
    ("Q105702", "Dr. Strangelove", "Q2001"), ("Q510657", "For a Few Dollars More", "Q164562"),
    ("Q217182", "Frankenweenie", "Q56008"), ("Q331617", "Enter the Dragon", "Q1888426"),
    ("Q750028", "Evil Dead II", "Q275402"), ("Q190050", "Fight Club", "Q184903"),
    ("Q208204", "Finding Neverland", "Q28497"), ("Q128518", "Gladiator", "Q56005"),
    ("Q106440", "Goldfinger", "Q363653"), ("Q42047", "Goodfellas", "Q41148"),
    ("Q193835", "Good Will Hunting", "Q25186"), ("Q59249", "Hachi: A Dog's Tale", "Q316051"),
)


# Human-selected answer concepts, aligned by FILMS order. They locate the
# paragraph that contains the answer inside a repeated section path; they are
# not derived from any retriever's ranking.
TARGET_ANCHORS = {
    "plot_character_structure": (
        "emergency airlock", "quarantine protocol", "nonlinear circular", "plant AUTO", "escaped hostage",
        "government agents", "Miller planet", "parents transformed", "Marion Crane", "organized crime Joker",
        "Ryan refuses", "park tour", "Miles Dyson", "Buzz replacement", "Brooks institutionalized",
        "incomplete medallion", "War Rig", "aunt uncle killed", "Cloud City trap", "Kurtz mission",
        "cash Chigurh Bell", "Roy Tyrell Deckard", "close beaches", "Kikuchiyo farmers", "Norwegian dog",
        "Hometree", "cotton escape", "Aaron Prowler", "Heart Ocean", "guns assassination",
        "attack Vito Michael", "red coat", "change himself", "home lives", "toxicology Ransom",
        "tutoring Park", "relationship grow learn", "Agents Morpheus", "choose Superman", "George existence",
    ),
    "production_craft": (
        "novel screenplay title", "Dune Giger", "film stock budget", "Gels atrophy", "American accent Gruber",
        "chronological farewell", "IMAX practical", "folklore inspiration", "television crew budget", "Batsuit Two-Face",
        "Ireland Normandy", "animatronic computer", "Porsche Patrick", "McKee Whedon", "sewage tunnel",
        "Ark serial", "development vehicles", "Tunisia malfunction", "Brackett Kasdan", "sound mixing",
        "differences novel", "Hauer cast", "Bruce shark", "weather horses", "novella remake",
        "Worthington unknown", "Alabama filming", "Miles Morales central", "water tank ship", "insomnia isolation",
        "Brando Pacino", "handheld black white", "Woodstock sixty towns", "Estevez Nelson", "automata mansion",
        "house set", "divorce screenplay", "sound effects music", "computer graphics twos", "Stoltz Fox",
    ),
    "reception_legacy": (
        "baffling harrowing", "haunted house reassessment", "influence dialogue nonlinear", "consumption environmental", "everyman imitators",
        "VHS sales", "South Korea", "poll greatest", "shower influence", "Ledger posthumous",
        "combat influence", "computer generated landmark", "computer-generated influence", "Special Achievement", "cult audience",
        "serial revival", "action critics", "Academy Awards", "award nominations", "number one war film",
        "Academy awards", "cinematography design", "critical praise", "Venice awards", "effects reviled",
        "militarism pantheism race", "Comedy classification", "animation industry", "billion record", "festival awards",
        "box office earnings", "Academy awards", "cultural shorthand", "negative reviews", "screenplay nominations",
        "class inequality", "optimistic AI", "bullet time influence", "Annie Awards", "greatest films",
    ),
}


CROSS_TARGET_ANCHORS = (
    ("learn grow", "protector John"), ("replicant humanity", "choose Superman"),
    ("machines control", "AUTO directive"), ("beaches close", "park safety"),
    ("Joker chaos", "Bell violence"), ("Michael family", "Kim family"),
    ("aunt uncle killed", "George existence"), ("Elliott protect", "Hogarth protect"),
    ("Brooks hope", "change himself"), ("Bates motel", "Armitage escape"),
    ("Ark medallion", "monolith mission"), ("samurai village", "Ryan refuses"),
    ("Furiosa alliance", "Jake Hometree"), ("Rose Jack", "time dilation"),
    ("nonlinear circular", "toxicology Ransom"), ("quarantine creature", "Norwegian dog"),
    ("escaped hostage", "Joker plan"), ("stereotypes home", "Buzz replacement"),
    ("Schindler rescue", "Miller rescue"), ("protector John", "Morpheus Agents"),
    ("Kurtz mission", "violence isolation"), ("Aaron Prowler", "aunt uncle killed"),
    ("parents transformed", "Armitage trap"), ("Hometree hierarchy", "Park house basement"),
    ("plant Earth", "Earth survival"), ("beaches shark", "distrust creature"),
    ("Michael crime", "Dent Joker crime"), ("replicant memory", "Samantha growth"),
    ("time loop change", "George future"), ("park cloning", "quarantine creature"),
    ("Furiosa vulnerable", "village farmers"), ("Rose disaster", "red coat"),
    ("Marion death", "Moss death Bell"), ("Ark quest", "rebellion quest"),
    ("nonlinear circular", "students stories"), ("Harlan family", "Armitage family"),
    ("phone home", "plant home"), ("Buzz identity", "choose Superman"),
    ("HAL monolith", "space survival"), ("Kurtz morality", "Ryan mission"),
)

COLLECTION_CODE = "english-1000-retained-narrative-v1"
CHUNKER_VERSION = "spacy-sentencizer-evidence-v3"


def _split(index: int) -> str:
    return "development" if index % 4 == 0 else "test"


def _narrative_target(
    db: Session, *, qid: str, locator: str, answer_anchor: str, group: str | None = None,
) -> BenchmarkTarget:
    rows = db.execute(
        select(NarrativePassage, SourceSnapshot)
        .join(CanonicalEntity, CanonicalEntity.id == NarrativePassage.subject_entity_id)
        .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
        .where(
            CanonicalEntity.wikidata_id == qid,
            NarrativePassage.section_locator == locator,
            NarrativePassage.id.in_(
                select(EvidenceChunk.narrative_passage_id)
                .join(EvidenceChunkRun, EvidenceChunkRun.id == EvidenceChunk.preprocessing_run_id)
                .where(
                    EvidenceChunkRun.collection_code == COLLECTION_CODE,
                    EvidenceChunkRun.chunker_version == CHUNKER_VERSION,
                    EvidenceChunkRun.status == "complete",
                    EvidenceChunk.quality_status == "eligible",
                )
            ),
        )
        .order_by(SourceSnapshot.retrieved_at.desc(), NarrativePassage.ordinal)
    ).all()
    if not rows:
        raise ValueError(f"No narrative target for {qid} at {locator!r}")
    latest_snapshot_id = rows[0][0].source_snapshot_id
    latest_rows = [row for row in rows if row[0].source_snapshot_id == latest_snapshot_id]
    anchor_terms = tuple(term for term in answer_anchor.casefold().split() if len(term) > 2)
    scored = [
        (sum(passage.content.casefold().count(term) for term in anchor_terms), -passage.ordinal, passage, snapshot)
        for passage, snapshot in latest_rows
    ]
    score, _, passage, snapshot = max(scored, key=lambda item: (item[0], item[1]))
    if score == 0:
        raise ValueError(f"Answer anchor {answer_anchor!r} did not resolve inside {qid} {locator!r}")
    return BenchmarkTarget(
        group=group or qid,
        kind="narrative_passage",
        subject_qid=qid,
        source_revision=snapshot.source_revision,
        section_locator=passage.section_locator,
        content_hash=passage.content_hash,
    )


def _assertion_target(db: Session, *, subject_qid: str, predicate: str, object_qid: str) -> BenchmarkTarget:
    assertion = db.scalar(
        select(Assertion)
        .join(CanonicalEntity, CanonicalEntity.id == Assertion.subject_entity_id)
        .where(
            CanonicalEntity.wikidata_id == subject_qid,
            Assertion.predicate == predicate,
            Assertion.review_status.in_(("resolved", "published")),
            Assertion.object_entity.has(CanonicalEntity.wikidata_id == object_qid),
        )
        .order_by(Assertion.created_at.desc())
    )
    if assertion is None:
        raise ValueError(f"No reviewed {predicate} assertion from {subject_qid} to {object_qid}")
    return BenchmarkTarget(
        group=subject_qid,
        kind="assertion",
        subject_qid=subject_qid,
        source_revision=assertion.source_revision,
        predicate=predicate,
        object_qid=object_qid,
    )


def build_benchmark_v1(db: Session) -> RetrievalBenchmark:
    cases: list[BenchmarkCase] = []
    category_specs = (
        ("plot_character_structure", 2, 3),
        ("production_craft", 4, 5),
        ("reception_legacy", 6, 7),
    )
    plot_locators = {qid: plot_locator for qid, _, plot_locator, *_ in FILMS}
    for category, locator_index, question_index in category_specs:
        for index, (film, answer_anchor) in enumerate(zip(FILMS, TARGET_ANCHORS[category], strict=True)):
            qid, title = film[0], film[1]
            adversarial = index % 2 == 0
            cases.append(BenchmarkCase(
                case_id=f"{category}.{index + 1:03d}", category=category, split=_split(index),
                question_id={
                    "plot_character_structure": "story.plot_character_structure",
                    "production_craft": "craft.production",
                    "reception_legacy": "reception.reception_legacy",
                }[category], question_text=film[question_index],
                evidence_class="narrative_extraction", subject_qids=(qid,), adversarial=adversarial,
                challenge_tags=("indirect_paraphrase",) if adversarial else (),
                targets=(_narrative_target(
                    db, qid=qid, locator=film[locator_index], answer_anchor=answer_anchor,
                ),),
            ))

    for index, (qid, title, director_qid) in enumerate(DIRECTOR_FACTS):
        adversarial = index % 2 == 0
        question = (
            f"Which filmmaker was at the helm of {title}?" if adversarial else f"Who directed {title}?"
        )
        cases.append(BenchmarkCase(
            case_id=f"objective_fact.{index + 1:03d}", category="objective_fact", split=_split(index),
            question_id="credit.director", question_text=question, evidence_class="source_fact",
            subject_qids=(qid,), adversarial=adversarial,
            challenge_tags=("role_paraphrase",) if adversarial else (),
            targets=(_assertion_target(db, subject_qid=qid, predicate="director", object_qid=director_qid),),
        ))

    for index, ((first_qid, second_qid, question), anchors) in enumerate(zip(
        CROSS_FILM_QUESTIONS, CROSS_TARGET_ANCHORS, strict=True,
    )):
        cases.append(BenchmarkCase(
            case_id=f"cross_film_comparison.{index + 1:03d}", category="cross_film_comparison",
            split=_split(index), question_id="story.cross_film_comparison", question_text=question,
            evidence_class="narrative_extraction", subject_qids=(first_qid, second_qid), adversarial=True,
            challenge_tags=("multi_subject", "analogy_without_shared_keywords"),
            targets=(
                _narrative_target(
                    db, qid=first_qid, locator=plot_locators[first_qid], answer_anchor=anchors[0], group=first_qid,
                ),
                _narrative_target(
                    db, qid=second_qid, locator=plot_locators[second_qid], answer_anchor=anchors[1], group=second_qid,
                ),
            ),
        ))
    benchmark = RetrievalBenchmark(
        version="cinegraph-retrieval-benchmark-v1",
        adjudication_status="assistant_evidence_reviewed_human_review_required",
        cases=tuple(cases),
    )
    validate_benchmark(benchmark)
    return benchmark


def write_benchmark(benchmark: RetrievalBenchmark, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(benchmark), indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the evidence-fingerprinted CineGraph benchmark v1.")
    parser.add_argument(
        "--output", default="backend/tests/fixtures/retrieval-benchmark-v1.json",
        help="Small manifest only; source prose remains in the local corpus.",
    )
    arguments = parser.parse_args()
    from app.db import SessionLocal

    with SessionLocal() as db:
        benchmark = build_benchmark_v1(db)
    write_benchmark(benchmark, Path(arguments.output))
    print(json.dumps({
        "output": arguments.output,
        "version": benchmark.version,
        "cases": len(benchmark.cases),
        "adjudication_status": benchmark.adjudication_status,
    }, indent=2))


if __name__ == "__main__":
    main()
