# Historical recovered notes

These notes are preserved from commit 285aef5d3d7a5678dc5812499aa1bf1cc2f0f618. Their trial commands/statuses are historical and are not instructions to deploy the revised source. The later RC7/v015 tester result rejected the UI; read RECOVERY-2026-11-05.md and the current README first.

# uOS27 — interfaccia Lomiri per Galaxy S10+

**Lomiri Glass è diventato il primo modulo di uOS27.** Il nuovo nome copre
l'intero redesign di sistema: non soltanto il Centro di controllo, ma anche
Home, dock, blocco schermo, animazioni, popup, switcher e componenti comuni.
La [roadmap uOS27](../../docs/uos27-roadmap.md) definisce le priorità e i
criteri di accettazione. Gli asset e i componenti restano originali; Lomiri
continua a gestire sicurezza, sessione e servizi nativi.

**Candidata 0.10.3 RC4 — preparata e collaudata soltanto su host Qt5.**
Home usa ora `AppDrawerModel` + `AppDrawerProxyModel` per mostrare tutte le app
visibili e non soltanto le app fissate in `LauncherModel` (che resta la fonte
del dock). La ricerca è interna alla Home. Nella sessione smartphone
**sbloccata** il launcher laterale è disattivato e il ritorno Home è affidato
a un nuovo gesto dal basso; il bordo destro dello switcher, la modalità
greeter e il flusso PIN/LightDM non sono stati sostituiti. Staging 26
originali modificati + 13 moduli aggiunti, patch SHA-256
`dfea07136453c99cad25b0d53da70beb0ca0c06900b762dd0a7f57d2a6d9126b`.
Host: 7/7 prove Home, 8/8 gesto e PIN, 6/6 cover, 2 varianti da 16/16
prove pannello. **Nessuna prova su Galaxy ancora eseguita.**

Un nuovo modulo separato [`shell/uos27-native/`](../uos27-native/) prepara
un tema Maliit e una patch sorgente per Impostazioni, ma **non li installa**.
I QML di Impostazioni sono compilati dentro l'eseguibile e richiedono una
build ARM64; non è tecnicamente possibile tematizzarli con il solo mount
`/usr/share/lomiri`. Bluetooth ON non è ancora convalidato sul dispositivo.

**Candidato uOS27 0.10 RC1, 23 ottobre (solo host):** 24 file originali Lomiri
modificati e 11 moduli nuovi coprono **Home con pagine/dock**, Libreria app,
Launcher, Greeter/PIN, notifiche, OSD del volume, status bar, Control Center,
switcher e popup/dialoghi. Entrambi i pannelli sono più scuri e semitrasparenti
(alpha **0,61 sulla Home**, **0,72 sopra le app**) e lasciano visibile il vero
sfondo. Stati radio e popup sono confermati dal backend. La luminosità viene
interrogata prima del primo pull-down; una GAction temporanea dell'utente
`phablet` prova a controllare l'effettivo `BlueZ.Adapter1.Powered`. Uno
strumento session-only raccoglie in JSONL i readback BlueZ e del backlight,
senza indirizzi hardware e senza messaggi. **Le correzioni hardware, gli effetti
Mali e il ripristino grafico rimangono da provare sul Galaxy S10+: il pacchetto
fornisce un unico trial integrato, non più piccoli test.** Tastiera Maliit,
contenuto delle Impostazioni e delle app non sono QML appartenente alla shell
e richiedono modifiche separate: qui non sono stati alterati.

Prima implementazione nativa QML della barra di stato, del centro notifiche e del centro di controllo per Ubuntu Touch 24.04. Il riferimento visivo è iOS 27: riquadri arrotondati, superfici traslucide, gerarchia leggibile e cursori verticali. Le icone vettoriali sono originali e i servizi rimangono quelli di Ubuntu Touch.

**Stato al 23 ottobre 2026:** le prove **0.5 e 0.6** hanno raggiunto l'interfaccia. La **0.7 ha provocato un errore fatale QML sul telefono** (`backgroundSourceSize` non supportato); non va ripetuta. La **0.8** ha raggiunto l'interfaccia. La **0.9** è stata soltanto preparata; **0.9.1, 0.9.2 e 0.9.3** sono state osservate sul telefono. Con la 0.9.3 l'utente ha approvato l'altezza della barra (allineata al foro delle fotocamere), il colore azzurro quando ci sono applicazioni aperte e il design complessivo; **Bluetooth non si riaccende e il cursore di luminosità continua a mostrare un valore iniziale non affidabile**. La **0.9.4 introduce un velo un po' più intenso sui controlli e sulle notifiche sovrapposti a un'app** e resta da provare sul telefono. Nessuna modifica permanente a BOOT/SYSTEM; prima di una nuova prova va confermato il ripristino originale.

