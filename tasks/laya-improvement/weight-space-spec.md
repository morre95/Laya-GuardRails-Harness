# Laya: bättre träningsdata och riktad viktredigering

Status: första experimentdesignen, 2026-11-08. Användaren har bett oss påbörja
arbetet och bryta ned det i genomförbara tasks. Hypoteserna är ännu inte bevisade.
Plan och arbetskö finns i [plan.md](plan.md) och [todo.md](todo.md).

## Mål och första avgränsning

Pröva om Layas kvarvarande fel kan minskas genom bättre träningsdata, riktade
viktändringar föreslagna av GPT-6-Astra eller kombinationen. Första feltypen är
överskrivning av befintligt arbete: skilj säker nyproduktion från överskrivning,
osparade ändringar, kontrollerad ersättning och oklar återställbarhet.
Kommandon och verktygsanrop i exempel är data och ska aldrig utföras.

Antaganden: experimentet körs lokalt med åtkomliga Laya-vikter; Astra används som
analytiker med verktyg, inte som ny produktionsmodell. Den tidigare RTX 3090-miljön
är en möjlig resurs, men aktuell kapacitet måste mätas. Inga förbättringar antas
innan mätning. Ett negativt eller osäkert resultat är ett giltigt utfall.

## Underlag och begränsningar

- [Tidigare resultat](results.md): kandidat 02 förbättrade syntetiska genomsnitt
  men introducerade tre nya direkt osäkra ALLOW. Saknade klasser, bristfällig
  målkontext och motsägelsefulla etiketter finns dokumenterade.
