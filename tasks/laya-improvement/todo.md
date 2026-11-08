# Tasks

- [x] Inspect configured checkpoint, original export and baseline tests.
- [x] Validate data and isolate training, selection and calibration.
- [x] Build and audit versioned scenario curriculum and disjoint splits.
- [x] Train and reload a candidate on the local GPU.
- [x] Independent adversarial agent review and fresh challenge evaluation.
- [x] Fix command-rule bypasses and expand native tool/context training coverage.
- [x] Train candidate 02 and evaluate on a new blind confirmation set.
- [x] Fix required code findings, run final tests, record measured gains and limitations.

Outcome: predeclared aggregate synthetic targets met. Independent final audit
verified both artifacts and all 160 policy decisions. Candidate is retained for
evaluation, not activated: adequate handling is unchanged and three new direct
false allows remain. See results.md and review.md. Production promotion and a
new human-labeled operational holdout remain future work, not claimed completed.

## Fortsättning: data och viktredigering (2026-11-08)

Kontrakt: [weight-space-spec.md](weight-space-spec.md). Varje task är en separat
fokuserad leverans. S = 1–2, M = 3–5 sannolika käll-/testfiler; experimentartefakter
ligger därutöver under `comparisons/laya-weight-space/`. Iterationer får egna id:n.
Taskstatus ska spegla faktisk evidens, inte att ett skript har skrivits.

### WS-00 — Dokumentera experimentstart [S]

- [x] Granska lokal träning, checkpoint-format, utvärdering och tidigare resultat.
- [x] Skriv hypoteser, fyrgrensjämförelse, datagränser och beroendeordnad arbetskö.
- Verifiering: kontrollera länkar, befintliga kodreferenser och fokuserad testbas.
- Beroenden: inga. Filer: denna fil, `plan.md`, `weight-space-spec.md` (M totalt).
- Underlag: repository `3a15e195711aa3deb7abcb8edb2c5927eecdd991`; tidigare
  modellresultat i `results.md` är historiska, inte nya körningar.
- Verifierat 2026-11-08: 25 befintliga tester passerade (3,47 s) med kommandot
  i specifikationen. Lokala Markdown-länkar, task-id WS-00–WS-12 och
  `git diff --check` kontrollerade. Ingen träning eller viktredigering utförd.

### WS-01 — Lås bas och verifiera Astra-körväg [M]

- [x] Inventera checkpoint/config/tokenizer, installerade paket och GPU-resurser;
  välj B och registrera hash samt känd ärvd träningshistorik.
- [x] Verifiera exakt Astra-modell och lokal verktygskörning med en ofarlig
  tensorprobe; registrera budget/körväg. En annan modell blir ett annat experiment.
- [x] Spara ett manifest med tydligt pending-status för saknade förutsättningar.
- Verifiering: upprepad inventering ger samma identiteter; kontrollera att
  basmodell och aktiv konfiguration inte ändrats. Ingen betald körning utan budget.
- Beroenden: WS-00. Filer: `experiments/laya_weight_space/preflight.py`,
  `tests/unit/test_weight_space_preflight.py`, experimentets `README.md`.
- Verifierat 2026-11-08: `ws01-preflight-01` och `ws01-preflight-02` under
  `comparisons/laya-weight-space/` har status complete och identiska bas-,
  kandidat-, konfigurations- och träningsfilidentiteter. Andra körningen använder
  slutversionen av inventeringsverktyget. Alla före/efter-kontroller passerade.
- B är den konfigurerade `20261012T163824Z`, med vikthash
  `d0eb0bf614119ed803d3690fd26926642954baa8d993a55ee97830f13b66033d`.
  Basens ursprungliga export och kandidat 02:s tre partitioner matchar metadata;
  kandidatens föräldrahashar matchar B. Okänd förträning förblir okänd.
- Aktuell Codex-turn anger `gpt-6-astra`, reasoning `high`. CPU och CUDA gav
  `[[5.0], [11.0]]` på påhittade tensorer. GPU: RTX 3090, 24 576 MiB totalt,
  cirka 17 280 MiB ledigt vid proben. Ingen slutsats om full träningskapacitet.
- Budget/körväg: befintlig agentsession och lokala verktyg; noll nya API-anrop,
  tak 0 USD för nya API-anrop. Codex-sessionens kostnad är inte uppmätt.