## Revisione 0.9.4 — leggibilità di Controlli e Notifiche sopra le app

- **Sulla Home:** Controlli e Notifiche mantengono il velo semitrasparente di 0.9.3 (opacità 0,48), attraverso cui si vede lo sfondo reale.
- **Con un'app aperta:** entrambi i pannelli usano una tinta identica ma leggermente più intensa (opacità 0,57), mantenendo visibile l'app sottostante e migliorando il contrasto con testi e video.
- **Barra di stato:** invariata. Restano l'altezza, la posizione delle icone e l'adattamento cromatico già approvati sul telefono.
- **Collaudo:** entrambe le varianti `WithCutouts` e `WithoutCutouts` hanno passato verifiche integrate Qt 5 della propagazione dello stato app/Home e della trasparenza risultante. Non si tratta di un test GPU o grafico sullo smartphone.
- **Difetti da isolare:** l'azione Bluetooth esposta da Ayatana risulta disattivata e l'adattatore BlueZ è spento pur senza blocchi `rfkill`; è possibile che il servizio agisca soltanto sul killswitch. La luminosità letta dal servizio è stata 1,0 mentre `actual_brightness` valeva 800 con `max_brightness` 48600; le scale o la sincronizzazione potrebbero differire. Nessuna delle due ipotesi è confermata senza ulteriori misure sul telefono, quindi non viene proposta una scrittura diretta a `/sys` o al controller Bluetooth.

La 0.9.4 si prepara in un albero separato con `lomiri_glass.py prepare --source /usr/share/lomiri --output "$HOME/lomiri-glass-qml-stage-v094"`. Si controlla con `sudo python3 scripts/lomiri_glass_trial_v094.py check`. Eseguire `trial` solo dopo la conferma del ripristino della 0.9.3 e la disponibilità di una via di recupero indipendente da Lomiri; lo script conserva il timer di ripristino di 600 secondi.

## Revisione 0.9.3 — barra adattiva, altezza fotocamere e rete separata

- Barra in verticale ulteriormente ridotta **da 6,2 a 5,4 GU** (espansa da 7,2 a 6,4 GU), con area riservata a destra per la doppia fotocamera. Sono misure candidate derivate dalle foto, non una calibrazione fisica.
- **Home:** trasparenza coordinata con il centro di controllo. **App aperta:** la barra prende il colore di testata dichiarato nell'identità dell'app (`splashColorHeader`, oppure `splashColor`) quando opaco. In mancanza, viene usato un fallback legato al tema; il browser Morph ha un fallback chiaro per il caso bianco osservato. Ora, batteria e icone passano automaticamente a una tinta scura su sfondi chiari. **Limite:** la shell non riceve il colore dei pixel correnti di ogni applicazione, perciò i colori che cambiano durante la navigazione non sono riprodotti in modo esatto.
- **Wi-Fi:** una vista dedicata utilizza l'endpoint nativo `/com/lomiri/indicator/network/phone_wifi_settings` ed elenca esclusivamente le reti e i relativi comandi, senza dati mobili o Ethernet.
- **Dati mobili:** una vista distinta con stato/interruttore nativo e collegamento diretto alla pagina Impostazioni SIM/cellulare; **modalità aereo** ha a sua volta una vista specifica. Nel centro di controllo non viene più presentata la pagina generale che include Ethernet; Ethernet continua a essere disponibile nelle Impostazioni di sistema.
- **Bluetooth e luminosità:** il comportamento osservato nella 0.9.2 non è ancora risolto, perciò non viene falsificato uno stato attivo. `scripts/lomiri_glass_hardware_readback_v093.py` legge senza modifiche i valori D-Bus, BlueZ/rfkill e del backlight per distinguere errori d'interfaccia da errori del backend.

Preparazione su smartphone senza sostituzione della shell originale:

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /usr/share/lomiri \
  --output "$HOME/lomiri-glass-qml-stage-v093"

