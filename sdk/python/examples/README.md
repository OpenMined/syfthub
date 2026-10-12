# Examples

| File | What it shows |
|---|---|
| `quickstart.ipynb` | The SDK cell by cell, offline: browse, compose, pre-flight, top up, execute, rejections and retry, budget, snapshots, and which hosts the requests went to. Runs on `syfthub.testing.FakeHub`; swap the first cell for a real `syfthub.Hub(token=...)`. |
| `openai_chat.py` | The reference app from the design doc: an OpenAI chat with SyftHub as retrieval. Pre-flight, skip what cannot be sent, hand a top-up back to the user with a saved plan, resume after payment, compose from the numbered context. |
| `openai_chat_sync.py` | The same app on the sync twin, `syfthub.Hub`, with no `await`. |

Both read `SYFTHUB_TOKEN` (and `SYFTHUB_URL` to point at another Hub) and, if installed, use the
`openai` package with `OPENAI_API_KEY`. Without `openai` they print the retrieved context instead.

```bash
python examples/openai_chat.py "adverse events in phase 3" erin/trials carol/papers
python examples/openai_chat.py resume job-1          # after the invoice is paid
```

To try the flow without a Hub, wire the app to `syfthub.testing.FakeHub` the way
`tests/unit/test_testing.py` does.
