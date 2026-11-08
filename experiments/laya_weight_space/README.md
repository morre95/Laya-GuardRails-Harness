# Laya weight-space experiment

Experimentets [specifikation](../../tasks/laya-improvement/weight-space-spec.md),
[plan](../../tasks/laya-improvement/plan.md) och
[tasklista](../../tasks/laya-improvement/todo.md) beskriver B/D/W/DW-jämförelsen.
Här finns hittills endast WS-01: inventering och en liten tensorprobe.

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

WS-02 måste fortfarande låsa protokollet, och WS-03/04 måste färdigställa data
och isolera det nya sluttestet. `experiment_ready` är därför alltid false i
WS-01-manifestet, även när preflight-status är complete.

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