sudo python3 scripts/lomiri_glass_trial_v093.py check
python3 scripts/lomiri_glass_hardware_readback_v093.py
```

**Non avviare `trial` senza confermare che la prova 0.9.2 è conclusa e che `/usr/share/lomiri` non è montato:** il report precedente ha riguardato la UI, non il recupero. Dopo un `check` positivo e conferma di un canale di recupero, lo script conserva il test temporaneo da 600 secondi con timer indipendente (`trial`/`restore`). Il rientro grafico completo resta da verificare sul telefono.

## Revisione 0.9.2 — lettura iniziale luminosità, Bluetooth e altezza barra

Questa versione conserva trasparenza sul wallpaper reale, ordine delle icone e cursori senza etichette/percentuali, ma corregge tre punti della 0.9.1:

- **Luminosità:** all'avvio di `NativeBackend.qml` viene creato un `QDBusActionGroup` verso `org.ayatana.indicator.power` e interrogato lo stato dell'azione `brightness`; il cursore legge il valore senza aspettare una prima modifica. Le variazioni provenienti dal servizio aggiornano il cursore senza richieste inverse. Il modello QMenuModel resta come fallback controllato.
- **Bluetooth:** il comando `bluetooth-enabled` usa in via primaria il `QDBusActionGroup` nativo impiegato anche da Impostazioni di sistema, con parametro Booleano. La UI continua a richiedere un riscontro del servizio e **non finge che l'hardware sia acceso** se non arriva. Il successo fisico non è ancora dimostrato: l'indicatore può accettare una richiesta senza riuscire ad alimentare l'adattatore.
- **Barra di stato:** altezza chiusa ridotta **da 7,8 a 6,2 GU**; altezza espansa Glass **da 8,8 a 7,2 GU**. Il cambiamento vale soltanto in sessione Glass telefono in verticale: le condizioni di greeter/stock non sono mutate. La distanza esatta dal foro frontale resta da calibrare con fotografie, non è stata misurata.

La suite locale Qt 5 ha confermato il valore iniziale della luminosità **prima di qualunque tocco**, la propagazione di un cambiamento del servizio e l'invio del parametro Bluetooth tramite il componente D-Bus nativo. Le due varianti PanelMenu e gli undici test d'interazione hanno superato le fixture. **Queste prove non riproducono lo stato BlueZ e la luminosità del display reale sull'S10+.**

Usare soltanto un nuovo staging e il nuovo script di verifica (non usare gli script di prove precedenti su questa versione):

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /usr/share/lomiri \
  --output "$HOME/lomiri-glass-qml-stage-v092"

sudo python3 scripts/lomiri_glass_trial_v092.py check
```

Se il controllo restituisce `ready_for_timed_trial: true`, il telefono è carico, Lomiri originale è tornato operativo, non vi è alcun mount attivo e si dispone di un percorso d'emergenza, eseguire la prova di 600 secondi con `sudo python3 scripts/lomiri_glass_trial_v092.py trial`. La procedura prova a ripristinare il QML originale e riavviare LightDM indipendentemente dal terminale. Non può garantire il recupero grafico in ogni condizione. Il ripristino anticipato è `sudo python3 scripts/lomiri_glass_trial_v092.py restore`. Controllare il valore del cursore **prima di muoverlo**, lo stato Bluetooth e la barra; poi leggere il marker `/run/lomiri-glass-v092-one-shot/rollback-result` e verificare che `/usr/share/lomiri` non sia montato. La nuova verifica rifiuta anche una prova 0.9.1 precedente ancora priva di rollback confermato.

## Revisione 0.9.1 — cronologia: barra ordinata e cursori senza testo

La preparazione e il controllo 0.9 sul telefono hanno avuto esito positivo (313 file, 19 aggiornamenti, nessuna installazione). Il test Bluetooth 0.9 aveva un errore nel **nome dell'azione interrogata**: `indicator.` è un prefisso usato dal client QMenuModel, non parte del nome esportato tramite `org.gtk.Actions`. Il messaggio `InvalidArgs` non dimostrava che il servizio mancasse. La 0.9.1 corregge la sonda e aggiunge un elenco delle azioni D-Bus, senza modificarne lo stato. Inoltre garantisce che l'altezza del pannello minimizzato (7,8 GU) sia inferiore a quella del pannello espanso (8,8 GU) nella sola sessione Glass sbloccata, preservando le dimensioni native in greeter e in modalità stock. **Non avviare la prova temporanea 0.9: usare 0.9.1 dopo un nuovo preflight.**

