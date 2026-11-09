# Laya weight-space experiment

Experimentets [specifikation](../../tasks/laya-improvement/weight-space-spec.md),
[plan](../../tasks/laya-improvement/plan.md) och
[tasklista](../../tasks/laya-improvement/todo.md) beskriver B/D/W/DW-jämförelsen.
Här finns WS-01:s inventering, WS-02:s frysta protokoll och utvärdering,
WS-03:s kontrastdata, WS-04:s utökning, överlappsaudit och partitionering samt
WS-05:s lokala B/D-träning och parade utvecklingsjämförelse.

## Kör WS-01

Från projektroten, i den befintliga Pythonmiljön:

```bash
.venv/bin/python -m experiments.laya_weight_space.preflight \
  --output comparisons/laya-weight-space/ws01-next \
  --base-training comparisons/20261017-prepared/original-training-export.jsonl \
  --reference-checkpoint comparisons/laya-v2/candidate-02
```

Välj en ny outputmapp för varje körning. Bas B läses från projektets effektiva
LGH-konfiguration; ett Hub-id utan lokala checkpointfiler accepteras inte och
ingen modell laddas ned. `--base-training` pekar på den äldre basens fullständiga
export, vars hash måste matcha metadata. Kandidat 02 inventeras som historisk
referens och dess deklarerade föräldrahashar kontrolleras mot B.

`manifest.json` innehåller:

- Hashar för samtliga checkpointfiler, inklusive tokenizer, encoder och rapport.
- Basens träningsmetadata och kontroll av tillgängliga train/validation/calibration-
  exporter. Okänd förträning och äldre återanvändning av validation för kalibrering
  redovisas som begränsningar, inte som verifierad oberoende historik.
- Effektiv konfigurationshash och filhashar före/efter, paketversioner,
  källkodshashar och GPU-avläsning. Konfigurerad modell skiljs från aktiv daemon;
  verktyget gör inga nätverksanrop till daemonen.
- Modell-id, reasoning-inställning och turn-id ur aktuell Codex-sessions
  `turn_context`, bunden till `CODEX_THREAD_ID`. Samtalsinnehåll, API-nycklar och
  autentiseringsfiler kopieras inte. Inställningen i `config.toml` räcker inte som
  belägg. Utanför en identifierbar Astra-session blir denna kontroll pending.
- En deterministisk matrisberäkning med fyra påhittade vikter på CPU och CUDA.
  Förväntat resultat är `[[5.0], [11.0]]`. Inga Laya-vikter laddas eller ändras.

Exitkod 0 betyder att **WS-01-kontrollerna** är kompletta. Exitkod 2 betyder
pending och orsaker finns i manifestet, exempelvis saknad CUDA-/Astra-åtkomst
eller exporthash som inte matchar. Ogiltiga checkpointfiler eller befintlig
outputmapp ger ett fel utan att skriva över tidigare resultat.

I Codex-sandlådan kan NVIDIA-åtkomst vara spärrad även när GPU:n fungerar.
Körningen behöver då tillåten GPU-åtkomst; verktyget byter inte tyst till CPU
och rapporterar framgång för CUDA. Det läser checkpointfiler men ändrar inte
deras filrättigheter. Hashkontroll är detektion av förändringar, inte åtkomstisolering.

## Astra-körväg och budget

Den första verifierade vägen är den befintliga Codex-sessionen med lokala verktyg.
WS-01 gör noll nya API-anrop, har ett tak på 0 USD för nya API-anrop och kör en
toy-probe per inventering. Kostnaden för själva Codex-sessionen är okänd här;
det betyder inte att modellåtkomsten är gratis. Inga W/DW-sökningar startas.

