# Examples

| File | What it shows |
|---|---|
| `quickstart.ipynb` | The SDK cell by cell against a real Hub: browse, compose, pre-flight, resolve what blocks, execute, retry, wallets, budget, snapshots, and what the SDK sent. Paid sources show their cost before anything is sent; nothing is paid without the `PAY` switch. |
| `openai_chat.py` | The reference app from the design doc: an OpenAI chat with SyftHub as retrieval. Pre-flight, skip what cannot be sent, hand a top-up back to the user with a saved plan, resume after payment, compose from the numbered context. |
| `openai_chat_sync.py` | The same app on the sync twin, `syfthub.Hub`, with no `await`. |
| `profile_hub.py` | Where the time goes: times every request the SDK sends, split into connection setup, wait for the server and body read, and every SDK operation into time on the wire versus time in this process. Prints a Markdown report per operation, per route and per source, with a verdict: Hub, Spaces, network or client. |

All of them read `SYFTHUB_TOKEN`, a personal access token from your SyftHub profile, and
`SYFTHUB_URL` to point at another Hub. The chat apps also use the `openai` package with
`OPENAI_API_KEY` when it is installed, and print the retrieved context otherwise.

```bash
python examples/openai_chat.py "adverse events in phase 3" erin/trials carol/papers
python examples/openai_chat.py resume job-1          # after the invoice is paid
python examples/profile_hub.py --repeat 3 --out profile.md   # add --http2 to compare
```