- Barra superiore rialzata provvisoriamente a **7,8 unità griglia**, da verificare sul display e confrontare con il bordo inferiore delle due fotocamere; questa dimensione è ricavata dalla stima fotografica (210 px / GridUnit 27), non da una calibrazione hardware.
- Ordine distinto: **ora a sinistra → Wi-Fi/rete e altri indicatori hardware attivi al centro → batteria a destra, prima dell'area delle fotocamere**. L'area delle fotocamere non viene coperta da una pillola artificiale.
- Il filtro riconosce i nomi Wi-Fi nativi `nm-signal-*` e non mostra la rete cablata scollegata. Icone/stati effettivi devono comunque essere verificati sul telefono.
- Barra superiore e Centro di controllo condividono lo stesso velo semitrasparente; nessun wallpaper sintetico aggiunto alla shell.
- **Luminosità e volume mostrano solo l'icona**, senza etichetta e senza percentuale stampata sul cursore. I valori reali restano disponibili alle API e all'accessibilità.
- La richiesta Bluetooth conserva l'azione nativa e l'attesa della conferma; **non è ancora dimostrato che il comando venga eseguito dal servizio Bluetooth sul dispositivo**. Il pacchetto include `scripts/lomiri_glass_radio_check_v09.py`, controllo diagnostico in sola lettura, senza `sudo`, MAC o nomi di reti.

Preparazione sicura (cartella nuova, senza Git e senza modifiche di sistema):

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /usr/share/lomiri \
  --output "$HOME/lomiri-glass-qml-stage-v091"

sudo python3 scripts/lomiri_glass_trial_v091.py check
python3 scripts/lomiri_glass_radio_check_v09.py
```

Solo dopo `ready_for_timed_trial: true`, conferma del ripristino precedente e possibilità di recovery, il comando per la prova temporanea è `sudo python3 scripts/lomiri_glass_trial_v091.py trial`. Il ripristino anticipato è `sudo python3 scripts/lomiri_glass_trial_v091.py restore`; quello pianificato tenta di smontare la copia temporanea e riavviare LightDM dopo 600 s. Non equivale a un rollback della shell già validato sul telefono.

## Correzioni visive della 0.8 — candidatura per prova temporanea

- Il Centro di controllo è **semitrasparente sulla scena reale sottostante**: quando è aperto sulla Home lascia intravedere **il wallpaper effettivo dell'utente**, senza immagini né disegni aggiunti da Glass. Un velo scuro traslucido (`Qt.rgba(0.07, 0.08, 0.15, 0.48)`) conserva il contrasto; solo la modalità ad alto contrasto usa sfondo opaco. Il gradiente delle anteprime Qt è uno **sfondo Home fittizio sotto il pannello**, non un asset della shell.
- Sono stati rimossi gli assegnamenti non supportati che hanno bloccato la 0.7. I test statici ne impediscono il reinserimento, senza sostituire un avvio completo del sistema.
- L'ora viene disegnata a sinistra della riga delle icone, per evitare che l'ordine cambi con la posizione dell'indicatore data/ora. Nella barra compatta restano batteria e icone coerenti con gli stati pubblicati dai servizi.
- È previsto un **mascheramento grafico provvisorio** nero sull'area delle due fotocamere, mentre le icone hanno una fascia riservata. Questo non sostituisce il cutout reale di DeviceInfo e **richiede ancora una foto di verifica** sul Galaxy S10+.
- Le notifiche di conferma volume riconoscibili tramite l'hint nativo `x-lomiri-private-synchronous` hanno un nuovo riquadro scuro con progressione reale; gli avvisi di sicurezza sul volume e le notifiche normali restano gestiti da Lomiri. Il risultato visivo necessita di una prova sul telefono.
- L'azione Bluetooth e i pulsanti inferiori non sono stati dichiarati riparati: serve individuare precisamente il comando non riconosciuto dal modello degli indicatori o dal relativo servizio.

Eseguire dalla cartella `Lomiri-Glass` estratta dal pacchetto 0.8, **senza Git e senza scrivere in `/usr/share/lomiri`**:

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /usr/share/lomiri \
  --output "$HOME/lomiri-glass-qml-stage-v08"

sudo python3 scripts/lomiri_glass_trial_v08.py check
```

Eseguire `trial` soltanto dopo aver confermato **Lomiri originale ripristinato**, con `ready_for_timed_trial: true`, telefono carico e recupero manuale possibile:

```sh
sudo python3 scripts/lomiri_glass_trial_v08.py trial
```

Il timer indipendente tenta il ripristino dopo **600 secondi**; per richiederlo prima, da un terminale disponibile: `sudo python3 scripts/lomiri_glass_trial_v08.py restore`. La UI può rendere inutilizzabile temporaneamente il terminale e il ripristino grafico autonomo non è ancora confermato sul dispositivo: può servire un reboot. Il controllo 0.8 rifiuta i dati runtime della 0.7 se manca `ROLLBACK_OK`; non sovrapporre le prove.

## Interazione

