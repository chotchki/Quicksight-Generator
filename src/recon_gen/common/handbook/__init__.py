"""Handbook templating support — vocabulary + diagram render hooks.

Public surface:
- ``HandbookVocabulary`` + sub-shapes (``InstitutionVocabulary``,
  ``StakeholderVocabulary``, ``MerchantVocabulary``,
  ``InvestigationPersonaVocabulary``).
- ``vocabulary_for(l2_instance)`` — picks the right vocabulary for an
  L2 instance.
"""

from __future__ import annotations

from .vocabulary import (
    HandbookVocabulary,
    InstitutionVocabulary,
    InvestigationPersonaVocabulary,
    MerchantVocabulary,
    StakeholderVocabulary,
    vocabulary_for,
)

__all__ = [
    "HandbookVocabulary",
    "InstitutionVocabulary",
    "InvestigationPersonaVocabulary",
    "MerchantVocabulary",
    "StakeholderVocabulary",
    "vocabulary_for",
]