- Slutlig verifiering: 11 nya tester; hela sviten **306 passed** (42,82 s) med
  localhost-/GPU-åtkomst; `uv build` skapade sdist och wheel. Första fulla körningen
  i sandlådan hade 15 socket-relaterade fel; dessa passerade utanför sandlådan.
  Offline-bygget saknade hatchling i cache; vanligt bygge hämtade byggberoendet
  och passerade. Inga testkrav sänktes. Befintlig träning-smoke använde temporär
  testcheckpoint; inga B/D/W/DW-experiment eller produktionsändringar genomfördes.
- Nästa task: WS-02. WS-01 bekräftar lokal körväg; det nya sluttestets isolering
  och protokollet är fortfarande kommande arbete.

### WS-02 — Lås utvärderingskontraktet [M]

- [x] Definiera B/D/W/DW-identiteter, gruppindelning, budgeträkning, fasta
  policyparametrar och pilotgränsen före mätning.
- [x] Implementera parade regressionsmått för alla fall och rule-PASS; håll
  semantisk ablation separat och använd oberoende accepterade routingbeslut.
- [x] Frys replay-kontext och fullständiga falljoinar; verkliga fall med saknad
  kontext får inte rekonstrueras som om de vore fångade händelser.
- Verifiering: fixture med bättre genomsnitt men ett nytt osäkert ALLOW måste
  misslyckas mot pilotgränsen; ändrad policy/hash och saknade fall avvisas.
- Beroenden: WS-01. Filer: experimentets `protocol.py`, `evaluate.py`,
  `tests/unit/test_weight_space_evaluate.py`, experimentets `README.md`.
- Verifierat 2026-11-08: protokollet finns i
  `comparisons/laya-weight-space/ws02-protocol-01/protocol.json`, identitet
  `872ab384bf7ef3d59af38747c060b90a8590bc867a64852c4726955f7134ed58`.
  Bas och effektiv konfiguration jämfördes med WS-01 före/efter frysning.
- `protocol.py` låser budgetdefinition, B:s identitet, B/D/W/DW:s föräldrar,
  kalibreringsmetod, gruppregler, frågor, policy och utvärderingskod. Framtida
  kandidatidentiteter och verkliga partitioner står uttryckligen som väntande.
  Den existerande replay-valideringen fick en återanvändbar ingång med config
  i `src/lgh/eval/backend_contract.py`; Laya/Kev-gränssnittet behåller sitt beteende.
- `evaluate.py` jämför kompletta sparade prediktioner med regler + reducer,
  och redovisar all/rule-PASS/rule-controlled samt separat semantic-only.
  B→D, B→W, D→DW och B→DW innehåller parade fall-id:n och explicita nämnare.
  Valfri B_operational kontrollerar originalkalibreringen. Inga handlingar,
  reviewers, regelsökningar eller sessionstillståndsövergångar körs.
- CLI-smoke i `comparisons/laya-weight-space/ws02-smoke-01/`: fyra syntetiska
  fall med deterministiska etiketter och förutbestämda svar. B→D förbättrar
  osäkra ALLOW 2→1 men skapar ett nytt (`case-2`), och underkänns. Detta är
  verifiering av utvärderingskoden, inte resultat för verkliga Laya-modeller.
- 28 nya tester. Fokuserad verifiering: **61 passed**; full regression med
  localhost-/GPU-åtkomst: **334 passed** (43,04 s). `uv build --offline`,
  dokumentlänkar och `git diff --check` passerade.
- Gränser: WS-02 definierar budgeträkning; verktygsräknaren kommer i WS-06.
  Modellidentiteter i sparade prediktioner är insamlarens deklarationer tills
  WS-05–WS-10 verifierar inferensinsamlingen. Data-/överlappsaudit kommer i WS-04,
  nytt sluttest och gruppbaserad osäkerhet i WS-11. Rapporter från denna task
  ger därför aldrig ett aktiveringsbeslut, även när den observerade gränsen passeras.
- Nästa task: WS-03, granskade kontrastfamiljer för överskrivningsfel.

### WS-03 — Bygg ett granskningsbart underlag för överskrivningsfel [M]

- [x] Ta fram kontrastfamiljer för nytt/befintligt/osparat innehåll, uttryckligt
  uppdrag, diffgranskning och återställning, med riktiga verktygsformat.
