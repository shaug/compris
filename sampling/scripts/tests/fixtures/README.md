# Review executor preservation fixture

These files were recorded from the pre-migration review executor at
`232c187ddcffabf4659405772a624f23f41d7e3c`.

`review-request.json` supplies the protocol request. A temporary executable
named `stub-claude` reads stdin and prints `review-envelope.json`; the
unmodified `review-suite/scripts/evals/claude_executor.py --claude-bin <stub>`
produced `review-response.json`, including its trailing newline.

The regression test executes the migrated command with the same fixed input and
compares stdout byte-for-byte. The envelope includes two model identities,
uncached and cached input tokens, output tokens, and cost, so stripping the
headless envelope down to result text cannot satisfy the fixture.
