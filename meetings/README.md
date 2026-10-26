# Generation publication and review safety

The normal creation flow reserves a draft ID, generates provider output, and
inserts its actions under a fresh generation token before inserting the draft.
An unfinished action set is therefore not a visible, reviewable draft. Revision
similarly stages a new action set while the prior generation remains visible,
then conditionally replaces the draft's token, notes and summary only if its
revision-requested status and expected generation still match. A losing request
cannot full-save an older decision, replace the winner's actions or resurrect a
deleted draft.

Display, review, review recovery and legacy task conversion select actions using
the published token. Review and revision forms submit that token, and review
decisions condition on it. Blank or missing historical tokens remain supported.
The durable review intent and unfinished marker still control approval recovery;
task confirmation and conversion share the same recorded accepted descriptions.
Later mutable item text or acceptance flags do not replace approved intent.

Cleanup deletes only the failing attempt's unpublished action generation. It
never deletes a visible draft. When a final write acknowledgement is uncertain,
a positively observed published generation is retained; an unconfirmed outcome
also retains its data and tells the officer to reload before retrying. Older
generations and uncertain unpublished stages may remain stored but are not
selected for display or conversion. There is no automatic background cleanup or
multi-document transaction guarantee.

The Django admin registration is view-only, including action inlines. Decisions
and content changes use the officer workflows rather than bypassing publication
and review through direct admin form saves. Provider summarization and audio
transcription implementations are unchanged by these guards.
