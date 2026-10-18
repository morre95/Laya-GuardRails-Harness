# Presentation

Slidev-presentation av projektet (cirka 30 min, svenska). Talarmanus finns i varje bilds
`<!-- -->`-kommentar och visas i presentatörsläget.

```bash
cd presentation
pnpm install
pnpm dev        # http://localhost:3030, presentatörsläge på /#/presenter
pnpm build      # statisk version i dist/
```

## Live-demo

Bilden "Prova själva" frågar Laya-daemonen direkt. Dev-servern proxar `/laya/*` till
`http://127.0.0.1:8765` (ändra med `LGH_DAEMON_URL`), eftersom daemonen inte skickar
CORS-headers. Starta daemonen före presentationen:

```bash
USE_TF=0 uv run lgh daemon start --device cuda
```

Svarar daemonen inte, eller körs den statiska versionen från `pnpm build`, visar bilden
inspelade svar för de fyra förinställda kommandona, märkta "inspelat".

## Siffror

Inga siffror skrivs in för hand. Kör från projektroten efter ny träning, nya etiketter
eller en ny `lgh compare`:

```bash
uv run python presentation/scripts/collect_metrics.py
USE_TF=0 uv run --extra laya python presentation/scripts/record_demo.py --device cuda
```

- `data/metrics.json`: aggregat från traces, `labels.jsonl`, träningsrapporten för modellen
  i `laya.model` och den senaste `comparisons/*/report.json`. Bara aggregat sparas, inga
  kommandon eller tillstånd.
- `data/recorded.json`: fyra påhittade demofall. De körs genom grundmodellen och den
  finjusterade modellen (median av 5 körningar), genom projektets regler och policy, och
  genom en LLM via `claude -p` med samma sju frågor (`scripts/prompts/seven_questions.j2`).
  LLM-svaret streamas och ankomsttiden för varje textbit sparas, så kapplöpningsbilden
  spelar upp det i uppmätt takt. Med `--skip-llm` återanvänds den förra LLM-inspelningen.

Texten på bilderna "Träffsäkerhet är inte säkerhet" och "Tillbaka till exemplet" tolkar
siffrorna. Kontrollera den om datan genereras om.

`markdown-it` 14 är ett direkt beroende eftersom `@comark/markdown-it` (via Slidev) har det
som peer-beroende och annars får version 15, som inte exporterar filen den importerar.
