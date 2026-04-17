# Legacy tools

Strumenti standalone non integrati con l'applicazione FastAPI.
Conservati per riferimento storico — non eseguire in produzione.

## `xml_pod_cutter.py`

GUI Tkinter Windows per il ritaglio di file XML POD.

**Perché è isolato:**
- È scollegato dal server FastAPI (non viene importato da nessun modulo `app/`).
- Dipende da `tkinterdnd2`, che **non** è in `requirements.txt`.
- Contiene un path di output hardcoded Windows
  (`C:\Users\esterboroni\Desktop\MISURE\Ritaglio XML`) — non portabile.
- Richiede un ambiente desktop con Tk — non eseguibile sul server.

**Come usarlo (se serve, a tuo rischio):**

```powershell
pip install tkinterdnd2
python "tools/legacy/xml_pod_cutter.py"
```

Prima modifica il path di output in cima allo script.