- [x] Korrigera kända etikettproblem i en ny datasetversion; behörighet får inte
  i sig avgöra återställbarhet. Dokumentera varje etikett och dess källa.
- [x] Visa exakt modellinput för granskaren; exkludera otillräcklig kontext och
  redovisa täckning över alla sju frågor och klasser.
- Verifiering: granska kontrastpar utan modellutfall; kontrollera schema, källa,
  motiveringar och klassstöd mot insamlingsmålen i specifikationen.
- Beroenden: WS-02. Filer: experimentets `curriculum.py`, `build_dataset.py`,
  `tests/unit/test_weight_space_data.py`, `data-review.md`.
- Verifierat 2026-11-08: `comparisons/laya-weight-space/ws03-pool-02/` innehåller
  72 frontier-märkta syntetiska exempel i 36 kontrastfamiljer; sex exempel
  uteslutna utan etiketter. Alla sju frågor och klasser har stöd. 504 faktiska
  frågesekvenser ryms utan kapning, högst 186 av 1 024 token. Basens identitet
  matchar före/efter. Ingen inferens eller modellträning i databyggandet.
- Självgranskning och begränsningar i
  [data-review.md](../../experiments/laya_weight_space/data-review.md).
  Mänsklig/oberoende granskning återstår; poolen är ännu opartitionerad.
  13 nya tester täcker bland annat bortfall, källa, etiketter och dubbletter.
- Slutkontroll: **347 passed** (49,01 s), `uv build --offline`, artefakt- och
  källkodshashar samt `git diff --check` passerade. Fullsvitens befintliga
  träning-smoke använde en tillfällig checkpoint; det är inget D-försök.

### WS-04 — Separera data och förbered ett nytt sluttest [M]

- [x] Utöka poolen med minst 39 ytterligare kontrastfamiljer och stärk svaga
  klasser; nå minst 75 användbara familjer efter audit för målen 30/15/15/15.
- [x] Skapa train/development/validation/calibration med grupper som hålls ihop;
  auditera mot ärvda dataset och kända historiska tester.
- [ ] Förbered nya mänskligt märkta verkliga testfall och separat syntetiskt
  underlag hos en granskare utanför optimerarens kontext. Spara replay-sidecar.
- [ ] Verifiera åtkomstisolering och manifest; saknade mänskliga etiketter lämnar
  sluttestdelen öppen men hindrar inte utveckling på färdiga partitioner.
- Verifiering: injicerad trace-/state-/familje-/sessionsöverlapp upptäcks; kontrollera
  rättigheter från Astra-miljön och rapportera faktisk täckning och bortfall.
- Beroenden: WS-03. Filer: experimentets `partitions.py`, `build_dataset.py`,
  `tests/unit/test_weight_space_data.py`, `data-review.md`.
- Öppen utvecklingsdel verifierad 2026-11-08. `curriculum_ws04.py` tillför
  54 familjer; `ws04-pool-02` har 202 exempel/90 familjer och sex bortfall.
  Sju semantiska länkar ger 83 odelbara grupper. `ws04-partitions-03` fördelar
  dem 38/15/15/15 och exemplen 88/36/41/37. Alla klasser finns i varje partition;
  sex träningsklasser har fortfarande färre än tio exempel och varnas uttryckligen.
- Tio historiska filer, 2 406 rader, granskade utan exakt trace-/state-/gruppöverlapp.
  Okänd förträning, saknade historiska sessions-id:n och semantisk osäkerhet kvarstår.
  Kompletta syntetiska replay-sidecars är fångade och validerade; inga handlingar körda.
- Användaren har bekräftat att användaren märker framtida verkliga sluttestfall.
  Ingen isolerad miljö finns. Läsproben kunde läsa validation/calibration;
  manifestet är därför `open_development_only`, `blind_evaluation_ready: false`.
  Insamlingskontrakt och tom mänsklig märkningsmall är skapade; noll sluttestfall
  finns ännu. De två sluttest-/isoleringspunkterna ovan förblir öppna.
- 15 nya tester i `tests/unit/test_weight_space_partitions.py`:
  transitiva gruppgränser, alla identitetsöverlappar, historik, reproducerbarhet,
  klassstöd, filintegritet, replay och ärlig åtkomststatus. Fokuserat **28 passed**;
  hela sviten **362 passed** (45,26 s). `uv build --offline`, hashkontroller,
  dokumentlänkar och `git diff --check` passerade. Bas och fryst protokoll matchar.
