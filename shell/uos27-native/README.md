# uOS27 — superfici native oltre la shell

Il tema uOS27 non deve sostituire input, autenticazione o servizi di sistema.
Questo modulo prepara esclusivamente interventi di presentazione su due
componenti indipendenti dalla shell Lomiri.

## Tastiera Maliit

- Repository originale: `ubports/lomiri-keyboard`, ref `ubports/24.04-2.x`,
  commit `85e1a77b2653f8cd28d8bd1308dbd6c577713892`.
- Le risorse QML sono file installati in
  `/usr/share/maliit/plugins/lomiri-keyboard`.
- La patch sorgente riproducibile è `patches/keyboard.patch`; le palette
  corrispondenti sono `keyboard/uOS27.json` e `keyboard/uOS27-Dark.json`.
- `scripts/uos27_native_inventory.py` permette un inventario **di sola
  lettura** sul dispositivo: confronta tre file chiave con gli SHA-256 della
  versione pin, segnala eventuali conflitti sui nomi dei temi e riferisce
  soltanto le versioni dei pacchetti pubblici. Non registra testo digitato,
  password o dati personali. Un risultato compatibile abilita soltanto la
  preparazione separata, **non autorizza l'installazione**.
- Le palette chiara e scura di questa directory e il piccolo intervento a `Keyboard.qml`
  e `keys/CharKey.qml` cambiano colori, spaziature e arrotondamenti, senza
  intervenire su `PressArea`, composizione, predizione, layout delle lingue,
  chiavi inviate o callback del servizio di immissione.
- Il colore segue il tema chiaro/scuro della tastiera già scelto dal sistema;
  l'utente non perde la propria preferenza. Il PIN della schermata di blocco
  **non dipende da questo tema**: il
  collegamento con LightDM e il `LoginList` devono essere provati a parte.
- Il preparatore `scripts/prepare_uos27_keyboard_stage.py` crea una copia
  **completa** dell'albero effettivamente installato, con un manifesto di
  tutte le impronte SHA-256: tre QML modificati, due palette aggiunte, tutti
  gli altri file identici. Non crea mount né scrive nel sistema. Con l'albero
  sorgente bloccato usato per i test locali: **74 file originali, 76 preparati**;
  il conteggio della reale installazione S10+ va letto sul dispositivo.
- `scripts/uos27_trial_v014.py` è soltanto un **runner di sviluppo** per la
  shell più la tastiera, con un unico timer indipendente da 600 secondi per
  smontare entrambi i bind mount nell'ordine inverso e riavviare LightDM.
  La modalità `trial` è bloccata per impostazione predefinita e richiede
  l'esplicita accettazione di un collaudo **parziale**: non è quindi il
  pacchetto unico finale richiesto dal tester. Il sistema di sblocco PIN
  utilizza ancora il Greeter LightDM nativo, **non** la tastiera Maliit.

## Impostazioni

- Repository originale: `ubports/lomiri-system-settings`, ref
  `ubports/24.04-2.x`, commit
  `2f4654cf8b32eac7d553910003d1072dfb6d11b3`.
- I file di `src/qml` vengono incorporati dal compilatore Qt nel programma
  tramite `QT5_ADD_RESOURCES(system-settings-resources ui.qrc)`. **Non basta**
  copiare o montare questi file sulla partizione `/usr/share` per vedere
  il risultato. La variante di Impostazioni e solo una patch sorgente; per
  provarla è necessaria una ricompilazione ARM64 del pacchetto. La build
  effettiva **è riuscita il 23/10/2026** usando GitHub Actions ARM64:
  [run 40025735292](https://github.com/MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus/actions/runs/40025735292).
  Non è stata installata né eseguita sul telefono: l'integrazione avviene
  soltanto tramite il triplo overlay temporaneo di RC6, con controllo stretto
  della versione delle librerie già installate.
- `patches/system-settings.patch` è stata verificata con `git apply --check`
  sull'esatto commit dichiarato; contiene solo modifiche di stile. Comprende
  un riquadro arrotondato dietro le icone delle voci di menu, mantenendo le
  icone e le azioni originali; ora aggiunge ritmi di griglia più compatti e
  una tinta coerente nelle pagine dei plugin. La verifica avviene su
  **7 QML sorgenti**, ma
  non dimostra il risultato visivo nell'applicazione compilata sul telefono.
- `scripts/prepare_uos27_settings_build.py` ricopia soltanto il contenuto
  tracciato dal commit upstream immutato, ricostruisce la patch e produce
  `prepared-manifest.json`, `BUILD-ARM64.txt` e un'impronta sull'**intero
  sorgente preparato**, non soltanto sui sette file visivi. È disponibile
  anche una verifica **di sola lettura** dell'output:

  ```bash
  python3 scripts/prepare_uos27_settings_build.py \
    --source /percorso/lomiri-system-settings \
    --output /percorso/settings-preparati
  python3 scripts/prepare_uos27_settings_build.py \
    --output /percorso/settings-preparati --verify
  ```

  Nella fixture del computer il verificatore ha riconosciuto **791 file**;
  il sorgente è stato poi **compilato su un runner nativo ARM64 isolato**,
  con dipendenze UBports del canale 24.04-2.x. Nessuna installazione su S10+.
- Dopo la compilazione il controllo offline
  `scripts/audit_uos27_settings_deb.py /percorso/lomiri-system-settings_arm64.deb`
  legge metadati e contenuto del pacchetto senza installarlo o eseguire script
  di manutenzione. Rifiuta il pacchetto sbagliato, un'architettura diversa da
  `arm64`, un eseguibile assente/non eseguibile o un ELF non AArch64 e registra
  i due SHA-256. I manifest della build collegano ora il pacchetto alle
  revisioni sorgenti immutabili, ma **non** provano che i plugin preinstallati
  sul Galaxy siano ABI-compatibili o che la UI funzioni sul dispositivo.

- `scripts/prepare_uos27_settings_trial.py` isola il **solo eseguibile
  AArch64** dal `.deb` verificato; non esegue maintainer script e non altera
  i pacchetti installati. `scripts/uos27_trial_v015.py` verifica gli SHA-256
  del `.deb` e dell'eseguibile, la presenza dei plugin nativi della versione
  **1.3.2** e lo stato delle altre due superfici. Il timer di sistema
  ripristina shell, Maliit e Settings dopo 600 secondi, o riavvia in caso
  di errore durante il ripristino grafico. Eseguire solo dopo un `check`
  completo e con una via di emergenza già disponibile.

## Sicurezza e collaudo

Il preparatore confronta ogni origine con gli SHA-256 esatti della revisione
pubblicata prima di emettere la variante. Le uscite sono copie isolate.
Questo modulo **non** include un installatore automatico, non effettua mount
e non e ancora convalidato sul Galaxy S10+. Nessun test host equivale alla
verifica del touch sul dispositivo o al corretto avvio della tastiera.

## Riferimenti visivi

Le scelte di proporzioni e gerarchia riprendono le indicazioni ufficiali per
la separazione fra contenuto e controlli e per i gruppi del Centro di controllo:
[Apple — Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass)
e [Apple — Centro di Controllo su iOS 27](https://support.apple.com/it-it/guide/iphone/iph59095ec58/27/ios/27).
Sono riferimenti di comportamento, **non** librerie, asset o codice Apple.
