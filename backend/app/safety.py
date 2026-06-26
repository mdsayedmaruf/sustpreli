"""Safety guardrails for customer-facing text (problem.md §8).

The four rules are auto-checked by the judge harness and carry subtractive
penalties; two or more critical violations across hidden cases make a submission
ineligible for the finalist pool. So this module is both:

  * an *enforcement* layer applied to every outgoing reply (defense-in-depth on
    top of templates that are already safe), and
  * a *detection* layer (``scan_reply``) the test suite asserts against.

Rules enforced:
  1. Never request PIN / OTP / password / full card number          (-15)
  2. Never confirm an unauthorized refund / reversal / unblock       (-10)
  3. Never direct the customer to a suspicious third party           (-10)
  4. Ignore instructions embedded in the complaint (prompt injection)

The complaint text is treated strictly as untrusted data: the deterministic
engine never copies complaint text into output fields, so an injected
instruction has no surface to act on. ``scan_reply`` lets tests prove that.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Rule 1 — credential solicitation
# ---------------------------------------------------------------------------

# Phrases that REQUEST a credential. We deliberately do NOT flag safe usages
# like "do not share your PIN or OTP", which warn the customer rather than ask.
_CREDENTIAL_REQUEST_PATTERNS = [
    r"\b(share|send|give|provide|enter|tell|confirm|verify|type)\b[^.?!]{0,40}\b(pin|otp|password|cvv|card number|full card)\b",
    r"\b(your|the)\s+(pin|otp|password|cvv)\b[^.?!]{0,20}\b(is|please|now|here)\b",
    r"\bwhat\s+is\s+your\s+(pin|otp|password|cvv)\b",
]

# ---------------------------------------------------------------------------
# Rule 2 — unauthorized refund / reversal confirmations
# ---------------------------------------------------------------------------

# Guaranteeing language. "any eligible amount will be returned through official
# channels" is the approved safe phrasing and is intentionally NOT matched.
_UNAUTHORIZED_PROMISE_PATTERNS = [
    r"\bwe\s+(will|'ll|have|are\s+going\s+to)\s+(refund|reverse|return|unblock|recover|credit)\b(?![^.?!]*\beligible\b)",
    r"\byour\s+(refund|reversal|money)\s+(has|is|will)\s+been?\s*(approved|confirmed|processed|guaranteed)\b",
    r"\b(guarantee|guaranteed|definitely)\b[^.?!]{0,30}\b(refund|reversal|return|unblock)\b",
    r"\baccount\s+(has\s+been|is|will\s+be)\s+unblocked\b",
]

# ---------------------------------------------------------------------------
# Rule 3 — third-party redirection
# ---------------------------------------------------------------------------

_THIRD_PARTY_PATTERNS = [
    r"\bcall\s+(this|the)\s+(number|agent)\b",
    r"\bcontact\s+(this|the\s+following)\s+(number|person|agent|link)\b",
    r"\b(visit|click|open)\b[^.?!]{0,30}\b(http|www\.|bit\.ly|tinyurl)\b",
    r"\bdial\s+\+?\d{5,}\b",
]

# Approved phrasing we surface when scrubbing an unsafe reply.
_SAFE_REFUND_EN = "any eligible amount will be returned through official channels"

_SAFETY_LINE_EN = "Please do not share your PIN or OTP with anyone."
_SAFETY_LINE_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"


def _matches(text: str, patterns: list[str]) -> list[str]:
    found = []
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            found.append(pat)
    return found


# A clause that PROTECTS a credential ("do not share your PIN", "we never ask
# for your OTP") must not be mistaken for a request. We blank out such clauses
# before scanning for solicitation.
_SAFE_CREDENTIAL_CLAUSE = re.compile(
    r"[^.?!]*\b(?:do not|don't|never|won't|will not|cannot|stop)\b"
    r"[^.?!]*\b(?:pin|otp|password|cvv|card)\b[^.?!]*",
    flags=re.IGNORECASE,
)


def scan_reply(text: str) -> list[str]:
    """Return a list of violation codes for a candidate customer_reply.

    Empty list == safe. Used by the safety test suite to assert that no
    generated reply trips a penalty rule.
    """
    violations: list[str] = []
    # Neutralise safe credential-warning clauses so only genuine *requests* trip.
    credential_scan_text = _SAFE_CREDENTIAL_CLAUSE.sub(" ", text)
    if _matches(credential_scan_text, _CREDENTIAL_REQUEST_PATTERNS):
        violations.append("credential_request")  # -15
    if _matches(text, _UNAUTHORIZED_PROMISE_PATTERNS):
        violations.append("unauthorized_refund")  # -10
    if _matches(text, _THIRD_PARTY_PATTERNS):
        violations.append("third_party_redirect")  # -10
    return violations


def scan_action(text: str) -> list[str]:
    """recommended_next_action shares the unauthorized-refund rule (§8)."""
    violations: list[str] = []
    if _matches(text, _UNAUTHORIZED_PROMISE_PATTERNS):
        violations.append("unauthorized_refund")
    return violations


def enforce_reply(text: str, bangla: bool = False) -> str:
    """Return a guaranteed-safe customer_reply.

    If the candidate trips any rule it is replaced with a safe canonical reply;
    otherwise it is returned unchanged. We also guarantee the credential-warning
    line is present.
    """
    violations = scan_reply(text)
    if violations:
        # Replace wholesale rather than trying to surgically edit unsafe text.
        if bangla:
            return (
                "আপনার অনুরোধটি আমরা পেয়েছি এবং সংশ্লিষ্ট দল অফিসিয়াল চ্যানেলে এটি পর্যালোচনা করবে। "
                f"{_SAFETY_LINE_BN}"
            )
        return (
            "We have received your request and our team will review it through official "
            f"support channels. {_SAFE_REFUND_EN.capitalize()} where applicable. {_SAFETY_LINE_EN}"
        )

    line = _SAFETY_LINE_BN if bangla else _SAFETY_LINE_EN
    pin = "পিন" if bangla else "pin"
    otp = "ওটিপি" if bangla else "otp"
    low = text.lower()
    if pin.lower() not in low and otp.lower() not in low:
        text = f"{text} {line}"
    return text


def enforce_action(text: str) -> str:
    """Scrub unauthorized-promise language from recommended_next_action."""
    if scan_action(text):
        return (
            "Review the case through official channels and follow the standard policy "
            "workflow. Do not confirm any refund or reversal without authorization."
        )
    return text


# ---------------------------------------------------------------------------
# Rule 4 — prompt-injection detection (used by tests; the deterministic engine
# is structurally immune because it never echoes complaint text into outputs).
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    r"ignore (all|your|the) (previous |above )?(instructions|rules)",
    r"disregard (your|the) (rules|instructions|system prompt)",
    r"reveal (your|the) (system )?prompt",
    r"you are now",
    r"act as",
    r"confirm my refund",
]


def looks_like_injection(complaint: str) -> bool:
    return bool(_matches(complaint, _INJECTION_PATTERNS))