- Nästa möjliga modelltask: WS-05 som öppet B/D-utvecklingsförsök enligt
  specifikationens uttryckliga väg när isolering saknas. Inga blinda testanspråk.

### Kontrollpunkt A — Data och protokoll

- [x] Identiteter, budget och utvecklingspartitioner klara; testansvar och isolering
  dokumenterade. Redovisa väntande mänsklig märkning separat.
- [x] WS-01–WS-04:s kontroller för öppna utvecklingsförsök passerar innan modellförsök.
- [ ] Nytt sluttest och faktisk åtkomstisolering klara innan blind slututvärdering.

### WS-05 — Kör referens och förbättrad vanlig finjustering [M]

- [ ] Kör B och D från samma låsta bas med befintlig träningsloop och explicit
  validation/calibration; välj vikter endast med validation.
- [ ] Spara inställningar, data-/vikthash, seed, historik, kostnad och development-
  resultat. D blir den låsta utgångspunkten för DW.
- [ ] Kontrollera komplett sju-frågorsinferens efter omladdning och redovisa
  regressioner även om medelresultatet förbättras.
- Verifiering: befintliga träningstester samt verklig GPU-körning och omladdning;
  behåll alla misslyckade körningar i journalen. Sluttestet förblir stängt.
- Beroenden: WS-04:s utvecklingsdata, kontrollpunkt A. Filer: experimentets
  `run_training.py`, `README.md`, `tasks/laya-improvement/weight-space-results.md`.

### WS-06 — Ge Astra en minimal vikt- och aktiveringsprobe [M]

- [ ] Inspektera namngivna tensorer och utvalda aktiveringar; koppla prober till
  utvecklingsfall och avlägsna hooks efter varje körning.
- [ ] Returnera prediktioner för sju frågor, feltyper och relevanta sammanfattningar;
  begränsa output så att hela vikter/privata traces inte dumpas i prompten.
- [ ] Räkna alla modellkörningar, även prober, och avvisa anrop över sökbudgeten.
- Verifiering: små fixtures testar budget, felvägar och hook-städning; verklig
  smoke bekräftar att enbart observation inte ändrar prediktioner/vikter.
- Beroenden: WS-01, WS-02, WS-04:s utvecklingsdata. Filer: experimentets
  `probe.py`, `budget.py`, `tests/unit/test_weight_space_probe.py`, `README.md`.

### WS-07 — Skapa reversibla och verifierbara viktpatchar [M]

- [ ] Läs basen skrivskyddat; tillämpa bara deklarerade tensorändringar i en kopia
  och spara bas-/patch-/resultathash, ändringsantal och normer.
- [ ] Avvisa fel bas, NaN/Inf, formfel, otillåtna tensorer och befintlig målmapp.
- [ ] En sparad kandidat kan laddas; återgång återställer basens tensorer exakt.
- Verifiering: negativa tester med små tensorer; verklig nollpatch bevarar
  modelloutput inom deklarerad numerisk tolerans. Originalets hash är oförändrad.
- Beroenden: WS-01, WS-02. Filer: experimentets `patch.py`,
  `tests/unit/test_weight_space_patch.py`, `README.md`.

### Kontrollpunkt B — Verktygen fungerar på en verklig modell

- [ ] B/D-artefakter och probe-/patch-smoke verifierade; testdata otillgängliga.
- [ ] Öppna verktygsfel åtgärdade innan Astra får föreslå riktiga viktändringar.

### WS-08 — Pröva riktad viktredigering på B [M]

- [ ] Kör W med högst 10 patchförslag inom protokollets utvärderingsbudget;
  spara exakt Astra-identitet, instruktioner, verktygslogg och varje hypotes.
- [ ] Börja i beslutsparametrarna. Utöka till namngivna encoder-delar endast om
  prober motiverar det; ingen gradientträning i W.
- [ ] Välj finalist på development, verifiera en gång på validation och registrera
  även inga förbättringar som resultat. Ändra inte efter testfeedback.
- Verifiering: återskapa finalist från bas + patch och jämför prediktioner/hash;
  granska ändringsomfång, feltyper och faktisk budgetförbrukning.
