# WS-03: kontrastdata för överskrivningsfel

**Aktuellt:** WS-04:s utökning och partitionering finns längre ned. WS-03-siffrorna
beskriver den bevarade tidigare exporten, inte den senaste poolen.

Verifierat 2026-11-08. Underlaget innehåller **72 syntetiska exempel i 36
kontrastfamiljer**, med sex uteslutna exempel i tre ytterligare familjer.
Etiketterna är författade och självgranskade av Codex/GPT-6-Astra (`high`),
utan Laya-prediktioner. Oberoende och mänsklig granskning återstår. Familjerna
är författarenheter, inte 36 statistiskt oberoende verkliga observationer.

Slutlig export: [ws03-pool-02](../../comparisons/laya-weight-space/ws03-pool-02/manifest.json).
Den tidigare `ws03-pool-01` bevaras som mellanversion. Artefakterna är lokala
och git-ignorerade; curriculum och byggverktyg är reproducerbar källkod.
Ingen partitionering, modellinferens, träning, viktredigering eller exekvering
av exemplens handlingar ingår i databyggandet.

## Granskningsunderlag

- [pool.jsonl](../../comparisons/laya-weight-space/ws03-pool-02/pool.jsonl):
  sju etiketter per exempel, `source: frontier`, syntetiskt ursprung,
  familj/session/kontrast-id, etikettmotivering, evidens och etikethistorik.
- [review.md](../../comparisons/laya-weight-space/ws03-pool-02/review.md):
  varje exakt serialiserat modelltillstånd, etiketter och motiveringar.
- [model-inputs.jsonl](../../comparisons/laya-weight-space/ws03-pool-02/model-inputs.jsonl):
  token-id:n, avkodad sekvens och längd för varje fråga i varje exempel.
- [envelopes.jsonl](../../comparisons/laya-weight-space/ws03-pool-02/envelopes.jsonl):
  syntetiska ursprungsenvelopes och författad handlingsreferens. Detta är
  ännu inte en färdig replay-sidecar: regelutfall måste fångas i WS-04.
- [excluded.jsonl](../../comparisons/laya-weight-space/ws03-pool-02/excluded.jsonl):
  bortfall med orsak och synlig kontext, utan måletiketter.

Manifestet binder filhashar, källkod, tokenizer och det frysta WS-02-protokollet
`872ab384bf7ef3d59af38747c060b90a8590bc867a64852c4726955f7134ed58`.
Basens samlade checkpointidentitet kontrollerades före och efter:
`2f10784de17807f85cc9f02622039fad8f2fc15e9e2f294259f673a9b26c831a`.

## Vad självgranskningen kontrollerade

De 32 första familjerna täcker nytt/befintligt/osparat arbete, Write och Edit,
append/truncate, exklusiv skapning, Git-index och arbetskopia, återställning,
diffgranskning, notebook, CSV, loggar, arkiv, rsync, databaser, symboliska länkar,
hårda länkar, skiftlägeskollisioner, flytt, backupintegritet och aktualitet,
gemensam konfiguration, behörigheter, versionslagring, formattering och
arbetsytans gräns. Ytterligare fyra familjer korrigerar publicering/kommentarer
och täcker stödjande läsning respektive uttryckligen oklart användarval.

Granskningen jämförde mål, synlig handling, motivering och alla sju etiketter
inom varje par. Följande tolkningsregler är explicita:

- Godkännande förändrar uppgiftsanknytning och hantering, men inte i sig
  destruktiv risk, känslighet, extern påverkan eller återställbarhet.
  Byggverktyget kontrollerar denna invarians i behörighetsparen.
- Frågan om destruktiv risk omfattar överskrivning av värdefullt tillstånd,
  även när överskrivningen är avsiktlig och återställbar. Sådana exempel kan
  samtidigt ha `handling: allow`. Den frysta reducern kan ändå eskalera dem;
  detta möjliga policyhinder ska redovisas, inte döljas genom lägre risketiketter.
