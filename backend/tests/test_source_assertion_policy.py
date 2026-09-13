from app.services.source_assertion_policy import project_wikidata_statement, review_status_for_target


def mainsnak(value_type: str, value, *, snaktype: str = "value") -> dict:
    return {"snaktype": snaktype, "datavalue": {"type": value_type, "value": value}}


def test_credit_target_is_a_resolved_typed_person() -> None:
    decision = project_wikidata_statement(
        "P57", mainsnak("wikibase-entityid", {"id": "Q10", "entity-type": "item"}),
    )

    assert decision.outcome == "project"
    assert (decision.predicate, decision.object_qid, decision.object_kind, decision.review_status) == (
        "director", "Q10", "person", "resolved",
    )


def test_character_property_uses_the_existing_character_entity_kind() -> None:
    decision = project_wikidata_statement(
        "P674", mainsnak("wikibase-entityid", {"id": "Q200"}),
    )

    assert (decision.predicate, decision.object_kind) == ("character", "character")
    assert review_status_for_target(decision, "character") == "resolved"
    assert review_status_for_target(decision, "film") == "review_required"


def test_work_relationship_stays_review_required_until_target_is_classified() -> None:
    decision = project_wikidata_statement(
        "P144", mainsnak("wikibase-entityid", {"id": "Q99"}),
    )

    assert (decision.predicate, decision.object_kind, decision.review_status) == (
        "based_on", "unknown_work", "review_required",
    )
    assert review_status_for_target(decision, "unknown_work") == "review_required"
    assert review_status_for_target(decision, "book") == "resolved"
    assert review_status_for_target(decision, "person") == "review_required"


def test_time_and_quantity_values_preserve_source_precision_and_units() -> None:
    released = project_wikidata_statement("P577", mainsnak("time", {
        "time": "+2008-07-18T00:00:00Z", "precision": 11,
        "calendarmodel": "http://www.wikidata.org/entity/Q1985727", "before": 0, "after": 0,
    }))
    runtime = project_wikidata_statement("P2047", mainsnak("quantity", {
        "amount": "+152", "unit": "http://www.wikidata.org/entity/Q7727",
        "lowerBound": "+151", "upperBound": "+153",
    }))

    assert released.value_json == {
        "type": "time", "time": "+2008-07-18T00:00:00Z",
        "precision": 11, "calendar_model": "Q1985727",
    }
    assert runtime.value_json == {
        "type": "quantity", "amount": "+152", "unit": "Q7727",
        "lower_bound": "+151", "upper_bound": "+153",
    }


def test_unsupported_and_non_value_statements_are_not_projected() -> None:
    unsupported = project_wikidata_statement("P999999", mainsnak("string", "x"))
    missing = project_wikidata_statement("P57", {"snaktype": "novalue"})

    assert (unsupported.outcome, unsupported.reason) == (
        "unsupported", "source property is not allow-listed",
    )
    assert (missing.outcome, missing.reason) == (
        "invalid", "statement has no concrete value",
    )