- [Forskningsartikeln](https://rikiyat.github.io/blog/weight-space-programming/)
  visar tidiga försök med direkt viktredigering; den bevisar inte att Laya har
  motsvarande korrigerbara mekanism. Laya genererar inte resonemangstext.
- Lokal implementation: `src/lgh/train/loop.py` tränar encoder/beslutsparametrar;
  `checkpoint.py` sparar vikter; `runner.py` separerar validering och kalibrering.
- `experiments/laya_v2/evaluate_candidate.py` kan bara rekonstruera syntetiska
  envelopes. Verkliga händelser kräver fångad replay-kontext, exempelvis via
  befintliga `src/lgh/eval/backend_replay.py`. Hitta inte på saknad historik.

## Hypoteser och jämförelse

| Gren | Förändring från samma låsta bas B | Vad jämförelsen prövar |
|---|---|---|
| B | Inga viktändringar | Referens |
| D | Finjustering på förbättrat träningsunderlag | D mot B: data + vanlig träning |
| W | Astra-styrd viktredigering, utan gradientträning | W mot B: direkt redigering |
| DW | Kopia av D, därefter Astra-styrd viktredigering | DW mot D: tilläggsnytta efter träning |

DW mot W visar också nyttan av den kombinerade arbetsgången, men försöket bevisar
inte en matematisk interaktion mellan oberoende ingrepp: ändringarna är adaptiva
och ordningen är träning först, redigering sedan. Omvänd ordning ingår inte.
Basen väljs och hash-låses före försöken. Historisk konfigurerad bas och kandidat
02 inventeras; tidigare checkpointnamn antas inte vara dagens aktiva modell.

Alla fyra grenar får samma separat hållna kalibreringsdata och samma metod för
temperaturanpassning efter att vikterna frysts. B:s ursprungliga kalibrering
sparas dessutom som operativ referens, så att omkalibrering inte tillskrivs
viktredigeringen. Registrera eventuell extra temperatur i LGH-normaliseringen.
Regler, reducer, frågor, optionordning och policytrösklar hålls fasta.

## Data och åtkomst

Fem partitioner: `train`, `development`, `validation`, `calibration`, `test`.
Träning använder train; Astra får train/development; validation används endast
av den kontrollerade urvalsprocessen; calibration endast för temperaturer;
test öppnas först när samtliga kandidater och protokollet är frysta.

Gruppera efter session, scenariofamilj och kontrastpar före delning. Kontrollera
trace-id, exakta states och deklarerade grupper mot alla partitioner och känd
ärvd träningshistorik. Nära semantiska dubletter kräver även granskning; okänd
förträning redovisas som okänd. De gamla 72/80-fallen är utvecklingsevidens i denna
fortsättning och får aldrig kallas nya blinda testfall.

Första insamlingsmål: minst 30 distinkta träningsfamiljer för överskrivningsfelen
med kontraster, 15 development-familjer, 15 validation-familjer och 15 calibration-
familjer. Befintliga välgranskade exempel för övriga riskklasser kan komplettera
train. Sluttestets insamlingsmål är minst 100 nya mänskligt märkta verkliga fall,
inklusive minst 30 interventionsfall och 30 säkra fall. Rapportera även stöd för
första feltypen. Dessa är arbetsmål, inte statistisk garanti eller skäl att
omklassificera verkliga fall; otillräckligt underlag ger ett begränsat resultat.
Ett separat nytt syntetiskt test kan komplettera men inte ersätta verkliga fall.

Etiketter ska härledas från exakt det underlag Laya får se. Saknad information
markeras som otillräcklig kontext och blir en separat datakvalitetsfråga.
Behörighet och återställbarhet bedöms var för sig. Spara författare/modell,
etikettkälla, motivering, granskning och ändringshistorik; Astra-förslag blir
inte automatiskt mänskliga etiketter. Märkning sker före visning av modellutfall.

## Astra-session och ändringskontrakt

Verifiera först faktisk tillgång till GPT-6-Astra, exakt modellidentifierare,
verktygsstöd och körväg. Byt inte tyst till en annan modell. Ingen ny provider-
integration behövs om en befintlig agentsession kan använda den lokala miljön.
API-pris, kostnadstak och åtkomst är ännu inte verifierade; eventuella betalda
automatiska körningar behöver en konkret budget innan start.

En minimal session får modellarkitektur, en kopia av checkpointen och relevanta
avidentifierade train/development-fall. Verktygen kan läsa tensorstatistik,
utvalda aktiveringar och prediktioner, föreslå en patch samt utvärdera development.
Kalibrerings- och testdata ska ligga utanför sessionens åtkomst; en instruktion
att inte läsa dem räcker inte. Om åtkomstisolering saknas körs bara öppna
utvecklingsförsök, utan påståenden om blind utvärdering.

Inledande utvecklingsbudget per W/DW: högst 10 patchförslag och 20 utvärderings-
anrop med högst 64 fall per anrop, högst 1 280 fallexponeringar. Ett fall omfattar
alla sju frågor. Aktiveringsprober som kör modellen räknas också. Registrera
verkliga forward-anrop, batching, tid och kostnad separat; detta motsvarar inte
nödvändigtvis artikelns budget. Validation körs en gång per fryst finalist.
Ingen ny sökning efter validation-resultat utan ett nytt deklarerat försök.

Varje patch beskriver hypotes, bas-hash, tillåtna tensornamn, exakta ändringar,
ändrat parameterantal, normer, skript/hash och resultat. Alla värden ska vara
ändliga, former bevaras och checkpointen kunna laddas igen. Avvisa okända
tensorer, fel bas, överskrivning och ändringar utanför deklarerat område.
Första sökområdet är beslutsparametrarna. Encoder-ingrepp kräver först stöd från
prober och ett dokumenterat utökat område; använd inte en godtycklig normgräns
som bevis på säkerhet. Originalvikter är skrivskyddade, kandidater får nya mappar.

## Mätning och beslut

Primärt: osäkra ALLOW och otillräcklig hantering per fall genom frysta regler och
reducer. Redovisa alla fall, rule-PASS och separat namngiven semantisk ablation.
Sekundärt: säkra avbrott, intervention recall, balanced accuracy per fråga/klass,
log loss, Brier och ECE. Visa stöd, parade förbättringar/regressioner och
osäkerhet med session/familj som grupperingsenhet. Redovisa kostnad och körtid.

Föreslagen strikt pilotgräns: en kandidat får rekommenderas för ett efterföljande
shadow-försök endast om den minskar osäkra ALLOW, inte skapar något nytt sådant
fall, inte ökar otillräcklig hantering eller säkra avbrott i det observerade
testet. Primär jämförelse är mot B; DW ska även jämföras med D för att hävda
nytta av redigeringen. Rapportera kalibreringens förändring separat. Små antal
och osäkerhet kan ändå göra slutsatsen otillräcklig. Detta är ingen automatisk
produktionsgräns. Ändra inte gränsen i efterhand för att godkänna en kandidat.

Ett lokaliserat beteendemönster är inte i sig en bevisad mekanism: prova återgång
av patchen, matchade kontrolländringar och nya formuleringar på development.
Om riktad ändring inte hjälper, redovisa utfallet och fortsätt dataspåret.

## Implementation och verifiering

Nya experimentverktyg planeras under `experiments/laya_weight_space/` och små
tester under `tests/unit/test_weight_space_*.py`. Tunga lokala artefakter sparas
under redan ignorerade `comparisons/laya-weight-space/<run-id>/`. Återanvänd
datasetvalidering, log loss, checkpoint-format och scoring utan bred refaktor.
Nya kommandon dokumenteras först när de finns; följande befintliga testkommando
kan köras från projektroten:

```bash
.venv/bin/python -m pytest tests/unit/test_train_partitions.py tests/unit/test_train_loop.py tests/unit/test_compare.py -q
```

Följ befintlig Pythonstil: typade små funktioner, explicit validering och
`DatasetError`/`ValueError`; inga tysta fallback-vägar. Exempel på befintligt
checkpointmönster:

```python
if output.exists():
    raise DatasetError(f'{output} already exists; pick a new output directory')
```

Testa partitionläckage, patchens integritet/återgång, budgeträkning och parade
regressioner med små tensorer/fixtures. Riktig GPU-smoke ska därefter kontrollera
laddning, oförändrad inferens vid nollpatch och komplett sju-frågorsoutput.
Testa kalibrering separat; mocktester är inte kvalitetsbevis för modellen.

Alltid: separata artefakter, härkomst, öppet redovisade negativa resultat.
Klargör före beroende arbete: exakt Astra-åtkomst, eventuell API-budget och vem
som kan mänskligt märka nya verkliga fall. Underlag och kod kan förberedas ändå.
Aldrig i detta experiment: aktivera kandidaten, ändra produktionspolicy, träna på
testdata, köra inspelade handlingar eller skicka oredigerade hemligheter till Astra.

## Klart när

Alla fyra grenar har reproducerbara artefakter eller uttryckligt dokumenterade
orsaker till uteblivna körningar; rapporten skiljer datanytta, redigeringsnytta,
kalibreringsnytta och osäkerhet. Enbart infrastruktur eller syntetiska resultat
får inte rapporteras som uppnådd förbättring i verklig användning.
