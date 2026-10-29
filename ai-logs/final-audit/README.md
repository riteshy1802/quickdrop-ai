# Sanitized live-evaluation model interaction evidence

These files record actual configured Nova Pro calls during all 24 original scenarios.
Each *-llm.json contains application-supplied text, effective timestamp, bounded
history/context, prompt version/hash, provider/model, wrapper elapsed time and the
validated structured model output or failure class. No canned model answers were
used. Cancelled calls are retained; upstream synchronous SDK work may outlive wrapper
cancellation. Hidden model reasoning, credentials, cookies and session tokens are not
recorded. *-traces.json contains the chronological public assignment trace API output.

These are evaluation interactions, NOT exports of the assistant development sessions
required by SUBMISSION.md. Those raw development-session exports remain missing and
are explicitly recorded as a submission defect. Do not claim these sanitized audit
artifacts satisfy that separate requirement.
