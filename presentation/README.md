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

## Jämförelsen med Kev-4B

Direkt efter "Träffsäkerhet är inte säkerhet" visas samma fem klasser för grundmodell,
finjusterad Laya och Kev-4B, följt av modellernas hanteringsförslag och HTTP-svarstid.
Alla använder samma 266 mänskligt etiketterade valideringsfall från träningsrapporten.
Originalexportens SHA-256 matchar checkpointens metadata; fallurval, kontrollsummor
och klassantal finns i `comparisons/slide28-validation/manifest.json`.

De gamla tracesen saknar fullständiga historiska envelopes, regelkonfigurationer,
sessionsräknare och oberoende referenser för slutbeslut. Därför mäter denna körning
bara modellernas svar. Den kör varken regler, policy, granskare eller kommandon.
`handling.intervention` jämför förslag som skiljer sig från `allow` med de mänskliga
hanteringsetiketterna; det är inte uppmätta avbrott i hela systemet.

Samla varje modell separat i en ny resultatkatalog med den frysta experimentfilen.
Starta först motsvarande isolerade server på porten i experimentfilen. Exempel:

```bash
.venv/bin/python -u -m lgh.eval.model_comparison \
  --dataset comparisons/slide28-validation/dataset.jsonl \
  --experiment comparisons/slide28-validation/experiment-models.json \
  --backend kev --output comparisons/slide28-validation/run-02/kev
```

Upprepa för `laya_current` och `laya_released` med respektive server och utdatamapp.
Ändra inte fall, etiketter, experimentfil eller evalueringskod mellan körningarna.
Kombinera färdiga pass och uppdatera sedan presentationsaggregatet:

```bash
.venv/bin/python -m lgh.eval.model_comparison \
  --runs comparisons/slide28-validation/run-02/laya_current \
         comparisons/slide28-validation/run-02/laya_released \
         comparisons/slide28-validation/run-02/kev \
  --output comparisons/slide28-validation/run-02/report
.venv/bin/python presentation/scripts/collect_backend_metrics.py \
  --report comparisons/slide28-validation/run-02/report/report.json \
  --validation-manifest comparisons/slide28-validation/manifest.json
```

`data/backend-comparison.json` innehåller bara aggregat och spårbarhet till rapporten
och valideringsurvalet med relativa sökvägar och SHA-256. Inga kommandon eller tillstånd kopieras. Det gör att bilderna fungerar
även när de lokala, git-ignorerade jämförelsefilerna saknas.

Varje modell körs tre gånger efter en separat uppvärmning på ett fall som inte ingår
i utvärderingen. Bara första genomgången används för kvalitet, så upprepningar
ökar inte antalet oberoende fall. Svarstiden på bilden är HTTP-medianen för första
genomgången, utan modellstart, granskning eller mänsklig väntetid. Alla råa mättider
och svar sparas lokalt. Etiketterna för första respektive upprepade genomgångar
bevisar inte cachemissar, cacheträffar eller kallstart.

Underlaget användes redan för Layas early stopping och temperaturanpassning.
Jämförelsen är därför explorativ och ger `inconclusive` för modellval. En oberoende
testmängd behövs före slutsatser om generalisering eller byte av aktiv modell.

Vid en ny rapport: kontrollera scenariernas och etiketternas ursprung, hårdvaran,
slutsatserna på båda bilderna och talarmanuset innan presentationen används igen.

`markdown-it` 14 är ett direkt beroende eftersom `@comark/markdown-it` (via Slidev) har det
som peer-beroende och annars får version 15, som inte exporterar filen den importerar.
