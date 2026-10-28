# RENON FLEX per Home Assistant

Integrazione locale per RENON FLEX-LV-EU-6K con Stick Logger LSW-5.
Versione 1.1.0, verificata con **Home Assistant Core 2026.6.2 / Python 3.14**.

## Stato del supporto hardware

Il caricamento dell'integrazione in Home Assistant e il trasporto Modbus TCP
sono verificati con test automatici e un server simulato. L'adattatore Solarman
V5 è coperto da test con client simulato. Non è stata eseguita una prova sul
logger fisico dell'utente.

**La mappa dei registri presente nel progetto originale non è verificata con
documentazione RENON.** Rimane configurata in `custom_components/renon_flex/const.py`:
holding registers (funzione 03), indirizzi PDU 0–6, sei misure uint16 con fattore
1 e un registro di stato. Il logger trasporta le richieste; i registri dipendono
dall'inverter e dal firmware. Questa mappa deve essere confrontata con il
protocollo Modbus del FLEX-LV-EU-6K prima di considerare attendibili i valori.
Una connessione TCP riuscita, da sola, non conferma la mappa. Un errore
`Illegal Data Address` può indicare indirizzi non supportati dall'inverter.

Non sono stati sostituiti questi indirizzi con quelli di altri inverter RENON,
perché la loro compatibilità con questo modello non è confermata.

## Installazione

1. Copia la cartella `custom_components/renon_flex` in
   `/config/custom_components/renon_flex` dell'installazione Home Assistant.
   Se aggiorni la versione precedente, sostituisci la cartella dell'integrazione.
2. Riavvia Home Assistant. Le dipendenze vengono installate automaticamente;
   durante questa prima installazione serve accesso al repository dei pacchetti Python.
3. Apri **Impostazioni → Dispositivi e servizi → Aggiungi integrazione** e cerca
   **RENON FLEX Stick Logger**.
4. Inserisci l'IP locale del logger e i parametri del suo protocollo.

| Collegamento | Protocollo nella configurazione | Porta usuale | Seriale |
| --- | --- | --- | --- |
| Logger con Solarman V5 | Solarman V5 | 8899 | Numero numerico del **logger**, non dell'inverter |
| Dispositivo/gateway con Modbus TCP nativo | Modbus TCP | 502 | Non richiesto |

L'ID unità Modbus predefinito è 1; deve corrispondere all'inverter.
La porta è modificabile: selezionare il protocollo non cambia automaticamente
il valore della porta. Per Solarman V5 occorre quindi inserire **8899**.
Il protocollo disponibile dipende dal firmware del logger: il nome LSW-5
non dimostra che Modbus TCP sulla porta 502 sia disponibile.

Le configurazioni create dalla versione 1.0.0 mantengono Modbus TCP e gli
identificativi dei sensori. Per cambiare collegamento, IP o seriale, apri il menu
dell'integrazione e scegli **Riconfigura**. Viene verificata una lettura prima
di applicare la nuova configurazione. È supportata una sola istanza.

## Sensori

Vengono creati otto sensori: potenza attiva (W), potenza reattiva (var),
tensione CC e CA (V), corrente CC e CA (A), stato inverter e stima dell'energia
giornaliera (kWh). Tutti i dati vengono aggiornati ogni 10 secondi.
L'integrazione esegue esclusivamente letture.

L'energia giornaliera è una stima ottenuta integrando i campioni positivi della
potenza attiva: `W × secondi / 3.600.000 = kWh`. L'interpretazione come produzione
richiede che il registro della potenza rappresenti effettivamente quella misura.
Il totale si azzera al primo campione del nuovo giorno nel fuso di Home Assistant.
Viene salvato circa ogni minuto e allo scaricamento/arresto ordinato, quindi
ripristinato ai riavvii nello stesso giorno. Un arresto improvviso può perdere
l'ultimo minuto. I periodi con letture fallite, gli intervalli tra campioni oltre
30 secondi e il tempo con Home Assistant spento non vengono stimati.
Il sensore usa la classe `total_increasing`, compatibile con le statistiche
energetiche di Home Assistant; i dati errati registrati dalla vecchia versione
non vengono corretti retroattivamente.

## Diagnosi della connessione

Se la configurazione fallisce, controlla IP locale, protocollo, porta, ID Modbus,
seriale del logger (per Solarman) e mappa dei registri. Evita altri client
contemporanei se il logger accetta una sola connessione.
Per maggiori dettagli abilita temporaneamente:

```yaml
logger:
  default: warning
  logs:
    custom_components.renon_flex: debug
```

## Verifica dello sviluppo

In un ambiente con Python 3.14:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

I test verificano configurazione e riconfigurazione, caricamento degli otto
sensori con le API effettive di Core 2026.6.2, disponibilità e recupero,
ripristino dell'energia, mezzanotte e cambio dell'ora, errori Modbus,
chiusura delle connessioni e adattatore Solarman. I test Modbus aprono
esclusivamente un server locale temporaneo su `127.0.0.1`.

Riferimenti: [coordinatore di Core 2026.6.2](https://github.com/home-assistant/core/blob/2026.6.2/homeassistant/helpers/update_coordinator.py),
[dipendenza Modbus di Core 2026.6.2](https://github.com/home-assistant/core/blob/2026.6.2/homeassistant/components/modbus/manifest.json),
[protocollo e libreria Solarman V5](https://github.com/jmccrohan/pysolarmanv5).
