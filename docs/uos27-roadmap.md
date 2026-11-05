# uOS27 — piano di sviluppo dell'interfaccia

**uOS27** è il nome del redesign nativo di Ubuntu Touch per il Galaxy S10+.
Il motore resta **Lomiri / Qt Quick**, non iOS: l'obiettivo è una fedeltà
visiva e d'interazione molto elevata al riferimento approvato, senza asset
proprietari Apple, servizi simulati o promesse di compatibilità con app iOS.

## Stato attuale: uOS27 0.10.5 RC6.1, 24 ottobre 2026

- **Build reale ARM64 completata:** [GitHub Actions 40025735292](https://github.com/MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus/actions/runs/40025735292) ha compilato i pacchetti nativi di Impostazioni a partire da **791 file originali identificati**, applicando le sette modifiche grafiche QML. `.deb` ed ELF AArch64 sono verificati con hash; il dispositivo non ha ricevuto alcuna modifica.
- **Un solo pacchetto di prova:** il generatore `scripts/package_uos27_integrated.py` raggruppa shell Glass, componente Home, PIN LightDM, temi Maliit, Impostazioni ARM64 e verifiche SHA-256. Il runner `scripts/uos27_trial_v015.py` monta soltanto copie temporanee dopo avere armato un timer di ripristino autonomo di 600 secondi. Dopo il preflight RC6 respinto sul telefono, RC6.1 distingue la versione sorgente `.deb` **1.3.2** dalla revisione completa dei tre pacchetti UBports effettivamente installati **1.3.2+0~20260808143253.1+ubports24.04.2~1.gbp2f4654** (stesso commit `2f4654cf`). Qualsiasi altra revisione, fonte non identica, overlay sovrapposto o recupero precedente non confermato continua a bloccare la prova.
- **Fedelità visiva:** il Centro di controllo usa ora la tonalità **blu notte** delle immagini di riferimento, radio raggruppate, riquadro audio, due cursori verticali, azioni di sistema reali e icone coerenti. Il preview Qt su desktop è una simulazione dichiarata, non una fotografia del Samsung. L'Home mostra le **vere icone installate**, dunque non inventa app Apple assenti. Lo sfondo resta quello personale del sistema, non un'immagine scattata dalle altre applicazioni.
- **Limiti ancora aperti:** nessuna dichiarazione di clone 1:1: riproduzione musicale in forma di scheda di dettaglio anziché comandi nativi nel riquadro, torcia/fotocamera senza un affidabile backend native dedicato, cartelle/widget non implementati, UI interna delle app terze non alterabile dalla shell. La prova sul dispositivo deve ancora confermare **PIN**, Bluetooth ON, luminosità iniziale, compatibilità plugin di Impostazioni, transizioni e recupero grafico.

## Base confermata

- Il telefono esegue BOOT 6 con la correzione grafica 1. Restano separati
  firmware, porting hardware e interfaccia uOS27.
- Nella prova reale **Lomiri Glass 0.9.3** sono stati approvati: proporzioni
  della barra sotto la fotocamera, collocazione della batteria, tinta azzurra
  della barra sopra le applicazioni e impianto estetico del Centro di controllo.
- La **0.9.4** è stata preparata con `preflight: OK` sul telefono, ma non esiste
  ancora evidenza della sua esecuzione grafica o del recupero completo.
- In RC6 il pannello Home passa a una tinta blu-notte semitrasparente **alpha 0,66**;
  sopra un'app a **alpha 0,76**. Vale sia per Controlli sia per Notifiche.
  Restano visibili lo sfondo reale e l'app sottostante; nessuna immagine di
  sfondo integrata, nessun costoso campionamento/blur dei pixel dell'app.

## Superfici dell'ultima build di riferimento e delle candidate RC4/RC5

| Priorità | Componente | Uscita verificabile | Blocco attuale |
| --- | --- | --- | --- |
| P0 | **Bluetooth** | `Gio.SimpleAction` temporanea scrive `BlueZ.Adapter1.Powered` dall'utente phablet e pubblica soltanto il reale readback; gli errori D-Bus sono registrati solo per nome, senza dati sensibili | **Non funziona ancora sul telefono** secondo l'ultimo test. Il solo stato letto dalla UI non dimostra che il comando `Powered=true` sia accettato da BlueZ/HAL; non mostrare un falso ON. |
| P0 | **Luminosità** | Reader `QDBusActionGroup` creato all'avvio della shell, riacquisizione all'apertura e polling solo durante l'interazione | L'utente riferisce che **ora sembra funzionare**; la scala fisica `actual_brightness` (800) non va confusa con `max_brightness` (48600). L'esatto comportamento iniziale resta da confermare nel trial RC3. |
| P1 | **Centro di controllo** | Tinte comuni 0,66/0,76; quattro radio raggruppate, scheda audio e due cursori verticali, controlli contestuali con conferma nativa | Qt5 visivo e input verificati, Mali reale non ancora. |
| P1 | **Notifiche e volume OSD** | Notifiche Lomiri originali con sfondo e card Glass; OSD mirato all'ID `indicator-sound` e sintassi Lomiri/canonical, nessuna alterazione avvisi critici | Qt source-reviewed; hardware OSD ancora da osservare. |
| P2 | **Schermata Home e dock** | RC4 legge il catalogo completo `AppDrawerModel` + `AppDrawerProxyModel` (include app non fissate), con pagine, ricerca e lancio nativi; il dock usa ancora `LauncherModel` | Qt5 con due modelli separati: 9/9. Ordinamento manuale, cartelle e widget non implementati e non simulati. |
| P2 | **Blocco schermo** | In RC3 lo swipe verticale/tocco apre il `LoginList` **originale**, riposizionato sopra la stessa cover e sopra il wallpaper; tastierino circolare `PinLockscreen` inoltra il PIN a LightDM | RC1 bloccava lo sblocco; RC2 conteneva ancora la pagina nativa separata. RC3 passa 6 controlli host con QML GreeterView/LoginList reale e LightDM simulato: apertura, input 4 cifre, errore, annullamento. Touch e PAM sul Galaxy ancora da provare. |
| P3 | **Switcher, Launcher, gesti, popup di sistema** | In RC4 il launcher laterale è nascosto nella sola sessione telefono sbloccata, ritorno alla Home con gesto dal basso; lo switcher dal bordo destro e le modalità greeter/desktop restano native | Qt5 e test di sorgente passati; il gesto reale su S10+ resta da provare. |
| P3 | **Tastiera Maliit** | Palette chiara/scura uOS27 con angoli 9dp, distanze e font migliorati su sorgenti upstream bloccati; gestione dei caratteri originale; RC5 prepara e verifica anche l'intero albero della tastiera | Compatibilità con la versione effettivamente installata, resa Maliit su S10+ e ripristino grafico ancora da provare. |
| P3 | **Impostazioni** | Patch a 7 QML per palette scura, icone in card, gerarchie, spaziatura dei gruppi e pagine dei plugin; **791 file** di sorgente nativo e pacchetto `.deb` ARM64 compilato e verificato | L'eseguibile è pronto per il triplo overlay; plugin ABI e resa sul Samsung non ancora verificati. |
| P3 | **Applicazioni di terzi** | La barra di stato può adattare i colori dichiarati dall'app quando disponibili | Non è possibile modificare il layout interno di ciascuna app dalla shell. |

## Linguaggio di movimento uOS27

- Impulso tattile sulle schede: sola scala **0,968 → 1** per circa 120 ms.
- Risposta dei cursori a cambiamenti esterni: altezza animata per 160 ms;
  trascinamento manuale immediato, senza inerzia falsificata.
- Passaggio Home ↔ applicazione: tinta del velo in 180 ms.
- Mini popup: comparsa/scomparsa di 190–210 ms con icona e breve stato.
  Radio ON/OFF annunciata **soltanto dopo il ritorno della proprietà nativa**.
- Tutte le transizioni sono disattivabili con `reducedMotion=true` e non
  utilizzano blur GPU, ShaderEffect o screenshot del contenuto privato.

## Una sola prova integrata sul Galaxy S10+

1. **Compatibilità:** QML originale byte-identico; `prepare`/`check` non
   installano; patch e moduli con hash bloccati. Mai sovrascrivere gli stage.
2. **Sblocco (primo gate):** verificare prima swipe verso l'alto, tastierino
   PIN e ingresso reale nella Home. Se il codice non si può inserire, fermarsi
   e lasciare agire il timer di ripristino; non cambiare le credenziali.
3. **Funzioni:** durante lo stesso trial grafico accendere/spegnere Bluetooth
   e modificare luminosità: il ponte salva in JSONL transizioni BlueZ e
   indicatore luminosità + valori `brightness`/`actual_brightness` grezzi.
4. **Interazione:** click, pressione lunga, scroll, swipe, notifiche e
   apertura dei dettagli senza duplicazioni né comandi quando la sessione
   è bloccata. Popup solo su stato confermato, niente falsi ON.
5. **Sicurezza:** preflight obbligatorio della tree SHA e dei 39 file modificati/aggiunti,
   mount separato e timer PID1 da 600 secondi; accesso di emergenza disponibile,
   ritorno ai file originali e sessione grafica da attestare sul dispositivo.
6. **Prestazioni:** verificare tempi d'ingresso, frame fluidi, consumo e
   artefatti su S10+, con effetti ridotti se necessari; i test Qt su PC
   con servizi fittizi non equivalgono a questa prova.

La **0.10 RC1 ha fallito il primo test sul telefono** prima della schermata
principale: swipe orizzontale e tastiera PIN assente. Il tester ha poi riferito
che l'interfaccia stock è tornata normale, senza però fornire il marker del
rollback. La **0.10.1 RC2** corregge il wiring del gesto e usa un tastierino
PIN nativo all'interno della shell. Sono state esercitate su Qt5 le interazioni
fino all'emissione della risposta originale; non il vero PAM del dispositivo.

La **0.10.2 RC3** sostituisce il tentativo RC2 di tastierino separato con il
`LoginList` originale integrato sulla cover e riordina il Centro di controllo.
Ha **26 QML originali modificati più 13 moduli**, con preparazione riproducibile
e checksum bloccati; sul computer sono passati i test di un PIN numerico fino
all'unica risposta dell'API LightDM, cancellazione dopo errore e ritorno
all'orologio senza sblocco. Il test Home eseguito in parallelo con altri processi
Qt ha avuto una chiusura isolata; ripetuto da solo, ha superato 6/6 controlli.

La 0.10.2 RC3 è **il candidato completo per il perimetro della shell Lomiri**:
non sostituisce il contenuto delle app, il servizio Maliit, il framework
Impostazioni o le API del sistema Android. Non è ancora approvata per
installazione persistente: l'unico test previsto è un overlay reversibile
di 600 secondi, dopo il quale un solo resoconto deve coprire UI, radio,
luminosità e recupero. La fonte di verità hardware rimane il telefono.

## Candidata successiva: 0.10.3 RC4 (23 ottobre 2026)

- **Modello Home corretto:** RC3 mostrava soltanto le app fissate nel launcher.
  RC4 usa davvero il catalogo di tutte le app installate che Lomiri ritiene
  visibili, con aggiornamento dinamico, filtro per nome e dock separato. Il
  pulsante Cerca in stile pillola apre la ricerca senza un menu laterale. Il
  launcher laterale sparisce nel profilo smartphone **sbloccato**, non nel
  greeter o nei profili desktop/tablet.
- **Gesti nativi:** ritorno alla Home con un gesto verticale deliberato dal
  centro in basso; indicatore Home a fondo schermo; switcher destro non
  disabilitato. Il PIN continua a usare `GreeterView`/`LoginList` e LightDM.
- **Staging riproducibile:** 26 file QML originali modificati + 13 moduli,
  patch SHA-256 `dfea07136453c99cad25b0d53da70beb0ca0c06900b762dd0a7f57d2a6d9126b`.
  Sul checkout upstream 306 originali → 319 QML; sull'ultimo inventario S10+
  si attendono 305 → 318, ma **nessun preparatore RC4 è stato eseguito sul telefono**.
- **Verifica al PC:** Home 9/9 (inclusa schermatura app e persistenza pagina); gesto sblocco / PIN 8/8; cover originale 6/6;
  entrambe le varianti del pannello 16/16. Suite Python uOS27 52/52;
  test precedenti Lomiri Glass 108/108. Scoperta generale Python:
  349 test, 3 saltati, zero errori. Resta da eseguire una sessione reale.
- **Superfici native esterne:** sorgenti ufficiali Maliit e Impostazioni
  bloccati su revisioni note. Preparatore `build_uos27_native_theme.py` e
  palette `uOS27.json` generano modifiche solo estetiche in alberi temporanei.
  L'inventario `uos27_native_inventory.py` fa un controllo passivo di SHA,
  collisioni dei temi e versioni dei pacchetti, senza installare nulla.
  Impostazioni comprende ora anche i riquadri delle icone native (5 file di
  stile QML), ma **non** è alterabile con l'overlay shell e richiede build Qt ARM64.
- **Limitazione esplicita:** non è corretto definire questa RC4 un clone
  completo 1:1 di iOS 27. Il linguaggio grafico sta diventando coerente,
  ma widget, cartelle, personalizzazione dei controlli, tastiera in funzione,
  Impostazioni e molte integrazioni Apple non sono ancora equivalenti o
  sono specifiche di altri sistemi. Non vanno simulate come operative.

Prima dell'unico test desiderato dall'utente occorrono il controllo della
revisione installata di Maliit, l'integrazione sicura delle sue risorse e un
collaudo di build dedicato per Impostazioni; altrimenti il trial RC4 verifica
la **shell**, non l'intero sistema.

## Candidata di preparazione: 0.10.4 RC5 sperimentale (23 ottobre 2026)

- **Shell + Maliit con ripristino unico:** il runner
  `scripts/uos27_trial_v014.py` verifica due stage indipendenti; monta la
  tastiera prima della shell, ma **arma il solo timer PID 1 da 600 secondi
  prima di qualunque mount**. Il ripristino smonta shell e tastiera, poi
  riavvia LightDM. Il test unitario usa solo mount e servizi simulati: nessuna
  prova RC5 è stata effettuata sul telefono.
- **Tastiera sorgente pin:** `prepare_uos27_keyboard_stage.py` controlla le
  tre QML originali e tutte le risorse non modificate, rifiuta link simbolici,
  file speciali e nomi di temi esistenti; scrive solo tre modifiche visive
  più due palette JSON. Su checkout host: 74 file originali → 76 preparati,
  5 modificati/aggiunti. Non tocca gli eventi di composizione o la password.
- **Impostazioni nativamente compilate, ancora mancanti:**
  `prepare_uos27_settings_build.py` genera da un commit Git verificato una
  sorgente completa con 7 QML modificati, più un controllo di integrità
  read-only su 791 file. Non esiste ancora un eseguibile ARM64 né una prova
  dei plugin Qt installati. Le patch delle Impostazioni non vengono attivate
  dal runner temporizzato. Un secondo auditor già pronto verifica offline i
  futuri `.deb` per nome, architettura, ELF AArch64 e hash, senza eseguire o
  installare il pacchetto: **non** può però attestare la provenienza della
  compilazione né la compatibilità con i plugin dell'S10+.
- **Bluetooth a due stadi:** il servizio non privilegiato ora invoca prima
  l'azione booleana dell'indicatore Ayatana esistente, attende l'effetto su
  rfkill/BlueZ e utilizza `Adapter1.Powered` solo come eventuale fallback,
  sempre con readback reale e tracciamento senza dati identificativi. Il
  rapporto distingue anche `soft_blocked`/`hard_blocked` delle sole radio
  Bluetooth: non registra ID, indirizzi, nomi né dispositivi accoppiati.
  È una **correzione candidata**: non prova che BlueZ accetti il comando sul
  dispositivo.
- **Blocco deliberato del trial parziale:** l'avvio predefinito `trial` di
  RC5 è disabilitato finché il pacchetto non copre anche le Impostazioni.
  L'esenzione `--ack-shell-keyboard-only` è riservata allo sviluppo e **non
  soddisfa il requisito dell'utente di una sola prova finale**. `check`
  restituisce sempre `ready_for_complete_single_trial: false`.
- **Verifiche:** preparazione completa di Maliit su fixture upstream;
  verifica sorgente Impostazioni sull'intero albero; prove di invarianti
  sull'ordine timer/mount e blocco del trial incompleto; suite Python generale
  superata sul computer. PIN/PAM, Bluetooth ON, luminosità e animazioni
  devono ancora superare **l'unica sessione fisica finale**.

Non etichettare questo punto di sviluppo come clone iOS 27 completo o come
release installabile. Mancano ancora le Impostazioni ARM64, la conferma del
rendering Maliit e soprattutto l'accettazione LightDM sulla vera lockscreen.