| Gesto o elemento | Comportamento |
| --- | --- |
| Discesa dalla metà sinistra del bordo superiore | Apre la vista Notifiche. La vista viene scelta all'inizio del gesto. |
| Discesa dalla metà destra | Apre la vista Controlli. |
| Due pulsanti circolari Notifiche / Controlli nel pannello | Cambiano vista; sostituiscono la precedente fascia di schede, troppo ingombrante. |
| Tocco su un controllo disponibile | Invia una richiesta al servizio; il colore e lo stato cambiano quando risponde il servizio. |
| Pressione prolungata su un controllo | Apre il corrispondente pannello Lomiri con le opzioni complete. |
| Cursori verticali | Regolano luminosità e volume con valori normalizzati e richieste limitate durante il trascinamento. |
| Pulsante di chiusura / maniglia inferiore | Chiude tramite il meccanismo nativo del pannello. |
| Telefono bloccato, greeter, schermo esterno o modalità desktop | Usa l'interfaccia originale e le sue regole di accesso. |

## Barra superiore e indicatori

La barra persistente è inclusa nel redesign. Rimangono le istanze native `IndicatorItem` e `ActionRootState` di Lomiri. Dalla **0.9**, quando il pannello è chiuso, vengono mostrati in regioni indipendenti **ora, icone per cui il servizio segnala attività rilevante e batteria prima delle fotocamere**. Le altre voci e azioni continuano a esistere nel pannello originale espanso. Le icone compatte sono in tinta chiara, senza la precedente fila di cerchi. La selezione si basa sui nomi effettivi pubblicati dagli indicatori: un nome non riconosciuto viene nascosto dalla barra compressa, non convertito in un falso stato.

L'icona messaggi mostra un puntino azzurro **soltanto quando il servizio emette `indicator-messages-new`**. L'indicatore originale di Lomiri può mostrare altri stati che non costituiscono necessariamente nuove notifiche: non viene aggiunto un conteggio numerico fittizio. Un tocco breve sull'icona messaggi apre la vista Notifiche; il trascinamento dal bordo superiore resta affidato ai riconoscitori di Lomiri. Privacy e contenuti bloccati non vengono modificati.

**Galaxy S10+ e foro delle fotocamere:** il codice preserva il pannello nativo `WithCutouts`, il suo `DisplayCutoutsModel` e il posizionamento anticollisione anche con icone di diversa larghezza. Il report raccolto sullo smartphone il 22 ottobre 2026 ha confermato **9/9 file Lomiri corrispondenti**, ma `device-info` restituisce `Unknown prop` per le chiavi `DisplayCutoutsCollapsed`, `DisplayCutoutsCollapsedLight`, `DisplayCutoutsExpanded` e `CollapsedPanelHeight`. Oggi Lomiri sceglie quindi la variante `WithoutCutouts`, come confermano anche le fotografie: alcune icone e l'orologio sono dietro il foro.

