"""Contact verification rules: Indian mobile format and the hard acceptance bar."""
import re

PLACEHOLDERS = {"9876543210", "9123456789", "9000000000", "8888888888", "7777777777",
                "9012345678", "9898989898", "1234567890"}


def normalize_mobile(raw) -> str | None:
    """Return a 10-digit Indian mobile (starts 6-9) or None for anything else."""
    if not raw:
        return None
    s = str(raw).strip()
    if re.match(r"^\s*(\+?91[\s-]*)?1[89]00", s) or s.replace(" ", "").startswith(("1800", "1860")):
        return None
    d = re.sub(r"\D", "", s)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    elif len(d) == 13 and d.startswith("091"):
        d = d[3:]
    if len(d) != 10 or d[0] not in "6789":
        return None
    if len(set(d)) <= 2 or d in PLACEHOLDERS:
        return None
    return d


def accept_check(*, is_indian: bool, phone: str | None, source_url: str | None,
                 phone_shared_with_other_store: bool, suppressed: bool,
                 duplicate_domain: bool) -> tuple[bool, str | None]:
    """Hard bar from the plan (section 3). Order = most specific reason first."""
    if duplicate_domain:
        return False, "duplicate"
    if not is_indian:
        return False, "not_india"
    if not phone:
        return False, "no_mobile"
    if not source_url:
        return False, "no_source_url"
    if suppressed:
        return False, "suppressed"
    if phone_shared_with_other_store:
        return False, "shared_number"
    return True, None