- Historiska v3-par för publicering och kommentarer blandade ihop tillstånd
  med återställbarhet. De nya paren har `difficult` på båda sidor eftersom
  mottagna notifieringar inte säkert kan återkallas. Äldre dataset ändras inte.
- Git-objekt kan finnas kvar efter att index och arbetskopia återställts.
  Fallet anger därför manuell objektsökning och `difficult`, inte omöjlig
  återhämtning. `repo.dirty` stämmer med de uttryckliga Git-scenarierna.
- Säkerhetskopians existens räcker inte: exakt innehåll, aktualitet och
  återställningsbarhet är skilda kontraster. Unika data utan återhämtning
  skiljs från kostsam men möjlig rekonstruktion.
- `unclear` används för ett uttryckligen obeslutat användarmål. Saknad kontext
  blir bortfall utan etiketter, inte ett påhittat negativt eller osäkert facit.

Native Write/Edit och MCP mappas genom den riktiga adaptern. Modellen ser inte
hela `action.arguments`. Accepterade mål anger därför nödvändiga fakta explicit;
de är syntetiska användaruppgifter, inte rekonstruerade verktygsobservationer.
Två par med dolda Write-/MCP-uppgifter och ett med bortkomprimerad målevidens
utesluts. Hela paret utesluts om någon medlem saknar synligt underlag.

Samtliga accepterade mål är högst 400 tecken. Den installerade Laya 0.3.4:s
sekvensbyggare och basens lokala tokenizer kontrollerade **504 frågesekvenser**
utan kapning; längst var 186 token mot `max_len=1024`, `head_max_len=256`.
Vikter laddades inte. Native innehåll kopieras inte artificiellt in i modellen.
Synliga dubbletter avvisas även när familjenamnet är annorlunda.

## Klassstöd före partitionering

| Fråga | Antal exempel per klass |
|---|---|
| task_alignment | aligned 39; supporting 4; unclear 1; outside_scope 28 |
| destructive_risk | false 27; true 45 |
| sensitive_resource | false 68; true 4 |
| external_impact | false 61; true 11 |
| reversibility | trivial 23; recoverable 20; difficult 6; irreversible 23 |
| verification_needed | false 37; true 35 |
| handling | allow 37; verify 5; replan 26; escalate 4 |

Alla klasser förekommer, men detta ger inte tillräckligt klassstöd i varje
framtida partition. Särskilt `unclear`, `supporting`, känslighet och eskalering
behöver fler självständigt utformade scenarier. Den explicita engelska mallen
och samma författares språk kan ge genvägar för modellen; nya verktygsförlopp,
andra formuleringar och senare verkliga fall behövs för att pröva överföring.

## Kvar till WS-04 och modellförsök

Insamlingsmålet kvarstår: minst 30 train-, 15 development-, 15 validation-
och 15 calibration-familjer, totalt 75. **39 ytterligare familjer behövs**
utöver denna pool, och fler om överlappsaudit eller granskning ger bortfall.
En författarfamilj räknas inte som statistiskt oberoende bara för att den har
ett nytt id. Semantiska släktskap behöver grupperas vid partitionering.

WS-04 ska utöka täckningen, auditera även ärvd träning och tidigare utmaningar,
hålla relaterade exempel tillsammans, fånga regelkontext och binda exporter.
Poolen är ännu `unassigned` och får inte beskrivas som blind eller isolerad.
Ett nytt mänskligt märkt verkligt sluttest och oberoende syntetisk granskning
återstår utanför optimerarens åtkomst. Inga kvalitetsvinster för Laya har mätts.

## Verifiering

13 nya datatester passerade. Hela sviten gav **347 passed** (49,01 s) med
localhost-/GPU-åtkomst; dess befintliga träning-smoke använder en tillfällig
checkpoint. `uv build --offline` skapade sdist och wheel. Exportens filhashar
och källkodshashar matchar, WS-02-protokollet är fortsatt giltigt och
`git diff --check` passerade. Produktionsmodell och policy är oförändrade.

## WS-04: öppna utvecklingspartitioner, 2026-11-08

