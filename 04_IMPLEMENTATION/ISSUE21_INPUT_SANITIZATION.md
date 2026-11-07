# Issue #21 — Input validation and sanitization

Implements SEC-003 on top of main commit `d8977e6`.

## Behaviour

Every free-text field a user submits is reduced to plain text before it is
stored: markup is removed, control characters are dropped, surrounding
whitespace is trimmed, and length is bounded.

Covered fields:

| Serializer | Fields | Bound |
|---|---|---|
| `WorkspaceSerializer` | `name`, `description` | 100 / 5000 |
| `ProjectSerializer` | `name`, `description` | 100 / 5000 |
| `TaskSerializer` | `title`, `description` | 150 / 5000 |
| `SprintCreateSerializer` | `name` | 100 |
| `TimeEntrySerializer` | `note` | 1000 |
| `TaskCommentSerializer` | `body` | 5000 |

Rules:

- `<script>alert(1)</script>` is stored as `alert(1)`; `<img src=x onerror=…>`
  is stored as an empty value and therefore rejected on a required field.
- Input that is nothing but markup is a 400, not a silently blank record.
- Plain text is never entity-escaped. `R&D` stays `R&D`, and re-saving a value
  does not change it again.
- `&lt;script&gt;` cannot decode back into live markup.
- NUL is rejected with a 400 by DRF before it can reach PostgreSQL, which
  would otherwise raise and surface as a 500.
- Tab, newline and carriage return survive; other C0 control characters do not.

Passwords and tokens are deliberately **not** sanitized — `RegisterSerializer`
and `LoginSerializer` do not use the mixin, because a credential is not
display text and must reach the view byte for byte.

## Design

`backend/common/validators.py` holds the whole control:

- `sanitize_text(value)` — the cleaning function.
- `SanitizedTextMixin` — opt-in serializer mixin that sanitizes every field
  that is an exact `serializers.CharField`.

The mixin works per serializer rather than per field so a free-text field
added later is covered without anyone remembering to opt in, and so each
field's `max_length` keeps living on the model. The exact-type check means
`EmailField`, `ChoiceField` and `SlugField` keep their own formats.

`bleach.clean` escapes whatever it keeps, so `R&D` would come back as
`R&amp;D` and gain another layer on every save. `sanitize_text` unescapes
after cleaning to undo that, and repeats until the value stops changing so
that `&lt;script&gt;` cannot decode into markup that never gets cleaned.

The three `description` fields were unbounded `TextField`s and are now capped
at 5000 characters (migrations `accounts/0004`, `projects/0007`). The cap is a
Django-level validator; the PostgreSQL column is unchanged.

`TaskCommentSerializer.validate_body` previously carried its own `bleach`
call. It now uses the shared mixin, which also fixes the entity-escaping bug
there — a comment reading `Tom & Jerry` was being stored as `Tom &amp; Jerry`.

## Tests

`backend/common/test_sanitization.py`, 11 tests:

```
cd backend && ./.venv/bin/python manage.py test --settings=config.test_settings
```

260 backend tests pass. The React suite (`cd frontend && npm test`) is
unchanged at 29.

## Notes

React escapes on render and the frontend uses no `dangerouslySetInnerHTML`, so
output encoding was already the first line of defence. This change makes the
stored data plain text as well, so a future consumer that is not React — a
report export, an email — does not inherit a stored-XSS problem.
