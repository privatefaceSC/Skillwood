import unicodedata
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.7


def normalize(s: str) -> str:
    """Привести имя отправителя к канонической форме для сравнения.

    Lowercase, strip, удаление символов кроме букв и цифр (включая emoji).
    """
    s = s.lower().strip()
    return ''.join(
        ch for ch in s
        if unicodedata.category(ch).startswith(('L', 'N'))
    )


def similarity_score(a_norm: str, b_norm: str) -> float:
    """Сходство двух уже нормализованных строк, [0.0, 1.0]."""
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def suggest_merges_for_handle(db, new_handle) -> int:
    """Создать MergeSuggestion(pending) для каждого существующего handle того же
    user_id с другим contact_id и similarity_score ≥ MATCH_THRESHOLD.

    Возвращает количество созданных предложений.
    """
    from .contacts import MergeSuggestion, MessengerHandle

    candidates = (
        db.query(MessengerHandle)
        .filter(
            MessengerHandle.user_id == new_handle.user_id,
            MessengerHandle.contact_id != new_handle.contact_id,
            MessengerHandle.id != new_handle.id,
        )
        .all()
    )

    created = 0
    for cand in candidates:
        score = similarity_score(new_handle.sender_normalized, cand.sender_normalized)
        if score < MATCH_THRESHOLD:
            continue
        exists = (
            db.query(MergeSuggestion)
            .filter(
                MergeSuggestion.source_handle_id == new_handle.id,
                MergeSuggestion.target_contact_id == cand.contact_id,
            )
            .first()
        )
        if exists:
            continue
        db.add(MergeSuggestion(
            user_id=new_handle.user_id,
            source_handle_id=new_handle.id,
            target_contact_id=cand.contact_id,
            score=score,
            status="pending",
        ))
        created += 1

    if created:
        db.commit()
    return created