Poolen har utökats med **54 explicit författade familjer** till **202 exempel
i 90 familjer**. Extra varianter ger fler stödjande läsningar och uttryckligen
obeslutade mål inom samma familj. Inga substantivbyten räknas som nya familjer.
Etiketterna är fortsatt syntetiska `frontier`-förslag, självgranskade utan
modellutfall. Ny författarturn är registrerad som `gpt-6-astra`/`high`,
`01a1bc92-d489-7550-b6af-bff4d87a6419`.

Nya mekanismer omfattar konverteringsförluster, YAML-/JSON-omskrivning,
SQL-predikat, transaktioner, schemaförlust, kalkylbladsformler, bildlager,
ljudkomprimering, PDF-anteckningar, generatorgränser, samtidiga ändringar,
backupnycklar, behörighetsregler och delade resursers versionsvillkor.
Självgranskningen preciserade bland annat loggrotationens race: bortfallet är
poster skrivna efter kopieringen men före trunkeringen. Git-fallet anger en
känd HEAD-reflog för återhämtning av en borttagen gren. Skriptbeteenden anges
explicit i målkontexten; deras namn är inte i sig evidens för beteendet.

Slutliga artefakter:

- [Poolmanifest](../../comparisons/laya-weight-space/ws04-pool-02/manifest.json)
  och [exakta indatas granskning](../../comparisons/laya-weight-space/ws04-pool-02/review.md).
  Alla **1 414 frågesekvenser** ryms utan kapning, högst 186 token. Sex
  otillräckliga WS-03-exempel förblir uteslutna. Basidentiteten är oförändrad.
- [Partitionsmanifest](../../comparisons/laya-weight-space/ws04-partitions-03/manifest.json):
  `c845c3de5f917c3561c4d41c2be57332c6d6ddf4e07af1bb22151e9aabb64a01`.
  Tidigare körmappar bevaras som mellanversioner.
- [Insamlingskontrakt](../../comparisons/laya-weight-space/ws04-partitions-03/test-intake.json)
  och [tom märkningsmall](../../comparisons/laya-weight-space/ws04-partitions-03/human-label-template.json).
  Mallen innehåller inga testfall eller färdiga mänskliga etiketter.

### Grupper och klassstöd

Sju konservativa länkar förenar närliggande familjer: arkivextraktion/restore,
backupintegritet/aktualitet, föråldrad diff/atomisk ersättning, hårdlänk/backupalias,
symbolisk länk/länkersättning, teckenkonvertering/radbrytningar samt firewall/roller.
Den sista länken fångades även av likhetskontrollen för de obeslutade varianterna.
Transitivitetskontrollen över session/familj/kontrastpar/semantisk grupp ger
**83 odelbara grupper**, inte 90 oberoende observationer.

| Partition | Exempel | Författade familjer | Odelbara grupper | Minsta gruppmål |
|---|---:|---:|---:|---:|
| train | 88 | 40 | 38 | 30 |
| development | 36 | 16 | 15 | 15 |
| validation | 41 | 18 | 15 | 15 |
| calibration | 37 | 16 | 15 | 15 |

Delningen är deterministisk och använder etikettstöd, aldrig prediktioner.
Sällsynta klasser placeras först, med stöd viktat efter partitionens gruppmål.
Alla klasser finns i varje partition. Gruppen följer alltid med i sin helhet.
Fördelningen utvecklades innan modellutfall; äldre partitionskörningar får
inte återanvändas selektivt efter att resultaten blivit kända.

| Fråga och klassordning | train | development | validation | calibration |
|---|---|---|---|---|
| alignment: aligned/supporting/unclear/outside_scope | 45/6/4/33 | 18/4/2/12 | 21/3/2/15 | 18/3/3/13 |
| destructive: false/true | 21/67 | 12/24 | 11/30 | 11/26 |
| sensitive: false/true | 80/8 | 31/5 | 35/6 | 34/3 |
| external: false/true | 78/10 | 32/4 | 36/5 | 32/5 |
| recovery: trivial/recoverable/difficult/irreversible | 24/35/2/27 | 12/12/1/11 | 9/18/2/12 | 9/14/2/12 |
| verification: false/true | 44/44 | 19/17 | 21/20 | 19/18 |
| handling: allow/verify/replan/escalate | 44/8/30/6 | 19/5/10/2 | 21/4/14/2 | 19/4/12/2 |

