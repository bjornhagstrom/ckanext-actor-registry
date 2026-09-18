# Backlog

Framtida förbättringar för `ckanext-actor-registry` som är beslutade men inte
prioriterade ännu. Se även `docs/I18N_PLAN.md` för i18n-specifik backlog
(språkväljare i GUI, m.m.).

## Visa datamängder som saknar kontaktpunkt, på kontaktpunktssidan (2026-09-15)

`actors_index.html` har idag en sektion "Datasets without an actor link"
(`unlinked_datasets`) som listar datamängder som saknar *både* utgivare och
kontaktpunkt bland aktörerna ovan (se
`ckanext/actor_registry/templates/actor_registry/actors_index.html`,
runt raden med `{{ _('Datasets without an actor link ({n})')... }}`).

`contactpoints_index.html` saknar motsvarande sektion helt idag.

Björn vill ha en liknande funktion på kontaktpunktssidan: visa datamängder
som saknar kontaktpunkt. Att utreda vid implementation:

- Ska listan vara specifik för "saknar kontaktpunkt" (oavsett om utgivare
  finns), till skillnad från aktörssidans "saknar både utgivare och
  kontaktpunkt"? Det är sannolikt rätt tolkning, eftersom sidorna annars
  skulle visa nästan identiska listor och kontaktpunktssidans lista annars
  vore missvisande.
- Delad logik: bryt ut en gemensam query/helper i `views.py` (typ
  `_datasets_missing(role=...)`) som båda sidorna kan återanvända, i stället
  för att duplicera SQL/logik.
- Uppdatera i18n-katalogen (`i18n/sv/LC_MESSAGES/ckanext-actor-registry.po`)
  med de nya strängarna, och lägg till motsvarande automatiska test (jämför
  med `test_i18n_extraction.py` och de befintliga vyerna för aktörer).

Status: ej påbörjad, tillagd i backlog per Björns instruktion
("Kör" avvaktar; "lägg på backlog nu").

## Från README/CHANGELOG "Known limitations" -- vad som flyttats till backlog (2026-09-15, uppdaterat 2026-09-18)

Björn bad om en genomgång av de kända begränsningarna i `README.md` och
`CHANGELOG.md` för att avgöra vilka som är faktiska att-göra-punkter kontra
medvetna designval. Resultat:

**Flyttat till backlog (riktiga funktionsluckor):**

- **Import/export-kommando för registerdata** (CSV/JSON). Behövs för
  massredigering, migrering och backup/återställning utanför databasen
  direkt. Implementeras direkt mot modellen/databasen (t.ex. via
  `ckan`-kommandots vanliga plugin-kommandon eller ett fristående skript),
  INTE ovanpå ett generellt Action API -- se beslutet nedan om att inte
  bygga ett sådant.
- **Webbläsar- och flerversionskompatibilitetstester samt en formell
  säkerhetsgranskning.** Ren pre-launch-uppgift innan tillägget
  driftsätts bredare än denna PoC -- inte en kodändring i sig, men en
  konkret att-göra-punkt.
- **Automatiserad testtäckning gäller idag bara CKAN 2.11.6** (se
  `TESTING.md`, det reproducerbara testflödet bygger en isolerad
  CKAN 2.11-miljö), medan vår egen portal kör CKAN 2.12 sedan ett tag.
  Testsviten bör uppdateras/verifieras mot 2.12 (och ev. köras mot båda)
  för att inte ge falsk trygghet om att den täcker den version vi
  faktiskt driftsätter.

**Redan löst sedan denna genomgång skrevs (2026-09-15), inte längre en
lucka:**

- **Finare behörighetsmodell.** Löst av commit `44f01d5`
  (2026-09-16): registret (visa/skapa/redigera aktörer/kontaktpunkter +
  quick-create) är nu tillgängligt för alla inloggade redaktörer, inte
  bara sysadmins. Sammanslagningsfunktionen (`actors_merge`) förblir
  medvetet sysadmin-only (destruktiv, katalogomfattande) -- se
  `claude/aktorsregister-sammanslagning-plan.md` i huvudprojektet.

**Inte flyttat till backlog (medvetet designval, inte en lucka):**

- *"Selection and validation of identifier schemes and publisher-type
  vocabularies is left to the deploying catalog."* Det här är avsiktligt
  -- `ckanext-actor-registry` är tänkt att vara en generell,
  portabel extension (se `TASKLISTA_SKELLEFTEA.md`s regel om att
  Skellefteå-specifikt inte ska in i det allmänna tillägget), så den ska
  INTE hårdkoda ett specifikt vokabulär. Om Skellefteå vill definiera och
  validera sitt eget identifierarschema/utgivartyp-vokabulär är det en
  Skellefteå-specifik uppgift som hör hemma i `TASKLISTA_SKELLEFTEA.md`,
  inte här -- inte tillagd där heller ännu, flagga separat om det är
  aktuellt.
- **Fullständigt `ckan.logic.action`-CRUD-API för registerhantering
  (skapa/läsa/uppdatera/radera aktörer och kontaktpunkter program-
  matiskt), tillagt som medvetet designval 2026-09-18.** Tidigare
  listad som en "riktig funktionslucka" (se ovan, version före
  2026-09-18) -- Björn korrigerade detta: efter en jämförande
  undersökning av liknande CKAN-tillägg (utfört i en annan session,
  möjligen med ChatGPT/Codex snarare än här, därför inte tidigare
  dokumenterat i det här repot) konstaterades att ett fullt CRUD Action
  API är ovanligt bland jämförbara register-/metadata-tillägg och inte
  behövs för hur `ckanext-actor-registry` faktiskt används: admin-GUI:t
  täcker det dagliga redaktörsarbetet, och `actor_registry_actor_merge`
  (se `claude/aktorsregister-sammanslagning-plan.md`) täcker det enda
  fallet där ett programmatiskt anrop hittills behövts. Framtida
  import/export-behov (se ovan) löses direkt mot modellen, inte via ett
  generellt API som annars bara skulle finnas för sin egen skull.
  **Status: avsiktligt nedprioriterat, inte en brist.**

Status: ej påbörjat (för de kvarvarande punkterna ovan), ren
backlog-katalogisering.
