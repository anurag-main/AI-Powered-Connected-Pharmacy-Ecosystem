"""Phone number normalisation for Indian mobile numbers.

WHY THIS EXISTS (M6.1)
----------------------
``customers.phone`` is UNIQUE and is the natural key for find-or-create. That
guarantee is only as good as the string handed to it. Before this module the
``/confirm`` endpoint accepted ``customer_phone`` as a plain ``str | None`` with
no validation at all, so all of these created FOUR different customer rows for
one person:

    "9876543210"   "+91 9876543210"   "09876543210"   "98765-43210"

The LLM prompt in ``billing_prompts.py`` already asks for digits-only output,
but that only covers the spoken-order path. Anything typed into the billing form
went straight through.

THE FUTURE REASON IT MATTERS MORE
---------------------------------
M6.2+ will send WhatsApp messages to this column. A phone number that is merely
"probably fine" is not good enough once it addresses a real message: a wrong
number does not bounce, it reaches a stranger, and that stranger receives an
unsolicited message about medicine. So M6.1 fixes the contract now, while the
only consequence of a bad number is a duplicate row.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
Not a full E.164 library. The pharmacy is Indian, its customers are Indian, and
pulling in ``phonenumbers`` to validate a ten-digit local mobile would be a
dependency earning its keep on one code path. If the product ever sells outside
India this becomes the seam where that library goes.
"""

from __future__ import annotations

import re

# Indian mobile numbers are 10 digits and start with 6, 7, 8 or 9. Landlines and
# service numbers start lower and cannot receive WhatsApp, so they are rejected
# rather than stored as an address no message can ever reach.
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")


class InvalidPhoneNumberError(ValueError):
    """Raised when a supplied phone number cannot be a real Indian mobile."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(
            f"{raw!r} is not a valid 10-digit Indian mobile number. "
            f"Enter 10 digits starting with 6-9, or leave the field empty."
        )


def normalize_indian_mobile(raw: str | None) -> str | None:
    """Return a canonical 10-digit mobile number, or ``None`` for blank input.

    Accepts the shapes a pharmacist actually types or a customer actually
    recites, and reduces them to one canonical form::

        "+91 98765-43210"  -> "9876543210"
        "09876543210"      -> "9876543210"
        "919876543210"     -> "9876543210"
        "  "               -> None
        None               -> None

    Raises ``InvalidPhoneNumberError`` for anything that survives cleaning but is
    not a plausible mobile number.

    Note the asymmetry, which is the important design choice: **blank is fine,
    wrong is not.** A sale with no phone is an ordinary walk-in. A sale with a
    malformed phone is a future message to the wrong person, so it is refused at
    the boundary while the pharmacist is still standing there to correct it.
    """
    if raw is None:
        return None

    # A genuinely empty field means "not given". Only whitespace counts as empty:
    # anything the pharmacist actually typed was an attempt at a phone number and
    # deserves an error rather than being silently discarded.
    if not raw.strip():
        return None

    # Strip everything that is not a digit: spaces, dashes, brackets, the "+".
    digits = re.sub(r"\D", "", raw)
    if not digits:
        # Characters were typed but none were digits ("abcdefghij", "----").
        # Returning None here would throw the input away and record the sale as a
        # walk-in, so the pharmacist would never learn the number did not save.
        raise InvalidPhoneNumberError(raw)

    # "+91 98765 43210" and "919876543210" both arrive here as 12 digits.
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    # Some POS habits prefix a trunk "0".
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if not _INDIAN_MOBILE.match(digits):
        raise InvalidPhoneNumberError(raw)

    return digits


def is_valid_indian_mobile(raw: str | None) -> bool:
    """Non-raising companion, for read paths that only need a yes/no.

    Used by the consent layer to answer "could we actually message this
    customer?" without turning a report into an exception.
    """
    try:
        return normalize_indian_mobile(raw) is not None
    except InvalidPhoneNumberError:
        return False