Gruppmålen är uppnådda. Sex träningsklasser ligger fortfarande under den
befintliga varningen om tio exempel, särskilt `difficult` med två. Varningarna
sparas oförändrade i manifestet. Ett öppet pilotförsök kan mäta bristerna;
goda genomsnitt kan inte bevisa inlärning för dessa små klasser.

### Överlapp och replay

Kontrollen läste **2 406 rader i tio historiska filer**: B:s ursprungliga export,
det äldre förberedda utvärderingsunderlaget, kandidatiterationernas båda
train/validation/calibration-uppsättningar samt 72/80-fallens challenge och
confirmation. Hashar, roller och saknade sessions-id:n sparas i manifestet.
Antalet avser rader över exporter, inte unika händelser.

Ingen exakt trace-/state-/deklarerad gruppöverlapp hittades. Måltokens granskas
dessutom med Jaccardgräns 0,65 utan etikettjämförelser. Inga historiska träffar
över gränsen hittades; en sådan träff skulle binda hela nya gruppen till
development. Olösta inbördes träffar stoppar export tills de grupperats.
Detta hittar inte alla semantiska dubletter. Okänd förträning och odeklarerade
släktskap förblir okända. Historiska tester blir aldrig nya blinda tester.

Varje partition har `dataset.jsonl` och komplett `replay.jsonl`. Riktiga regler
har matchats mot syntetiska envelopes under fryst konfiguration, och varje
envelope måste reproducera exakt sparat modelltillstånd. Regelfördelning:
train 86 PASS/2 HUMAN, development 36 PASS, validation 41 PASS, calibration
36 PASS/1 HUMAN. Aktuell sökvägsupplösning är deklarerad som syntetisk
fångstmiljö; detta är inte återskapad operativ historik. Inga exempelhandlingar
har exekverats. Questions, policy och basmodell är oförändrade.

### Sluttest och åtkomstbeslut

Användaren har bekräftat att **användaren märker de verkliga sluttestfallen**
och att **ingen miljö utanför Astras läsåtkomst finns**. En faktisk läsprobe från
agentprocessen (uid 1000) kunde läsa validation och calibration. Curriculum
och hela poolen har också varit synliga för författaren.

Status är `open_development_only`, med `development_ready: true` och
`blind_evaluation_ready: false`. Filerna är logiskt separerade men inte
åtkomstisolerade. En annan katalog eller samma användares filrättigheter
undanröjer inte redan sedd data. Ingen blind validering eller kalibrering hävdas.

Inga verkliga sluttestfall har samlats in. Målet kvarstår: minst 100 nya
mänskligt märkta verkliga fall, minst 30 säkra och 30 interventionsfall,
med separat stöd för överskrivningsfel. Mallen anger sju etiketter, motiveringar,
granskare, tidpunkt, grupp/session, handlingsreferens och nödvändig replay-kontext.
Märkning sker före modellutfall; otillräcklig kontext utesluts. En separat
oberoende syntetisk slututmaning återstår också.

Nästa modellsteg får endast vara det öppna B/D-utvecklingsförsök som
specifikationen tillåter när isolering saknas. Sluttestdelen av WS-04 förblir
öppen tills nya fall, mänsklig märkning och verifierad åtkomstgräns finns.

Verifiering: 15 nya partitionstester, **28 fokuserade tester** och **362 passed**
(45,26 s) i fullsviten. `uv build --offline`, fil-/källkodshashar, dokumentlänkar
och `git diff --check` passerade. Befintlig träning-smoke körde på tillfällig
checkpoint; ingen B/D-träning eller viktredigering har genomförts i WS-04.
