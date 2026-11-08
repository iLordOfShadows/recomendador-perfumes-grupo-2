"""Mide costo en tokens y latencia del analista con usuarios reales de la base.

Para N usuarios: 1 análisis automático + 1 pregunta de seguimiento que obliga a re-consultar el modelo.
Uso:  GEMINI_API_KEY=... python -m pruebas.medir_costo [N]
Escribe pruebas/costo_latencia.csv y pruebas/costo_latencia.md.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

from src.analista import Analista, MODELO_DEFECTO, MODELOS, crear_cliente
from src.sistema import Sistema

PREGUNTA = "¿Qué recomendaría el modelo si además esta persona comprara Nautica Voyage?"


def main(n=10, modelo=MODELO_DEFECTO, semilla=42):
    variable = "GEMINI_API_KEY" if MODELOS[modelo]["proveedor"] == "gemini" else "ANTHROPIC_API_KEY"
    cliente = crear_cliente(modelo, os.environ[variable])
    s = Sistema()
    usuarios = np.random.default_rng(semilla).choice(sorted(s.secuencias), n, replace=False)
    filas = []
    for u in usuarios:
        seq = s.secuencias[int(u)]
        an = Analista(s, cliente, modelo)
        an.nueva_sesion(seq[:-1], seq[-1])
        for tipo, f in [("análisis automático", an.analisis_automatico), ("chat con re-consulta", lambda: an.preguntar(PREGUNTA))]:
            try:
                r = f()
                filas.append({"usuario": int(u), "tipo": tipo, "tokens_entrada": r["tokens_entrada"],
                              "tokens_salida": r["tokens_salida"], "costo_real_usd": r["costo_usd"],
                              "costo_equivalente_usd": r["costo_equivalente_usd"], "latencia_s": r["latencia_s"],
                              "herramientas": len(r["herramientas"]), "ok": True})
            except Exception as e:
                filas.append({"usuario": int(u), "tipo": tipo, "ok": False, "error": str(e)[:200]})
            if MODELOS[modelo]["gratis"]:
                time.sleep(6)
        print(f"usuario {u}: listo")
    df = pd.DataFrame(filas)
    df.to_csv("pruebas/costo_latencia.csv", index=False)
    ok = df[df["ok"]]
    res = ok.groupby("tipo").agg(llamadas=("latencia_s", "size"), tokens_entrada=("tokens_entrada", "mean"),
                                 tokens_salida=("tokens_salida", "mean"), costo_equiv_usd=("costo_equivalente_usd", "mean"),
                                 latencia_mediana_s=("latencia_s", "median"),
                                 latencia_media_s=("latencia_s", "mean"),
                                 latencia_p90_s=("latencia_s", lambda x: float(np.percentile(x, 90))))
    p = MODELOS[modelo]
    texto = (f"# Costo y latencia del analista\n\n- Modelo: `{modelo}` · {n} usuarios de la base · fecha "
             f"{pd.Timestamp.now():%Y-%m-%d %H:%M}\n- Precio de referencia (plan pagado): US$ {p['entrada']} / millón de "
             f"tokens de entrada y US$ {p['salida']} / millón de salida. Costo real con la llave gratuita: "
             f"US$ {ok['costo_real_usd'].sum():.4f}.\n- Llamadas fallidas: {int((~df['ok']).sum())}\n\n"
             + res.round(4).to_markdown() +
             f"\n\n**Costo equivalente por sesión** (análisis + 1 pregunta): US$ "
             f"{ok.groupby('usuario')['costo_equivalente_usd'].sum().mean():.5f}. "
             f"Por 1.000 sesiones: US$ {1000 * ok.groupby('usuario')['costo_equivalente_usd'].sum().mean():.2f}.\n")
    open("pruebas/costo_latencia.md", "w", encoding="utf-8").write(texto)
    print(texto)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