OpenAI anger modellidentifieraren `gpt-6-astra` och stöd för verktyg i
[modelldokumentationen](https://developers.openai.com/api/docs/models/gpt-6-astra).
Det fastställer inte kontots API-behörighet. Den lokala sessionsloggen ger
belägg för vald modell i just denna körning, inte en låst serverrevision.
Proben använder [PyTorch 2.14:s matrisoperationer](https://docs.pytorch.org/docs/2.14/generated/torch.mm.html).

## Verifiering

```bash
.venv/bin/python -m pytest tests/unit/test_weight_space_preflight.py -q
USE_TF=0 OMP_NUM_THREADS=4 .venv/bin/python -m pytest -q
```

Den fullständiga sviten kräver localhost-sockets och kan även köra befintlig
träning-smoke på en tillfällig checkpoint. Det är en regressionstest, inte en
B/D/W/DW-körning. Vid upprepad inventering ska basens identitet och effektiva
konfigurationshash matcha; tidsstämplar och ledigt GPU-minne får variera.

WS-01 låser inte i sig protokoll eller data. `experiment_ready` är därför
alltid false i WS-01-manifestet, även när preflight-status är complete.
WS-02 har senare låst protokollet; data och sluttest kräver fortfarande WS-04.

## Verifierad start 2026-11-08

Två lokala inventeringar finns i
`comparisons/laya-weight-space/ws01-preflight-01/manifest.json` och
`comparisons/laya-weight-space/ws01-preflight-02/manifest.json` (git-ignorerade).
Den senare innehåller slutversionens källkodshashar. Bas, kandidat, konfiguration,
träningsfilhashar och sessionsidentitet matchar mellan körningarna.

Vald bas är den konfigurerade `20261012T163824Z`, eftersom alla grenar ska börja
från samma kända utgångsläge. Kandidat 02 inventeras som historisk jämförelse,
inte som ny bas. Basens sammanlagda filidentitet är
`2f10784de17807f85cc9f02622039fad8f2fc15e9e2f294259f673a9b26c831a` och vikthashen är
`d0eb0bf614119ed803d3690fd26926642954baa8d993a55ee97830f13b66033d`.

Lokal miljö: Laya 0.3.4, PyTorch 2.14.0, Transformers 5.17.0, safetensors 0.8.0;
RTX 3090 med 24 GB VRAM. Aktuell Codex-turn registrerar `gpt-6-astra`/`high`.
CPU- och CUDA-prober passerade. Paketbygge och samtliga 306 tester passerade;
11 tester gäller preflight. Full evidens och begränsningar finns i tasklistan.

## WS-02: frys protokoll och utvärdera sparade svar

Protokollet låser B:s vikthash, grenarnas föräldrarelationer, frågor och
optionordning, effektiv konfiguration, inbyggda regler, utvärderingskod,
sökbudget och kriterier. D/W/DW:s framtida checkpointidentiteter anges som
väntande; de finns ännu inte. Verktyget kontrollerar att bas och konfiguration
fortfarande matchar WS-01 innan protokollet skrivs.

```bash
.venv/bin/python -m experiments.laya_weight_space.protocol freeze \
  --preflight comparisons/laya-weight-space/ws01-preflight-02/manifest.json \
  --output comparisons/laya-weight-space/ws02-protocol-next
```

Varje outputmapp måste vara ny. Protokollets `sha256` är dess identitet.
Ändrad kod, frågor eller policy kräver ett nytt protokoll och nya bundna
artefakter. Ändra inte den gamla filen eller dess hash för att få en körning
att fortsätta. Källkod kan behöva utvecklas i senare tasks; frys då en ny
protokollversion före nästa försök och behåll den tidigare körningens artefakter.

WS-02 definierar budgeträkningen: W och DW har var sin budget om 10 patchförslag,
20 utvecklingsutvärderingar, högst 64 fall per anrop och 1 280 fallexponeringar.
Upprepade fall räknas igen, aktiveringsprober räknas och ett fall omfattar sju
frågor. En validation-körning tillåts per fryst finalist. Själva verktygsräknaren
implementeras i WS-06; WS-02 gör inga modellkörningar och förbrukar ingen sökbudget.

### Indata och fångad replay-kontext

Datasetet använder befintligt LGH-exportformat med `trace_id`, `timestamp`,
`state`, de sju `questions`, `labels` och `source`. Dessutom krävs ett icke-tomt
`group_id` och `provenance.kind` (`synthetic` eller `operational`). Den fångade
sidofilen använder befintligt `ReplayCase`: komplett `envelope`, `rules`,
`rule_config_sha256`, `session` med räknare och en oberoende `reference` med
`source`, `requires_intervention`, `acceptable` och `forbidden`.

Trace-id måste koppla varje fall exakt en gång. Envelope ska reproducera den
sparade modellinputen och regelhashen ska matcha protokollet. Saknad historik
rekonstrueras inte. Ingen rad får tappas under frysning, inklusive rader som
tidigare markerats som otillräcklig kontext: gör exkluderingarna före frysning.
Verkliga fall kräver mänskliga referenser för både modellfrågor och handling.
Syntetiska och verkliga fall hålls i separata paket. Session/familj/kontrastpar
sparas för WS-04:s partitionering och WS-11:s gruppbaserade osäkerhet.

Exempel med de sparade, deterministiska smoke-fallen från WS-02:

```bash
.venv/bin/python -m experiments.laya_weight_space.protocol inputs \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --dataset comparisons/laya-weight-space/ws02-smoke-01/data.jsonl \
  --replay comparisons/laya-weight-space/ws02-smoke-01/replay.jsonl \
  --purpose synthetic_smoke \
  --output comparisons/laya-weight-space/ws02-smoke-next/frozen
```

Paketet innehåller kopior av `protocol.json`, `dataset.jsonl`, `replay.jsonl`
och en hashbunden `binding.json`. `purpose` får vara `synthetic_smoke` eller
`development`. Sluttestkörning och rekommendation om aktivering ingår inte här.
Exempelartefakterna ovan är lokala och git-ignorerade; testerna återskapar samma
kontrollfall utan att behöva dessa filer.

### Prediktionsformat, version 1

Prediktionsfilen är ett JSON-objekt med följande fält:

| Fält | Innehåll |
|---|---|
| `version` | `1` |
| `protocol_sha256` | Identiteten i paketets `protocol.json` |
| `inputs_sha256` | Identiteten i paketets `binding.json` |
| `models` | Identiteter för exakt B/D/W/DW, valfritt även B_operational |
| `predictions` | Samma grennamn; varje värde är en lista med `trace_id` och `answers` |

Varje modellidentitet har `weights_sha256`, `checkpoint_sha256`,
`parent_weights_sha256`, `calibration` och `calibration_dataset_sha256`.
Föräldern är null för B; B:s vikthash för D/W; D:s vikthash för DW.
B:s vikter måste matcha protokollet. `checkpoint_sha256` är den samlade
filidentiteten från WS-01:s `checkpoint_snapshot`, inte bara vikthashen.

Utvecklingskörningar kräver `calibration: shared_holdout` och samma explicita
kalibreringsdatasethash i alla fyra grenar. Smoke använder `synthetic_fixture`
och null datasethash. B_operational bevarar den ursprungliga checkpointidentiteten,
har `calibration: original` och null datasethash. Den ger en separat kontroll
av omkalibreringens effekt. Om kontrollen saknas anges det i rapporten.

`answers` är de fullständiga sju Laya-svaren, med `type`, `noul` respektive
`choice` och normaliserade `probabilities`. Saknade/extra alternativ, NaN/Inf,
inkonsekventa val och ofullständiga eller dubbla fall avvisas. Ordningen på
prediktionsrader får variera; kopplingen görs alltid på trace-id.

Identiteterna i denna fil deklareras av insamlaren. WS-02 validerar format,
relationer och referenser men bevisar inte att svaren producerats av vikterna.
Verifierad inferensinsamling tillkommer i WS-05–WS-10; inga modellvinster eller
oberoende testresultat får hävdas utifrån ett godkänt prediktionsformat.

```bash
.venv/bin/python -m experiments.laya_weight_space.evaluate \
  --bundle comparisons/laya-weight-space/ws02-smoke-01/frozen \
  --predictions comparisons/laya-weight-space/ws02-smoke-01/predictions.json \
  --output comparisons/laya-weight-space/ws02-smoke-01/report-next
```

### Rapportens betydelse

`report.json` har modellmått och parade jämförelser B→D, B→W, D→DW och B→DW.
`routing.json` innehåller varje beslut och referens; `manifest.json` binder
resultatfilernas hashvärden. Samtliga fall, rule-PASS och regelstyrda fall
redovisas var för sig. `semantic_only` tvingar PASS och är en separat ablation.

Kontrollen kräver färre osäkra ALLOW, inga nya sådana fall, ingen ökning av
otillräcklig hantering och ingen ökning av säkra avbrott. Noll stöd för säkra
eller interventionskrävande fall ger inte godkänt resultat. Parade fall-id:n
visar både förbättringar och regressioner; genomsnitt kan inte dölja dem.
En ökning av otillräcklig hantering mäts mot accepterade routingbeslut, inte
bara mot om kandidaten valde något annat än ALLOW.

Besluten kommer från de fångade reglerna och produktionsreducern. Inga regler
matchas om mot dagens filsystem, inga handlingar utförs, inga sessionstillstånd
ändras och ingen reviewer anropas. Detta är inte slutliga fullständiga
pipelinebeslut efter verifiering, anti-loop-räknare och mänskligt godkännande.

`observed_gate.passes` beskriver enbart de observerade fallen.
`selection.status` är alltid `not_evaluated_for_promotion` i denna task.
Sluttest, härkomst-/överlappsaudit, gruppbaserad osäkerhet och verifierad
modellinsamling krävs fortfarande innan slutsatser om faktisk förbättring.

### WS-02:s verifierade smoke

`comparisons/laya-weight-space/ws02-protocol-01/protocol.json` är fryst mot B
från WS-01. Körningen i `ws02-smoke-01/` innehåller fyra syntetiska fall med
deterministiska etiketter och förutbestämda svar. I B→D minskar osäkra ALLOW
2→1 men ett nytt fall (`case-2`) tillkommer: kontrollen underkänner kandidaten.
En annan fixture förbättrar samtliga riskfall utan nya regressioner och passerar
den observerade kontrollen; rapporten ger fortfarande inget aktiveringsbeslut.

```bash
.venv/bin/python -m pytest tests/unit/test_weight_space_evaluate.py \
  tests/unit/test_backend_contract.py tests/unit/test_backend_replay.py -q
```

## WS-03: bygg och granska kontrastpoolen

```bash
USE_TF=0 .venv/bin/python -m experiments.laya_weight_space.build_dataset \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --output comparisons/laya-weight-space/ws03-pool-next

.venv/bin/python -m pytest tests/unit/test_weight_space_data.py -q
```

Ange en ny outputmapp. Verktyget använder den lokala checkpointens tokenizer
och den installerade Laya 0.3.4:s sekvensbyggare. Det laddar inga vikter och
kör inga av datasetets handlingar. Basidentiteten kontrolleras före och efter.
För en annan Laya-version måste sekvensbyggarens kontrakt granskas först.

Exporten innehåller `pool.jsonl`, ursprungliga `envelopes.jsonl`, exakta
frågesekvenser i `model-inputs.jsonl`, `review.md`, bortfall i `excluded.jsonl`
och ett hashbundet `manifest.json`. Envelopes innehåller ännu inte fångade
regelutfall och kan därför inte användas som färdig WS-02-replay-sidecar.
Alla etiketter har `source: frontier` och syntetisk proveniens. Författarens
självgranskning hålls uttryckligen skild från oberoende/mänsklig granskning.

Den verifierade exporten `ws03-pool-02` omfattar 72 exempel i 36 familjer,
sex uteslutna exempel och 504 frågesekvenser utan kapning. Längsta sekvensen
är 186 token. Alla klasser förekommer men vissa har lågt stöd. Poolen är
opartitionerad; minst 39 ytterligare familjer behövs för målet 75 innan
WS-04:s gruppindelning och överlappsaudit. Se [datagranskningen](data-review.md)
för fullständig täckning, etikettbeslut och kvarstående begränsningar.

Verifiering: 13 nya datatester, **347 passerade tester** i hela sviten,
`uv build --offline`, fil-/källkodshashar och `git diff --check`. Fullsvitens
befintliga träningstest använder en tillfällig checkpoint och utgör inte D-grenen.

## WS-04: utöka och partitionera

```bash
USE_TF=0 .venv/bin/python -m experiments.laya_weight_space.build_dataset \
  --curriculum ws04 \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --output comparisons/laya-weight-space/ws04-pool-next

.venv/bin/python -m experiments.laya_weight_space.partitions \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --pool comparisons/laya-weight-space/ws04-pool-next \
  --output comparisons/laya-weight-space/ws04-partitions-next
```

Båda outputmapparna måste vara nya. Byggaren behåller WS-03:s författaridentitet
för äldre familjer och registrerar den nya för de 54 tillkommande familjerna.
Partitioneringen kräver matchande fil-/källkodshashar från poolmanifestet;
bygg om till en ny mapp om källkod har ändrats. Alla tio deklarerade historiska
exporter måste finnas. Saknade filer innebär ett fel, inte tyst överhoppad audit.

Grupper binds transitivt genom session/familj/kontrastpar och explicit granskade
semantiska länkar. Exakta trace-/state-/gruppöverlapp avvisas, även mot ärvd
historia. Likhetskontrollen för måltexter är ett komplement med gräns 0,65;
den bevisar inte semantiskt oberoende. Historiska nära träffar binds till
development och nya inbördes träffar kräver explicit gruppering före export.

Varje partition får `dataset.jsonl` och `replay.jsonl`, med regelutfall från
fryst konfiguration. Envelopes valideras mot modellindata. Inga handlingar
exekveras och ingen inferens sker. `manifest.json` binder filer, historia,
klassstöd, regler, gruppantal, källkod och faktisk åtkomststatus.

Slutliga lokala artefakter är `ws04-pool-02` och `ws04-partitions-03`:
202 exempel, 90 författade familjer och 83 odelbara grupper. Train/development/
validation/calibration har 88/36/41/37 exempel och 38/15/15/15 grupper.
Alla klasser stöds i varje partition, men små träningsklasser varnas fortfarande.

Status är **open_development_only**. Läsproben kan läsa validation/calibration,
och användaren bekräftar att isolerad miljö saknas. Samma författare har sett
hela curriculum. Separata filer ska därför inte beskrivas som blinda data.
Nästa B/D-försök kan vara ett öppet utvecklingsförsök enligt specifikationen.

Användaren ansvarar för framtida mänsklig märkning. `test-intake.json` anger
insamlingsmålet och `human-label-template.json` är en tom mall med frågor,
etikettfält, motiveringar och handlingsreferens. Den är inte ett dataset och
innehåller inga mänskliga etiketter. Nya verkliga fall och en separat oberoende
syntetisk slututmaning förblir väntande tills insamling och åtkomstgräns finns.
Spara inte framtida sluttestinnehåll i aktuell agents läsbara arbetsyta eller chatt.

```bash
.venv/bin/python -m pytest tests/unit/test_weight_space_partitions.py \
  tests/unit/test_weight_space_data.py -q
```

Verifierat: 28 fokuserade tester, **362 tester** i hela sviten, offline-paketbygge,
artefakt-/källkodshashar och oförändrat WS-02-protokoll. Full täckning och
begränsningar finns i [datagranskningen](data-review.md).

## WS-05: vanlig finjustering och jämförbar B/D-inferens

```bash
USE_TF=0 OMP_NUM_THREADS=4 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m experiments.laya_weight_space.run_training \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --partitions comparisons/laya-weight-space/ws04-partitions-03 \
  --output comparisons/laya-weight-space/ws05-training-next
```

Kräver befintlig Astra-session och CUDA-åtkomst. Ingen modell laddas ned.
CLI använder befintliga `TrainSettings`: fyra epoker, encoder-lärhastighet
1e-5, head-lärhastighet 1e-4, ackumulering över åtta fall, patience 1 och seed 0.
En körning deklarerar ett träningsförsök före inferens i `plan.json`; bästa
validation-förlust väljer vikterna, inklusive epok noll som möjlig vinnare.
Inställningar anpassas inte efter development-utfallet. Seed och paketversioner
registreras; bitidentisk CUDA-reproduktion är inte utlovad.

Den befintliga träningsloopen tränar encoder och beslutskomponenter med fryst
act-head. `runner.py` använder explicit validation/calibration och sparar D i
en ny mapp. Kalibreringen använder `fit_bucket_temperatures` på samma 37 fall
för B och D: temperaturer per frågetyp/optionsantal, rutnät 0,05–5,00, minsta
log loss. B kopieras byte för byte och endast temperaturkonfigurationen ändras.
Den aktiva modellens ursprungliga checkpoint och LGH-konfiguration bevaras.

Efter omladdning samlas samtliga sju svar för varje development-fall:

- **B/D:** samma separata kalibreringsdata och metod, olika frysta vikter.
- **B_operational:** ursprungliga B-vikter och temperaturer.
- **B_unit_temperature/D_unit_temperature:** diagnostiska kontroller med alla
  använda Laya-temperaturer satta till 1 i minnet; kontrollens override anges
  uttryckligen i identiteten. LGH:s extra normalisering är fryst i protokollet.

`predictions.json`, `routing.json` och `report.json` bevarar svar, identiteter,
klassmått och parade förbättringar/regressioner för all/rule-PASS/rule-controlled
och semantic-only. B→D och kalibreringskontroller använder WS-02:s befintliga
mått och reducer. Formatet är ett WS-05-utvecklingsresultat, inte WS-02:s
fyrgrensformat: inga påhittade W/DW-prediktioner skapas. Rapporten väljer aldrig
en modell för aktivering. Uppgifter om verklig exekvering eller reviewers saknas.

`journal.jsonl` registrerar framsteg och fel; `failure.json` bevarar ett avbrutet
försök. Befintliga outputmappar avvisas. Det avslutande manifestet binder
samtliga filer och pekar ut D:s låsta checkpoint för framtida DW. D:s interna
`report.json` innehåller träningshistorik och validation-mått; använd den yttre
rapporten för jämförbar B/D-kalibrering och utvecklingsresultat.

```bash
USE_TF=0 OMP_NUM_THREADS=4 .venv/bin/python -m pytest \
  tests/unit/test_weight_space_training.py tests/unit/test_train_partitions.py \
  tests/unit/test_train_loop.py -q
```

Se [WS-05-resultatet](../../tasks/laya-improvement/weight-space-results.md) för
den faktiska körningen, regressionerna och begränsningarna. Nästa steg är WS-06,
vikt-/aktiveringsprobe med budgeträkning; sluttestet väntar fortsatt på nya fall
som användaren märker och på faktisk åtkomstisolering.

## WS-06: budget och observationsprobe

`budget.py` håller en persistent, hashförseglad logg per gren/försök. Hela
anropet reserveras före inferens: högst 20 anrop, 64 fall per anrop och 1 280
fallexponeringar; samma fall räknas igen vid upprepning. Patchförslag har en
separat gräns på 10. Misslyckade anrop återbetalas inte. Avbrutna processer med
en kvarvarande `running`-reservation stoppar fortsatt körning för utredning.
Fyll aldrig i en ny tom logg för att fortsätta samma försök.

En separat fillåsfil och atomisk ersättning skyddar uppdateringar mellan
processer. Loggen är lokal bokföring, inte en säkerhetsgräns mot en användare
som kan skriva om både logg och hash. `tool_smoke` finns för fixtures; den
verkliga utvecklingssmoken debiterar **W:s ordinarie sökbudget**.

`probe.run_probe` tar en laddad eval-modell och redan validerade, kompletta
train/development-fall med replay-referenser. Anroparen ansvarar för bindningen
till checkpoint och tillåten partition; `smoke.py` visar den verifierade vägen.
Proben returnerar samtliga sju svar, fel per fråga, fryst reducerbeslut och
feltyperna osäkert ALLOW, otillräcklig hantering och säkert avbrott. Ingen
regelmatchning eller inspelad handling körs.

Välj högst åtta exakta tensorer och fyra namngivna moduler med tensoroutput,
exempelvis `scorer.3.weight`, `scorer.3.bias`, `type_emb` och `scorer.3`.
Rapporten innehåller form, datatyp, antal, min/max, medel, standardavvikelse och
L2-norm; inga fulla tensorer, states eller envelopes. Aktiveringar kopplas till
fall-id. Hela modellens tensorer/buffertar jämförs med bitbaserad hash före/efter.
Hooks returnerar inget och avlägsnas i `finally`, även vid fel.

Varje fall kör alla sju frågor i ett forward-anrop. En pre-hook journalför
försöket, frågebatchens storlek och enhet före beräkning, även om forward sedan
misslyckas. Interna återförsök avvisas före en andra forward; ett nytt försök
kräver en ny budgetreservation. Endast inference-körningar genom dessa verktyg
räknas automatiskt; WS-08/10 måste använda samma väg och logg för samtliga prober.

## WS-07: exakta och reversibla viktpatchar

`patch.py` läser originalet utan att skriva till det. Ersättningar levereras som
en safetensors-fil med exakta tensornamn och fullständiga nya tensorvärden.
Basens fulla checkpointidentitet, en uttrycklig tillåtelselista och en hypotes
krävs. Första sökområdet är `type_emb.*`, `head.*` och `scorer.*`.
Encoder-tensorer kräver dessutom dokumenterad probe-evidens; temperatur och
act-head kan inte ändras med detta verktyg.

```bash
.venv/bin/python -m experiments.laya_weight_space.patch apply \
  --base /path/to/frozen-checkpoint \
  --expected-base-sha256 FULL_CHECKPOINT_SHA256 \
  --replacements /path/to/replacements.safetensors \
  --allow-tensor scorer.3.bias --hypothesis 'Declared hypothesis' \
  --output comparisons/laya-weight-space/new-patch

.venv/bin/python -m experiments.laya_weight_space.patch restore \
  --base /path/to/frozen-checkpoint \
  --patch-directory comparisons/laya-weight-space/new-patch \
  --output comparisons/laya-weight-space/new-restoration
```

Verktyget avvisar befintlig målmapp, mål inne i basen, checkpointsymlänkar,
fel bas, okända/otillåtna tensorer, ändrade former/datatyper samt NaN/Inf.
`checkpoint/`, `replacements.safetensors` och ett förseglat manifest sparas i
den nya patchmappen. Manifestet binder bas, payload, resultat, källkod, antal
ändrade parametrar och normer. Bitförändringar inklusive `+0.0`→`-0.0` räknas.
En nollpatch bevarar originalets filbytes. Safetensors verifieras vid skrivning;
full Laya-omladdning verifieras separat i smoken. Fel efter att mappen skapats
bevaras som ett misslyckat försök.

Återställning skapar en ny byte-identisk kopia av den verifierade basen och
kontrollerar även kandidat/payload. Ingen flyttalssubtraktion används och ingen
befintlig kandidat skrivs över. Verktyget registrerar inte sökförslag automatiskt:
WS-08/10 måste reservera varje förslag med `Budget.proposal` före patchförsöket.

## Gemensam verklig smoke för WS-06/07

```bash
USE_TF=0 OMP_NUM_THREADS=4 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m experiments.laya_weight_space.smoke \
  --protocol comparisons/laya-weight-space/ws02-protocol-01/protocol.json \
  --partitions comparisons/laya-weight-space/ws04-partitions-03 \
  --output comparisons/laya-weight-space/ws06-ws07-smoke-next \
  --budget comparisons/laya-weight-space/ws06-w-search-budget.json
```

Kräver verifierad Astra-session och lokal CUDA. Läser bara development-dataset
och replay, inte validation/calibration/test. De första två development-fallen
väljs före inferens; `--cases` kan väljas uttryckligen inom protokollets gräns.
Layas laddare kan skriva tokenizerkonfiguration, därför laddas alltid en
separat kopia och både filbytes och laddade tensorer verifieras.

Fem körningar jämförs med fördeklarerad absolut tolerans **0**: före hooks,
med hooks, efter hooks, omladdad nollpatch och omladdad återställning. Bas och
aktiv konfiguration kontrolleras före/efter. Plan, svar, budgetsnapshot,
felrapport vid misslyckande och filmanifest bevaras. Den levande budgetloggen
ligger utanför manifestets frysta fillista; rapportens snapshot är oföränderlig.
En ny outputmapp är inte en ny sökbudget: fortsätt med `--budget`.

```bash
OMP_NUM_THREADS=4 .venv/bin/python -m pytest \
  tests/unit/test_weight_space_probe.py tests/unit/test_weight_space_patch.py -q
```

PyTorch-hookarnas observations- och borttagningskontrakt kontrollerades via
Context7 mot [PyTorch Module](https://github.com/pytorch/pytorch/blob/main/torch/nn/modules/module.py)
och [eval/inference-dokumentationen](https://github.com/pytorch/pytorch/blob/main/docs/source/notes/autograd.md).
Inga nya beroenden eller produktionskodvägar infördes.