La cartella [`cutout/`](cutout/) contiene una **prima proposta di esclusione 1080 0 360 210**, ricavata da due fotografie dello schermo in verticale, con margini conservativi. Rimane **una stima, non una misura geometrica validata sul display**. Il 23 ottobre l'utente ha letto entrambi i file DeviceInfo reali: la mappatura `beyond2lte` è uguale in `/etc/deviceinfo` e nell'overlay Halium. La 0.9 non modifica DeviceInfo: riserva temporaneamente il **27% destro** della barra alle fotocamere, pone la batteria subito prima e usa **7,8 unità griglia** in altezza per un test sullo schermo. Questa correzione pratica non sostituisce la calibrazione fisica, soprattutto in orizzontale. Le coordinate proposte sono in pixel fisici. Vedere [la documentazione ufficiale UBports](https://docs.ubports.com/en/latest/porting/configure_test_fix/device_info/DisplayCutouts.html).

## Lingue e adattamento allo sfondo

L'interfaccia legge `i18n.language` da Lomiri; le etichette personalizzate seguono la lingua selezionata e cambiano anche a runtime. Sono incluse traduzioni di inglese, italiano, francese, tedesco, spagnolo e portoghese, con ritorno all'inglese nelle altre lingue finché non saranno aggiunte le rispettive traduzioni. I pannelli e i messaggi nativi conservano le traduzioni di sistema già installate, senza forzarli in italiano. La stringa di anteprima Qt usa appositamente `it_IT` e non rappresenta la configurazione obbligata sul telefono.

La palette Glass privilegia **un velo semitrasparente sopra la scena reale**, anche quando il tema Lomiri è chiaro. Le schede restano traslucide; il progetto **non campiona i pixel del wallpaper** né applica uno shader di blur supplementare, per limitare il carico grafico del port. Se è visibile la Home, apparirà la sua immagine; altrimenti si vedrà l'app sottostante. Contrasto e composizione devono essere verificati sull'S10+.

Nella 0.8 i controlli principali sono in quattro schede compatte, come nel concept: Wi-Fi, Bluetooth, dati mobili e modalità aereo. Seguono una scheda audio/riproduzione **che apre il menu audio originale, senza inventare metadati musicali**, due cursori verticali per luminosità/volume e sei pulsanti per silenzioso, rotazione e le principali pagine native. I due pulsanti reali di stato rimangono distinti dai collegamenti alle pagine. La disponibilità di un comando nella UI non dimostra che una funzione hardware del port abbia superato il collaudo.

Il comando Bluetooth usa ancora il parametro Booleano previsto da `bluetooth-enabled`. La 0.8 **attende la conferma del servizio**: dopo 3,2 secondi, se lo stato non cambia, mostra un errore esplicito anziché simulare un'accensione riuscita. La mancata attivazione osservata nelle prove precedenti rimane da diagnosticare sul telefono.

La luminosità automatica continua a essere gestita dal sistema: quando è attiva il cursore manuale è bloccato. Il volume passa dall'indicatore sonoro, mantenendo gli avvisi nativi. Un cambiamento della politica del volume interrompe il trascinamento e impedisce di reinviare il valore rifiutato.

## Notifiche e privacy

La cronologia usa lo stesso `MenuContent`, lo stesso modello degli indicatori e gli stessi `MessageMenuItemFactory` di Lomiri. Le notifiche vengono presentate con spaziatura e riquadri arrotondati; apertura, rimozione, raggruppamenti e risposte supportate continuano a usare le azioni native. Non viene creato un secondo archivio dei messaggi né viene usato il modello temporaneo dei popup come cronologia.

`Shell.qml` mantiene intatte le condizioni `enableIndicatorsWhileLocked`, `hideNotificationContentWhileLocked`, i profili `phone_greeter`/`desktop_greeter` e i meccanismi di autenticazione. Il nuovo pannello è caricato soltanto sullo schermo principale, nella sessione telefonica sbloccata. Una transizione a greeter/desktop chiude l'interazione in corso. Le richieste dei controlli vengono bloccate anche durante i dialoghi e gli avvisi modali nativi.

Queste proprietà sono state controllate nel codice; il comportamento completo del blocco schermo e delle notifiche reali richiede ancora una sessione Lomiri sul dispositivo.

## Integrazione

- `qml/Glass/`: componenti dell'interfaccia, icone di stato, traduzioni, contenitore Lomiri e adattatore ai servizi.
- `integration.patch`: modifiche a **26** file upstream, comprese Home/Greeter/Launcher/Spread, le notifiche/OSD, `IndicatorItem.qml` e entrambe le varianti del pannello, con e senza cutout.
- `upstream.lock.json`: revisione sorgente, hash dei file originali, della patch e del modulo.
- `upstream-api-evidence.json`: sorgenti primarie e dettagli dei contratti dei servizi.
- `preview/`: esecuzione e rendering della UI in Qt 5 con stati dichiaratamente simulati.
- `tests/`: prove del comportamento QML e delle azioni native sul bus di test.
- `../../scripts/lomiri_glass.py`: verifica di compatibilità e preparazione di una nuova copia della shell.

Il riferimento Lomiri è il ramo `ubports/24.04-2.x`, commit `0bd07c68b7ab8dee5720516c7549dff8992995c6`. **Non si assume che questo commit coincida con i pacchetti del telefono.** La preparazione della RC4 richiede che tutti i **26 originali** corrispondano esattamente ai rispettivi hash; una differenza interrompe l'operazione. In precedenti prove S10+ ne erano stati confermati 11: il nuovo set completo non è ancora stato letto dal telefono.

Non sono richieste nuove librerie compilate per l'interfaccia: si usano QtQuick 2.15, Lomiri.Components 1.3, QMenuModel 1.0 e GSettings già impiegati dalla shell. Il primo profilo grafico evita un ulteriore passaggio di blur in tempo reale e usa effetti ridotti. Prestazioni GPU, tempi di apertura, consumo e sospensione rimangono da misurare sull'S10+.

## Prima verifica sul telefono

Dalla cartella estratta del pacchetto o dalla radice del repository:

```sh
python3 scripts/lomiri_glass.py probe \
  --qml-root /usr/share/lomiri \
  --output lomiri-glass-compatibility.json
```

Il comando legge versioni dei pacchetti, architettura, versione del sistema, hash dei file QML e, tramite `device-info` quando presente, soltanto i parametri relativi al cutout. Scrive esclusivamente il report richiesto; non richiede `sudo`, non riavvia la shell e non modifica il sistema. Non raccoglie messaggi, nomi delle reti, identificativi radio o registri di sessione. Per ripetere la prova scegliere un nuovo nome di report: i file esistenti non vengono sovrascritti.

Un risultato non compatibile è un dato utile: il report permette di individuare la versione effettiva e adattare la patch. **Non applicare la patch manualmente aggirando il confronto degli hash.**

### Preparazione isolata del profilo S10+ (passo successivo)

Sul telefono, con lo ZIP estratto e nella cartella `Lomiri-Glass`, eseguire **senza sudo**:

```sh
python3 scripts/lomiri_glass_cutout.py stage \
  --output "$HOME/lomiri-glass-cutout-stage"
```

Si ottengono un report JSON, la bozza di DeviceInfo completa e due copie esatte degli originali. Lo script valida i due profili realmente presenti, ne confronta il contenuto e rifiuta aggiunte di proprietà già definite, strutture sconosciute, link simbolici e destinazioni preesistenti. Non installa nulla. **Non copiare ancora il candidato in `/etc` o `/opt`, non riavviare Lomiri:** prima occorre controllare il report sui montaggi e mettere alla prova un percorso di ripristino indipendente dalla sessione grafica. La disposizione sul foro frontale e in orizzontale va poi calibrata sul telefono.

## Preparazione della shell per sviluppo, anche senza Git

Con una copia locale del sorgente upstream verificato:

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /percorso/lomiri \
  --output out/lomiri-glass-prepared
```

La directory padre dell'output deve esistere; l'output deve essere nuovo. Il comando copia l'albero QML, applica la patch nella copia e aggiunge il modulo. Produce `prepared-manifest.json` con gli hash effettivi. Il sorgente originale resta intatto. Sono rifiutati collegamenti simbolici, percorsi inattesi, patch o moduli alterati e output annidati nel sorgente. Un errore durante la preparazione rimuove soltanto l'output appena creato.

**Galaxy S10+ con Ubuntu Touch:** non è necessario installare Git né rimontare la root in scrittura. Per una prova della vecchia 0.8, dopo averne estratto lo ZIP, dalla cartella `Lomiri-Glass` si usava:

```sh
python3 scripts/lomiri_glass.py prepare \
  --source /usr/share/lomiri \
  --output "$HOME/lomiri-glass-qml-stage-v08"
```

L'implementazione usa soltanto la libreria standard di Python 3: controlla gli SHA-256 originali prima di avviare la preparazione, applica esclusivamente gli hunk della patch verificata dal lock e controlla i contenuti di tutte le righe di contesto. Accetta soltanto piccoli scostamenti dei numeri di riga (massimo 24) quando **l'intero contesto è identico**, senza applicazione approssimativa. Tutti i file vengono controllati prima della scrittura; un errore sul nuovo albero comporta la sua rimozione, non la modifica dei sorgenti di sistema.

Il 23 ottobre la copia di sviluppo è stata preparata su host senza invocare Git e i 9 file modificati sono risultati byte per byte identici a una seconda copia ottenuta con `git apply`. Questa prova non certifica che il risultato funzioni sulla GPU, sul pannello o sulla sessione del telefono. Finché il ripristino temporizzato e indipendente non sarà verificato, **non copiare i file in `/usr/share/lomiri`, non montarli e non riavviare la shell**.

Un ulteriore test sul telefono ha verificato lo **smontaggio automatico di un bind mount isolato** mediante timer root, con risultato `RECUPERO_AUTOMATICO_OK`. La prima prova Glass 0.5 ha poi mostrato sul telefono l'interfaccia realmente eseguita, con i difetti descritti sopra. **Non è arrivato un rapporto esplicito che certifichi il completo ripristino di LightDM alla scadenza dei 150 secondi.**

La nuova prova `scripts/lomiri_glass_trial_v08.py` controlla l'albero QML v08 file per file contro la baseline S10+, ne crea una copia privata in `/run`, imposta un timer di ripristino root di **600 secondi (10 minuti)** prima del bind mount temporaneo e soltanto dopo programma il riavvio di LightDM. Controlla inoltre che un eventuale precedente tentativo 0.7 abbia un esito di rollback noto. Non scrive sulla partizione di sistema o su DeviceInfo. Un guasto della shell potrebbe comunque richiedere riavvio o recovery: il test non è privo di rischi.

Dopo la preparazione, verificare **prima**:

```sh
sudo python3 scripts/lomiri_glass_trial_v08.py check
```

Solo se `ready_for_timed_trial` è `true` e il telefono dispone di un percorso di recupero:

```sh
sudo python3 scripts/lomiri_glass_trial_v08.py trial
```

Per chiedere un ripristino anticipato, da un terminale funzionante:

```sh
sudo python3 scripts/lomiri_glass_trial_v08.py restore
```

Al termine dei dieci minuti, il file `/run/lomiri-glass-v08-one-shot/rollback-result` contiene `ROLLBACK_OK` soltanto se lo script ha completato sia lo smontaggio sia il riavvio LightDM. Conservare anche il risultato di `findmnt -T /usr/share/lomiri` e il feedback visivo. Dopo un riavvio fisico il file in `/run` si perde. Gli script delle versioni precedenti non devono essere usati per l'albero v08.

Questa operazione **prepara file**, non installa, non monta overlay e non esegue Lomiri. Il pacchetto non contiene un installer che sostituisca automaticamente `/usr/share/lomiri`: versione installata e percorso di ripristino vanno validati prima del primo test della shell. Per la prova sul telefono sarà necessario un overlay reversibile o un pacchetto compatibile, con ritorno alla shell originale verificato.

## Prove riproducibili

L'interfaccia è verificata con PyQt5/Qt 5.15 e rendering software; le schermate di anteprima riportano **STATI SIMULATI**. Vedere [preview/README.md](preview/README.md).

```sh
python3 -m unittest discover -s tests -p test_lomiri_glass_prepare.py -v

/percorso/venv/bin/python shell/lomiri-glass/tests/test_qml_surface.py \
  --report out/lomiri-glass/qt5-tests.json

/percorso/venv/bin/python shell/lomiri-glass/tests/test_status_icons.py

python3 shell/lomiri-glass/tests/test_cutout_estimate.py

python3 -m unittest discover -s tests -p 'test_lomiri_glass_cutout.py' -v

/percorso/venv/bin/python shell/lomiri-glass/tests/test_native_backend.py

/percorso/venv/bin/python shell/lomiri-glass/tests/test_panel_host.py \
  --source out/lomiri-glass-prepared \
  --report out/lomiri-glass/integration-host-tests.json
```

L'ultima prova richiede il plugin nativo `QMenuModel` per Qt 5, `dbus-run-session` e le librerie GLib/GIO; può usare un plugin estratto localmente tramite `LOMIRI_TEST_QML_IMPORT_PATH`. Crea un bus privato e servizi GAction controllati. Il modulo GSettings e i servizi hardware sono simulati; il binding QMenuModel e la serializzazione D-Bus sono reali. Le prove verificano parametri delle azioni, stato autorevole, rifiuto dei controlli disabilitati, disconnessione/riconnessione e tipi numerici dei cursori. La politica acustica reale è mantenuta tramite il servizio originale, ma la sua risposta fisica non è collaudata da queste fixture.

Le evidenze e i limiti della verifica sono nel [record di sviluppo](../../docs/evidence/lomiri-glass-2026-10-22.json). Non sono stati avviati workflow GitHub Actions per questa fase.

Il test del contenitore esegue i componenti integrati per entrambe le varianti del pannello. Verifica anche che il contenuto nativo e il suo modello sopravvivano al cambio di contenitore e allo scaricamento della nuova UI. Tema, riconoscitore dei gesti, barra e servizi sono fixture: non equivale all'esecuzione della shell completa.

Per produrre il pacchetto con le anteprime e i report già generati:

```sh
python3 scripts/package_lomiri_glass.py \
  --output out/Lomiri-Glass-0.8-dev.zip \
  --source-commit COMMIT_COMPLETO_DEI_SORGENTI
```

Lo ZIP comprende sorgenti, script di verifica, documentazione, anteprime e manifest degli hash. Non include dipendenze binarie, firmware o un installer.

## Riferimenti e licenza

- [Apple: iOS 27, design e Liquid Glass](https://www.apple.com/os/ios/).
- [Apple: uso e personalizzazione del Centro di Controllo](https://support.apple.com/guide/iphone/use-and-customize-control-center-iph59095ec58/ios).
- [Lomiri upstream](https://gitlab.com/ubports/development/core/lomiri/-/tree/0bd07c68b7ab8dee5720516c7549dff8992995c6).
- Le altre sorgenti primarie sono elencate con revisioni e percorsi in `upstream-api-evidence.json`.

Il nuovo modulo è distribuito con licenza GPL-3.0-only. I file upstream modificati conservano le rispettive licenze e attribuzioni. Le copie delle licenze sono in `COPYING` e `COPYING.LGPL`. Non sono inclusi font, loghi o asset proprietari Apple.
