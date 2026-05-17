"""Merge scraped Perfect Game results into the local schedule."""

import re


def normalize_opponent(name):
    """Strip record strings like (3-0-0) from opponent names."""
    if not name:
        return ""
    return re.sub(r"\s*\(\d+-\d+(?:-\d+)?\)", "", name).strip()


def game_key(game):
    """Identity key for matching games across fetches."""
    return (
        (game.get("Date") or "").strip(),
        normalize_opponent(game.get("Opponent") or "").lower(),
    )


def _is_placeholder_opponent(name):
    return normalize_opponent(name or "").lower() in {"", "unknown", "tbd"}


def _placeholder_match_key(game):
    return (
        (game.get("Date") or "").strip(),
        (game.get("Time") or "").strip().lower(),
        (game.get("Location") or "").strip().lower(),
    )


def _apply_fresh_game(old, fresh):
    updated = dict(old)
    changed_fields = []

    for field in ("Time", "Location", "Opponent"):
        if (fresh.get(field) or "").strip() != (old.get(field) or "").strip():
            updated[field] = fresh.get(field)
            changed_fields.append(field)

    if fresh.get("Type") == "Past":
        updated["Type"] = "Past"
        updated["Score/Result"] = fresh.get("Score/Result", "N/A")
        updated["Time"] = "N/A"
        changed_fields.append("Result")

    return updated, changed_fields


def merge_into_schedule(existing, scraped):
    """
    Merge freshly scraped games into the existing schedule.

    Past games are locked. Upcoming games may update time, location, opponent,
    or promote to Past when a score appears. Placeholder opponents such as
    Unknown are replaced by a later named opponent when date/time/location match.
    """
    existing_by_key = {game_key(g): g for g in existing}
    scraped_by_key = {game_key(g): g for g in scraped}
    scraped_placeholder_matches = {
        _placeholder_match_key(g): (key, g)
        for key, g in scraped_by_key.items()
        if not _is_placeholder_opponent(g.get("Opponent"))
    }
    matched_scraped_keys = set()

    merged = []
    changed_entries = []

    for key, old in existing_by_key.items():
        if old.get("Type") == "Past":
            merged.append(old)
            continue

        placeholder_match = None
        if key not in scraped_by_key and _is_placeholder_opponent(old.get("Opponent")):
            placeholder_match = scraped_placeholder_matches.get(_placeholder_match_key(old))

        if key not in scraped_by_key and not placeholder_match:
            merged.append(old)
            continue

        fresh_key, fresh = placeholder_match if placeholder_match else (key, scraped_by_key[key])
        if placeholder_match and fresh_key in existing_by_key:
            continue
        matched_scraped_keys.add(fresh_key)

        updated, changed_fields = _apply_fresh_game(old, fresh)
        if changed_fields:
            changed_entries.append({"old": old, "new": updated, "fields": changed_fields})
        merged.append(updated)

    new_entries = []
    for key, fresh in scraped_by_key.items():
        if key not in existing_by_key and key not in matched_scraped_keys:
            merged.append(fresh)
            new_entries.append(fresh)

    merged.sort(key=lambda g: (0 if g.get("Type") == "Past" else 1, g.get("Date", "")))
    return merged, new_entries, changed_entries
