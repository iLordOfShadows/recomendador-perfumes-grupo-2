"""Cruza los perfumes de Amazon (data/mapa_items.csv) con fichas olfativas del dataset público de Parfumo
(TidyTuesday 2024-12-10, rfordatascience; origen: Kaggle, Olga G. Miufana). No se hizo scraping propio de Parfumo.
Base del grupo: Excel con esas fichas traducidas
por marca + nombre, y guarda data/fichas_olfativas.csv (notas, acordes, ocasión) para el dashboard.

Uso:  python -m src.fichas ruta/Base_de_datos_perfumes_completa.xlsx
"""
import re
import sys
import unicodedata

import pandas as pd

VACIAS_MARCA = {"perfumes", "perfume", "parfums", "parfum", "fragrances", "fragrance", "inc", "the", "by",
                "cosmetics", "beauty", "paris", "co", "ltd", "llc", "de", "di"}
VACIAS_NOMBRE = {"eau", "de", "parfum", "toilette", "cologne", "extrait", "edt", "edp", "edc", "spray", "for", "pour",
                 "man", "men", "woman", "women", "homme", "femme", "him", "her", "the", "by", "and", "y", "intense"}


FEM = {"femme", "woman", "women", "her", "she", "donna", "mujer", "girl"}
MASC = {"homme", "man", "men", "him", "he", "uomo", "hombre", "boy"}


def genero_nombre(nombre):
    t = set(normalizar(nombre).split())
    return "Mujer" if t & FEM else "Hombre" if t & MASC else None


def normalizar(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fichas(ruta_excel, ruta_items="data/mapa_items.csv", salida="data/fichas_olfativas.csv"):
    x = pd.read_excel(ruta_excel)
    # Solo las fichas que vienen del dataset público de Parfumo redistribuido por TidyTuesday (2024-12-10).
    # Se excluyen las 174 filas agregadas a mano desde la web (perfumes 2025-2026 y otras fuentes).
    anio = pd.to_numeric(x["Año"], errors="coerce").fillna(0)
    x = x[(anio < 2025) & x["Enlace"].astype(str).str.contains("parfumo.com", regex=False)]
    items = pd.read_csv(ruta_items)

    x["marca_tok"] = x["Marca"].map(lambda m: frozenset(normalizar(m).split()) - VACIAS_MARCA)
    x["nombre_tok"] = [frozenset(normalizar(p).split()) - VACIAS_NOMBRE - mt
                       for p, mt in zip(x["Producto"], x["marca_tok"])]
    # "intense" distingue versiones (Club de Nuit vs. Club de Nuit Intense): se conserva si está en el nombre
    x["nombre_tok"] = [nt | ({"intense"} & set(normalizar(p).split())) for nt, p in zip(x["nombre_tok"], x["Producto"])]
    x["genero"] = x["Producto"].map(genero_nombre)
    x = x[x["marca_tok"].apply(len) > 0]
    x = x[x["nombre_tok"].apply(lambda t: len(t) > 0 and len("".join(t)) >= 4)]
    # Una ficha por (marca, nombre): la que tiene acordes y más votos
    x = (x.assign(tiene=x["Acordes"].notna(), votos=x["Votos"].fillna(0))
          .sort_values(["tiene", "votos"], ascending=False)
          .drop_duplicates(["marca_tok", "nombre_tok"]))
    por_marca = {}
    for j, mt in zip(x.index, x["marca_tok"]):
        por_marca.setdefault(mt, []).append(j)

    filas = []
    for _, it in items.iterrows():
        titulo = set(normalizar(it["titulo"]).split())
        marca_amz = set(normalizar(it["marca"]).split()) - VACIAS_MARCA
        mejor, mejor_n = None, 0
        for mt, idxs in por_marca.items():
            if not (mt <= titulo or (marca_amz and (mt <= marca_amz or marca_amz <= mt))):
                continue
            for j in idxs:
                nt = x.at[j, "nombre_tok"]
                g = x.at[j, "genero"]
                if g is not None and it["genero"] in ("Mujer", "Hombre") and g != it["genero"]:
                    continue                                   # "pour Femme" no es la versión masculina
                if nt <= titulo and len(nt) > mejor_n:
                    mejor, mejor_n = j, len(nt)
        if mejor is not None:
            f = x.loc[mejor]
            filas.append({
                "idx": it["idx"], "ficha": f"{f['Marca']} — {f['Producto']}", "acordes": f["Acordes"],
                "nota_salida": f["Nota Salida"], "nota_corazon": f["Nota Corazón"], "nota_base": f["Nota Base"],
                "ocasion": f["Ocasión (estimada)"], "concentracion": f["Concentración"],
                "valoracion_parfumo": f["Valoración (0-10)"], "votos_parfumo": f["Votos"], "enlace": f["Enlace"],
            })
    out = pd.DataFrame(filas)
    out.to_csv(salida, index=False)
    pop = items["reseñas_entrenamiento"]
    cubre = items["idx"].isin(out["idx"])
    print(f"Perfumes con ficha: {cubre.mean():.0%} | ponderado por reseñas: {pop[cubre].sum() / pop.sum():.0%} | "
          f"con acordes: {out['acordes'].notna().mean():.0%} de los cruzados")
    return out


if __name__ == "__main__":
    fichas(sys.argv[1])
