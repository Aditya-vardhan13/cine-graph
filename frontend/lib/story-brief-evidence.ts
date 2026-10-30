import type { PinnedEvidence } from "./writer-study-export";

export type DraftEvidenceSelection =
  | { ready: true; firstIds: string[]; secondIds: string[] }
  | { ready: false; reason: string };

/** Only writer-selected source IDs may reach the optional model draft. */
export function selectDraftEvidence(
  pinned: PinnedEvidence[], firstEntityId: string, secondEntityId: string,
): DraftEvidenceSelection {
  const idsFor = (entityId: string) => pinned
    .filter((item) => item.film_entity_id === entityId)
    .map((item) => item.chunk_id);
  const firstIds = idsFor(firstEntityId);
  const secondIds = idsFor(secondEntityId);
  if (!firstIds.length || !secondIds.length || firstIds.length > 3 || secondIds.length > 3) {
    return { ready: false, reason: "Pin one to three source passages from each film before drafting. You decide what the model may read." };
  }
  if (new Set([...firstIds, ...secondIds]).size !== firstIds.length + secondIds.length) {
    return { ready: false, reason: "A source passage is pinned more than once. Unpin the duplicate before drafting." };
  }
  return { ready: true, firstIds, secondIds };
}
