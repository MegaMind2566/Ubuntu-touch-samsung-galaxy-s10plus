# uOS27 - interfaccia nativa Lomiri

Il progetto precedente e' stato recuperato dal branch storico, commit
`285aef5d3d7a5678dc5812499aa1bf1cc2f0f618`. La [provenienza](RECOVERY-2026-11-05.md)
ricostruisce il lavoro e distingue le vecchie osservazioni RC7/v015, le nuove
revisioni sorgente e le anteprime. **La shell rivista non e' installata o
collaudata sul telefono.** Il port Ubuntu Touch e le sue correzioni restano
separati da questo sorgente candidato.

L'obiettivo confermato e' una riproduzione quanto piu' fedele possibile della
presentazione e delle interazioni iOS 27 su Ubuntu Touch: Home/dock, blocco e
sblocco, Centro di controllo, notifiche, gesti, animazioni e Impostazioni. Il
codice e' Qt Quick/Lomiri nativo, non una dashboard React.

## Stato reale

- Home usa il catalogo nativo e il dock fissato di Lomiri; la revisione corregge
  l'ordine per righe e mantiene pagine orizzontali e ricerca.
- Il Centro di controllo usa l'altezza disponibile; gli stati radio, volume e
  luminosita' provengono dai servizi Ubuntu. I comandi attendono readback e non
  accendono graficamente un hardware che non ha confermato il cambiamento.
- Il backend espone `capabilities` con disponibilita', provenienza e stato.
  `automaticBrightnessProfileVerified` resta false: la preferenza GSettings non
  basta a dimostrare un profilo ALS funzionante. Il progetto del profilo reale
  e' in [tools/automatic-brightness](../../tools/automatic-brightness/README.md).
- LightDM conserva verifica delle credenziali, retry, annullamento e fallback;
  le notifiche riusano il modello filtrato della shell. L'anteprima non verifica
  PIN e non sblocca il dispositivo.
- Il codice recuperato include switcher, OSD/popup, tastiera e Impostazioni come
  lavori distinti; non sono tutti integrati o verificati in una ROM.

Le vecchie note sono in [HISTORY-RC7.md](HISTORY-RC7.md). Non riutilizzare i loro
trial/installer su questa revisione. Il nuovo source lock conserva gli input
upstream e gli hash dei QML correnti per preparazioni riproducibili, senza
costituire compatibilita' o autorizzazione d'installazione sul telefono attuale.

## Anteprima e verifiche gratuite

Il workflow separato `.github/workflows/uos27-preview.yml` usa il runner pubblico
Ubuntu 24.04 standard e pacchetti Qt liberi; nessuna compilazione C++ locale.
Il renderer usa davvero i QML, con catalogo, ora e wallpaper di fixture dichiarati
in ogni cattura. Non legge D-Bus o dati personali del telefono.

```sh
python3 shell/lomiri-glass/tests/test_qml_surface.py --report out/lomiri-glass/surface-tests.json
python3 shell/lomiri-glass/preview/render.py --output out/lomiri-glass/controls
python3 shell/lomiri-glass/preview/render_shell.py --output out/lomiri-glass/shell
```

Qt software non prova rifrazione Liquid Glass, blur/GPU Mali, animazioni sul
telefono, gesti reali, sicurezza LightDM o flusso notifiche in esecuzione. Mancano
ancora integrazione/accettazione sul dispositivo, comportamento delle cartelle,
parita' delle superfici applicative e tutte le funzioni proprietarie iOS/Apple.
La nuova UI non va descritta come clone completo o release pronta.
