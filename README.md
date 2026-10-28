# RENON FLEX per Home Assistant

Versione **1.2.2**, verificata con **Home Assistant Core 2026.6.2 / Python 3.14**.
Integrazione locale per RENON FLEX-LV-EU-6K con Stick Logger LSW-5,
con trasporti Solarman V5 e Modbus TCP.

## Correzione della mappa Modbus

Le versioni 1.0–1.1 assumevano erroneamente che le misure fossero nei registri
PDU 0–6. Una risposta Modbus `Illegal Data Address` conferma che il dispositivo
rifiuta gli indirizzi richiesti: non è un fallimento di apertura della connessione.

La versione 1.2 usa un sottoinsieme del profilo community **RENON Flex IFL** di
[ha-solarman](https://github.com/davidrapan/ha-solarman/blob/main/custom_components/solarman/inverter_definitions/renon_ifl.yaml).
Il profilo pubblico è indicato come testato dal suo autore; non è una specifica
ufficiale RENON. La compatibilità con il firmware dell'inverter dell'utente deve
ancora essere confermata tramite una lettura reale. Se un blocco è rifiutato,
il modulo di configurazione mostra il suo indirizzo preciso.

Tutti gli indirizzi seguenti sono PDU esadecimali, senza offset 40001.
Si usa esclusivamente la funzione Modbus 03 (holding registers).

| Misura | Indirizzo | Conversione |
| --- | --- | --- |
| Tensione FV1 | `0x1690` | uint16 × 0,1 V |
| Corrente FV1 | `0x1691` | uint16 × 0,1 A |
| Tensione FV2 | `0x1692` | uint16 × 0,1 V |
| Corrente FV2 | `0x1693` | uint16 × 0,1 A |
| Potenza FV1 | `0x227F` | uint16 W |
| Potenza FV2 | `0x2281` | uint16 W |
| Tensione rete L1 | `0x3110` | uint16 × 0,1 V |
| Corrente rete L1 | `0x3111` | uint16 × 0,1 A |
| Energia FV prodotta oggi | `0x3153`, `0x3154` | uint32, parola bassa prima, × 0,001 kWh |

La decodifica dei valori a più parole segue il
[parser del profilo originale](https://github.com/davidrapan/ha-solarman/blob/main/custom_components/solarman/parser.py).
Le letture avvengono in cinque blocchi consecutivi sulla stessa connessione,
senza includere indirizzi intermedi non definiti come `0x2280`.
La versione 1.2.1 gestisce il supporto parziale del profilo. Se un blocco viene
rifiutato con il codice Modbus 02, le sue misure risultano **non disponibili**;
le letture degli altri blocchi proseguono. Un indirizzo rifiutato non viene
interrogato a ogni aggiornamento: viene riprovato dopo il ricaricamento
dell'integrazione o il riavvio. Timeout, errori di rete e gli altri codici Modbus
continuano invece a rendere non disponibile tutto l'aggiornamento.

Sul dispositivo dell'utente è stata confermata una lettura riuscita del blocco
`0x1690–0x1693`, seguita dal rifiuto di `0x227F`. Questo conferma il supporto
parziale della mappa, non l'assenza di comunicazione con il logger.
Per identificare l'indirizzo alternativo della potenza FV1 serve ancora una
mappa Modbus compatibile con il firmware effettivo: non è stato inventato un
indirizzo sostitutivo né un valore stimato.

## Installazione e aggiornamento

1. Sostituisci la cartella `/config/custom_components/renon_flex` di Home Assistant
   con `custom_components/renon_flex` contenuta nel pacchetto 1.2.2.
2. Riavvia Home Assistant. Le dipendenze vengono installate automaticamente;
   durante questa prima installazione serve accesso al repository dei pacchetti Python.
3. Apri **Impostazioni → Dispositivi e servizi → Aggiungi integrazione** e cerca
   **RENON FLEX Stick Logger**. Se è già configurata, usa **Riconfigura**.
4. Inserisci l'IP locale del logger e i parametri del protocollo.

L'integrazione integrata chiamata **solarman** è un componente diverso. Un errore
con sorgente `homeassistant.components.solarman.config_flow` e connessione HTTP
alla porta 8080 non proviene da questo componente Solarman V5.

| Campo | Per Stick Logger con Solarman V5 |
| --- | --- |
| Host | Solo l'IP del logger, per esempio `192.168.1.12` |
| Protocollo | Solarman V5 |
| Porta | 8899, se esposta dal firmware del logger |
| ID unità Modbus | 1, salvo diversa configurazione dell'inverter |
| Seriale | Numero numerico dello **Stick Logger**, non dell'inverter |
| Timeout | 15 secondi per operazione, regolabile tra 3 e 60 |

Non inserire `http://`, percorsi o `:8899` nel campo Host.
Per un gateway che espone Modbus TCP nativo, seleziona **Modbus TCP** e la sua
porta, normalmente 502; il seriale non è richiesto. La porta non viene cambiata
automaticamente quando si seleziona il protocollo.

La configurazione prova tutti i blocchi del profilo e crea l'istanza se almeno
una misura è leggibile. Se tutti i blocchi vengono rifiutati, la configurazione
fallisce con un errore di incompatibilità della mappa.
La riconfigurazione conserva le entità esistenti e applica le nuove impostazioni
solo dopo una lettura riuscita. È supportata una sola istanza.

## Sensori e migrazione

Sono disponibili **undici sensori**: le nove misure in tabella, la potenza FV
totale calcolata come somma di FV1 e FV2 e **Potenza FV1 stimata**.
L'aggiornamento avviene ogni 10 secondi.

**Potenza FV1 stimata** calcola `Tensione FV1 (V) × Corrente FV1 (A) = Potenza (W)`
dai valori dello stesso aggiornamento. Funziona anche quando il registro della
potenza FV1 è rifiutato. Per esempio, 360 V × 3 A = 1080 W. Se manca una delle
due misure o la comunicazione fallisce, il sensore diventa non disponibile;
uno zero misurato produce invece correttamente 0 W. È una stima della potenza
continua istantanea del solo canale FV1, prima delle perdite di conversione
dell'inverter, e non un contatore di energia in kWh.
Le misure non supportate dal firmware restano non disponibili, senza zeri
sostitutivi. La potenza totale richiede entrambe le potenze: non viene calcolata
come una somma parziale quando un canale manca. Anche l'energia giornaliera
resta non disponibile se il suo registro è rifiutato.

L'energia giornaliera è ora il contatore dell'inverter, anziché una stima
integrata da Home Assistant. Rimane disponibile ai riavvii perché viene riletta
dal dispositivo e segue l'azzeramento giornaliero effettuato dall'inverter.
Il sensore usa `total_increasing`. La versione 1.2 non usa più il totale stimato
salvato dalle versioni precedenti e non modifica retroattivamente le statistiche.
I vecchi file `.storage/renon_flex.*`, se presenti, non vengono letti.

Sono conservati gli identificativi delle misure esistenti, con nomi più precisi:
CC indica ora esplicitamente FV1 e CA indica la rete L1. Potenza reattiva e stato
inverter non vengono più creati: mancava una corrispondenza affidabile nel
profilo scelto. Eventuali entità residue delle vecchie versioni rimangono
non disponibili e possono essere rimosse dall'interfaccia di Home Assistant.

## Diagnosi

Il modulo mostra il dettaglio dell'errore e lo registra anche senza debug:

- **Connessione rifiutata**: quel tentativo di apertura TCP è stato rifiutato.
- **Nome non risolto**: controlla il campo Host o la risoluzione DNS.
- **Timeout di lettura**: connessione aperta ma nessuna risposta valida entro
  il tempo previsto; verifica protocollo, seriale e ID Modbus.
- **Registri rifiutati**: il dispositivo ha restituito un errore Modbus 02.
  L'indirizzo esadecimale mostrato identifica il blocco non supportato.
  Se altre misure sono supportate, la configurazione prosegue e il blocco
  rifiutato viene segnalato nei registri come `Unsupported register block skipped`.

Dal menu dell'integrazione è possibile **scaricare la diagnostica**: contiene
i blocchi rifiutati e gli elenchi delle misure disponibili e non disponibili,
senza esportare l'indirizzo IP né il seriale del logger.

Evita client contemporanei se il logger accetta una sola connessione.
Per ulteriori dettagli puoi abilitare temporaneamente:

```yaml
logger:
  default: warning
  logs:
    custom_components.renon_flex: debug
```

## Test

Con Python 3.14:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

La suite verifica le API reali di Core 2026.6.2 per configurazione,
riconfigurazione e sensori; usa i veri client Modbus e Solarman contro server
TCP simulati su `127.0.0.1`. Controlla indirizzi, conversioni, ordine delle parole,
riavvio del coordinatore, errori del dispositivo, timeout e chiusura delle
connessioni. Non sostituisce la verifica sul logger fisico dell'utente.