- Beroenden: kontrollpunkt B, tillgänglig Astra-körväg. Filer: experimentets
  `astra-session.md`, `run_edit.py`, `weight-space-results.md` under tasks.

### WS-09 — Kontrollera den föreslagna mekanismen [M]

- [ ] Jämför patch, återställd bas och norm-/omfångsmatchade kontrolländringar på
  development utan att låta kontrolländringar bli nya sökkandidater.
- [ ] Pröva nya formuleringar och kontraster samt övriga riskklasser; skilj
  beteendeeffekt från enbart ändrad säkerhet i sannolikheterna.
- [ ] Redovisa om mekanismen stöds, motsägs eller är oklar. Ett negativt resultat
  får stoppa redigeringsspåret med dokumenterat skäl.
- Verifiering: reproducerbar ablationsrapport med grupper, antal och alla kontroller;
  separat redovisad kontrollbudget låst före kontrollerna, inga sluttestanrop.
- Beroenden: WS-08. Filer: experimentets `controls.py`,
  `tests/unit/test_weight_space_controls.py`, taskfilen `weight-space-results.md`.

### WS-10 — Pröva kombinationen och kalibrera finalisterna [M]

- [ ] Kör DW från låsta D med samma sökbudget som W; ingen återanvändning av
  validation som interaktiv feedback. Redovisa ärvd kunskap från W-sessionen.
- [ ] Frys B/D/W/DW-vikter och kalibrera alla med samma separata data/metod;
  spara även ursprunglig B-kalibrering som operativ referens.
- [ ] Lås slutmanifestet och bevara negativa grenar; kalla en utebliven DW-körning
  utebliven om WS-09 stoppade redigeringsspåret.
- Verifiering: kalibrering ändrar inga vikter; ingen calibration/test-rad har
  använts i sökning; omladdade finalister ger kompletta sannolikhetsfördelningar.
- Beroenden: WS-05, WS-09. Filer: experimentets `run_edit.py`, `calibrate.py`,
  `tests/unit/test_weight_space_calibrate.py`, taskfilen `weight-space-results.md`.

### Kontrollpunkt C — Frysning före sluttest

- [ ] Kandidater, kalibrering, regler, budgetlogg och utvärderingskod hash-låsta.
- [ ] Mänskligt märkt nytt test och full replay-kontext färdiga; inga kända
  läckor. Om underlaget saknas väntar WS-11, utan att syntetiska fall ersätter det.

### WS-11 — Kör och rapportera det orörda sluttestet [M]

- [ ] Kör samtliga finalister på identiska fall med fryst routing och spara
  fullständiga prediktioner samt parade förbättringar/regressioner.
- [ ] Rapportera B→D, B→W, D→DW och B→DW, kalibreringskontrollen, klassstöd,
  gruppbaserad osäkerhet, kostnad och syntetiska/verkliga resultat separat.
- [ ] Utvärdera pilotgränsen utan efterhandsjustering. Vid ny modelliteration
  blir detta test utvecklingsevidens och en ny bekräftelsemängd krävs.
- Verifiering: slutmanifestet matchar kontrollpunkt C; rapporten omfattar varje
  fall och återberäknade routingbeslut stämmer med sparade prediktioner.
- Beroenden: kontrollpunkt C. Filer: experimentets `evaluate.py`, `report.py`,
  `tests/unit/test_weight_space_evaluate.py`, taskfilen `weight-space-results.md`.

### WS-12 — Granska slutsats och formulera nästa beslut [S]

- [ ] Granska varje nytt osäkert ALLOW, datakällor, läckage och påstådd mekanism;
  skilj mätresultat från hypoteser och begränsningar.
- [ ] Dokumentera fortsätt data / fortsätt mekanism / föreslå shadow-försök /
  otillräcklig evidens med länkar till reproducerbara artefakter.
- [ ] Uppdatera taskstatus med faktisk evidens; eventuell aktivering beskrivs
  som ett separat efterföljande arbete.
- Verifiering: slutrapporten går att följa från kriterium till enskilda fall;
  ändrade kodvägar har relevanta tester och slutlig regressionstestning är gjord.
- Beroenden: WS-11, eller dokumenterad avbruten experimentgren. Filer:
  `tasks/laya-improvement/weight-space-results.md`, denna tasklista.
