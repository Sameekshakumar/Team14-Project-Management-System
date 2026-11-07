"""
SEC-003: the one place user-submitted free text is cleaned before storage.

Serializers opt in with `SanitizedTextMixin` rather than this running
globally, because a few CharFields — passwords, tokens — must reach the
view byte for byte.
"""
import html

import bleach
from rest_framework import serializers

#: Upper bound for a free-text body. Matches TaskComment.body, which was the
#: first bounded text field in the project.
MAX_TEXT = 5000

# Tab, newline and carriage return are the only C0 controls worth keeping;
# the rest only serve to hide content from whoever reads it back.
_ALLOWED_CONTROLS = "\t\n\r"


def strip_markup(value):
    """
    Return `value` as plain text with any HTML or script markup removed.

    `bleach.clean` escapes whatever it keeps, so "R&D" comes back as
    "R&amp;D" and gains another layer on every save. Unescaping afterwards
    restores the plain text, but a single pass would let "&lt;script&gt;"
    decode into live markup that never gets cleaned. Repeating until the
    value stops changing gives plain text with no such second chance.
    """
    for _ in range(5):
        cleaned = bleach.clean(
            value, tags=[], attributes={}, strip=True, strip_comments=True
        )
        unescaped = html.unescape(cleaned)
        if unescaped == value:
            return value
        value = unescaped
    # Pathological nesting: stop unescaping and keep the escaped form, which
    # is inert even though it is ugly.
    return bleach.clean(value, tags=[], attributes={}, strip=True, strip_comments=True)


def sanitize_text(value):
    """Plain text with markup, control characters and edge whitespace gone."""
    # DRF's CharField already rejects NUL before this runs; stripping it here
    # covers the callers that sanitize a string outside a serializer.
    value = "".join(c for c in value if c >= " " or c in _ALLOWED_CONTROLS)
    return strip_markup(value).strip()


class SanitizedTextMixin:
    """
    Sanitizes every plain-text field the serializer accepts.

    Applied per serializer rather than per field so that a free-text field
    added later is covered without anyone remembering to opt in, and so the
    model keeps owning each field's max_length.
    """

    #: Field names whose input must survive untouched.
    sanitize_exempt = ()

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        errors = {}
        for name, value in validated.items():
            field = self.fields.get(name)
            # Exact type only: EmailField, ChoiceField and SlugField are
            # CharField subclasses with their own formats to preserve.
            if not isinstance(value, str) or type(field) is not serializers.CharField:
                continue
            if name in self.sanitize_exempt:
                continue
            cleaned = sanitize_text(value)
            if not cleaned and not field.allow_blank:
                # Input that was nothing but markup reaches here non-empty and
                # would otherwise be stored blank.
                errors[name] = ["This field may not be blank."]
            validated[name] = cleaned
        if errors:
            raise serializers.ValidationError(errors)
        return validated
