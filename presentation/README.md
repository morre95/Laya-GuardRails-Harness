# Presentation

Slidev-presentation av projektet (~30 min, svenska). Talarmanus finns i varje bilds
`<!-- -->`-kommentar och visas i presentatörsläget.

```bash
cd presentation
pnpm install
pnpm dev        # http://localhost:3030, presentatörsläge på /presenter
pnpm build      # statisk version i dist/
```

## Live-bilden

Bilden "Prova själva" frågar Laya-daemonen direkt. Dev-servern proxar `/laya/*` till
`http://127.0.0.1:8765` (ändra med `LGH_DAEMON_URL`), eftersom daemonen inte skickar
CORS-headers. Starta daemonen före presentationen:

```bash
USE_TF=0 uv run lgh daemon start --device cuda
```

Svarar daemonen inte, eller körs den statiska versionen från `pnpm build`, visar bilden
inspelade svar för de fyra förinställda kommandona. De märks då med "inspelat".
Frågorna läses från `src/lgh/laya/questions_v0_1.yaml`, alltså samma fil som LGH använder.

## Siffror

Alla siffror genereras. Inget skrivs in för hand. Kör från projektroten efter ny träning,
nya etiketter eller en ny `lgh compare`:

```bash
uv run python presentation/scripts/collect_metrics.py
USE_TF=0 uv run --extra laya python presentation/scripts/record_demo.py --device cuda
```

- `data/metrics.json`: aggregat från traces, `labels.jsonl`, träningsrapporten för
  modellen i `laya.model` och den senaste katalogen under `comparisons/`. Bara aggregat
  sparas, inga kommandon eller tillstånd.
- `data/recorded.json`: påhittade demotillstånd körda genom grund- och finjusterad modell,
  med uppmätt latens och tokenlayout. Reducerbeslutet förutsätter att ingen hård regel matchar.

Texten på bilden "Tillbaka till exemplet" tolkar `recorded.json`. Kontrollera den om
inspelningen görs om.
