import xml.etree.ElementTree as ET
import os
import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from datetime import datetime

# Cartella di output fissa
OUTPUT_DIR = r"C:\Users\esterboroni\Desktop\MISURE\Ritaglio XML"

class XmlPodCutterPro:
    def __init__(self, root):
        self.root = root
        self.root.title("XML POD Cutter PRO")
        self.root.geometry("500x350")

        self.file_path = None

        # Area drag & drop
        self.drop_label = tk.Label(
            root,
            text="Trascina qui il file XML",
            bg="lightgray",
            width=50,
            height=5
        )
        self.drop_label.pack(pady=10)
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.drop_file)

        # Campo POD multipli
        tk.Label(
            root,
            text="Inserisci uno o più POD (uno per riga o separati da virgola):"
        ).pack()
        self.text_pod = tk.Text(root, height=5)
        self.text_pod.pack(pady=5)

        # Bottone estrai
        self.btn_extract = tk.Button(root, text="Estrai POD", command=self.extract)
        self.btn_extract.pack(pady=10)

        # Stato
        self.status = tk.Label(root, text="", fg="green")
        self.status.pack()

    def drop_file(self, event):
        # Gestione path con spazi
        self.file_path = event.data.strip("{}")
        self.drop_label.config(text=os.path.basename(self.file_path))

    def get_pod_list(self):
        raw = self.text_pod.get("1.0", tk.END)
        pods = set()
        for line in raw.splitlines():
            for p in line.split(","):
                p = p.strip()
                if p:
                    pods.add(p)
        return pods

    def extract(self):
        if not self.file_path:
            messagebox.showerror("Errore", "Trascina un file XML")
            return

        pods = self.get_pod_list()
        if not pods:
            messagebox.showerror("Errore", "Inserisci almeno un POD")
            return

        try:
            # Assicuriamoci che la cartella esista
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)

            log_lines = []

            # Parsing XML a flusso
            context = ET.iterparse(self.file_path, events=("start", "end"))
            context = iter(context)
            event, root = next(context)

            found = {pod: False for pod in pods}

            for event, elem in context:
                if event == "end" and elem.tag == "DatiPod":
                    pod_elem = elem.find("Pod")
                    if pod_elem is not None:
                        pod_value = pod_elem.text
                        if pod_value in pods:
                            output_file = os.path.join(OUTPUT_DIR, f"output_{pod_value}.xml")

                            # Creiamo nuovo root e aggiungiamo il DatiPod
                            new_root = ET.Element(root.tag, root.attrib)
                            new_root.append(elem)

                            # Scrittura output XML
                            tree = ET.ElementTree(new_root)
                            tree.write(output_file, encoding="utf-8", xml_declaration=True)

                            found[pod_value] = True
                            log_lines.append(f"{pod_value} -> OK")

                    # libera memoria
                    root.clear()

            # POD non trovati
            for pod, ok in found.items():
                if not ok:
                    log_lines.append(f"{pod} -> NON TROVATO")

            # Scrittura log in UTF-8
            log_file = os.path.join(OUTPUT_DIR, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))

            self.status.config(text=f"Completato! Log: {os.path.basename(log_file)}")
            messagebox.showinfo("Successo", f"Estrazione completata!\nLog: {os.path.basename(log_file)}")

        except Exception as e:
            messagebox.showerror("Errore", str(e))


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = XmlPodCutterPro(root)
    root.mainloop()