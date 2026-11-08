"""Reúne modelo, datos y líneas base. Lo usan el dashboard y las herramientas del analista."""
import os
from collections import Counter

import numpy as np
import pandas as pd

from src.lineas_base import LineasBase
from src import modelo as M


def _limpio(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating,)):
        return round(float(v), 2)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def lista_acordes(texto):
    if not isinstance(texto, str):
        return []
    return [a.strip() for a in texto.split(",") if a.strip()]


class Sistema:
    def __init__(self, raiz="."):
        r = lambda *p: os.path.join(raiz, *p)
        self.modelo, ck = M.cargar_modelo(r("modelos", "sasrec.pt"))
        self.config = ck["config"]
        self.n_items = ck["n_items"]
        self.items = pd.read_csv(r("data", "mapa_items.csv")).set_index("idx")
        fichas = r("data", "fichas_olfativas.csv")
        self.fichas = pd.read_csv(fichas).set_index("idx") if os.path.exists(fichas) else pd.DataFrame()
        sec = pd.read_parquet(r("data", "secuencias.parquet"))
        self.secuencias = {int(u): [int(i) for i in s] for u, s in zip(sec["usuario"], sec["items"])}
        self.fechas = {int(u): list(f) for u, f in zip(sec["usuario"], sec["fechas"])}
        self.metricas = pd.read_csv(r("data", "metricas.csv"), index_col=0)
        self.segmentos = pd.read_csv(r("data", "segmentos.csv"))
        reglas = pd.read_csv(r("data", "reglas.csv")) if os.path.exists(r("data", "reglas.csv")) else None
        self.base = LineasBase([s[:-2] for s in self.secuencias.values()], self.n_items, reglas)
        self.populares = set(self.base.popularidad.index[: int(0.2 * self.n_items)])
        self.corte_largo = int(np.median([len(s) - 1 for s in self.secuencias.values()]))

    # ---------- atributos ----------
    def nombre(self, i):
        return f"{self.items.at[i, 'marca']} · {self.items.at[i, 'titulo']}"

    def ficha(self, i, notas=True):
        it = self.items.loc[i]
        d = {"idx": int(i), "titulo": it["titulo"], "marca": it["marca"], "genero": it["genero"],
             "precio_usd": _limpio(it["precio"]), "valoracion_amazon": _limpio(it["valoracion"]),
             "resenas_entrenamiento": int(it["reseñas_entrenamiento"]),
             "popularidad": "popular (top 20 %)" if i in self.populares else "cola larga"}
        if i in self.fichas.index:
            f = self.fichas.loc[i]
            d["ficha_olfativa"] = {"perfume_parfumo": f["ficha"], "acordes": _limpio(f["acordes"])}
            if notas:
                d["ficha_olfativa"].update({"salida": _limpio(f["nota_salida"]), "corazon": _limpio(f["nota_corazon"]),
                                            "base": _limpio(f["nota_base"]), "ocasion": _limpio(f["ocasion"])})
        else:
            d["ficha_olfativa"] = None
        return d

    def acordes(self, i):
        return lista_acordes(self.fichas.at[i, "acordes"]) if i in self.fichas.index else []

    def buscar(self, texto, k=8):
        t = texto.lower()
        m = self.items["titulo"].str.lower().str.contains(t, regex=False, na=False) | \
            self.items["marca"].str.lower().str.contains(t, regex=False, na=False)
        res = self.items[m].sort_values("reseñas_entrenamiento", ascending=False).head(k)
        return [{"idx": int(i), "marca": r["marca"], "titulo": r["titulo"]} for i, r in res.iterrows()]

    # ---------- modelo ----------
    def recomendar(self, historial, k=10):
        return [{"puesto": p + 1, "idx": i, "puntaje": round(s, 3), "probabilidad": round(pr, 4)}
                for p, (i, s, pr) in enumerate(M.recomendar(self.modelo, historial, k))]

    def atencion(self, historial):
        hist, w = M.atencion(self.modelo, historial)
        return [(int(i), float(x)) for i, x in zip(hist, w)]

    def lineas_base(self, historial, k=10):
        return {"Popularidad": self.base.popular(historial, k), "Reglas (lift)": self.base.reglas_lift(historial, k),
                "Ítem–ítem coseno": self.base.item_item(historial, k)}

    # ---------- perfil olfativo (innovación) ----------
    def perfil_olfativo(self, perfumes, top=6):
        c = Counter()
        con_ficha = 0
        for i in perfumes:
            a = self.acordes(i)
            if a:
                con_ficha += 1
                for pos, x in enumerate(a):            # el primer acorde pesa más que el quinto
                    c[x] += 1 / (1 + 0.25 * pos)
        total = sum(c.values()) or 1
        return {"perfumes_con_ficha": f"{con_ficha} de {len(perfumes)}",
                "acordes": {a: round(v / total, 3) for a, v in c.most_common(top)}}

    def descubrir_por_acordes(self, elegidos, genero=None, excluir=(), k=10, solo_cola_larga=False):
        """Modo sin historial: perfumes cuya ficha comparte más acordes con los elegidos (no usa SASRec)."""
        elegidos = set(elegidos)
        filas = []
        for i in self.fichas.index:
            if i in excluir or (genero and self.items.at[i, "genero"] != genero):
                continue
            if solo_cola_larga and i in self.populares:
                continue
            a = self.acordes(i)
            if not a:
                continue
            puntaje = sum(1 / (1 + 0.25 * p) for p, x in enumerate(a) if x in elegidos)
            if puntaje > 0:
                filas.append((i, puntaje, self.items.at[i, "valoracion"]))
        filas.sort(key=lambda x: (-x[1], -(x[2] if x[2] == x[2] else 0)))
        return [i for i, _, _ in filas[:k]]

    # ---------- asesor guiado (innovación): lo que tienes + lo que buscas ----------
    def notas(self, i):
        """Notas de salida, corazón y base de la ficha (en minúsculas)."""
        if i not in self.fichas.index:
            return set()
        f = self.fichas.loc[i]
        return {x.strip().lower() for c in ("nota_salida", "nota_corazon", "nota_base")
                if isinstance(f[c], str) for x in f[c].split(",") if x.strip()}

    def todas_las_notas(self, minimo=10):
        c = Counter(n for i in self.fichas.index for n in self.notas(i))
        return [n for n, v in c.most_common() if v >= minimo]

    def asesor(self, tengo, genero=None, ocasiones=(), acordes=(), notas=(), precio_max=None, explorar=False, k=5,
               n_candidatos=200):
        """SASRec propone y el CÓDIGO filtra (el LLM no interviene en esta lista).

        1. Candidatos = top-`n_candidatos` de SASRec dado lo que la persona tiene (sin lo que ya tiene).
           Sin perfumes declarados (arranque en frío), los candidatos son los más populares.
        2. Filtros duros, aplicados por el código sobre esos candidatos: género, presupuesto, marcas nuevas, y los
           criterios olfativos pedidos (al menos un acorde pedido, al menos una nota pedida, ocasión).
        3. Orden: el mismo de SASRec. No hay puntaje mixto: el modelo ordena y los filtros solo quitan.
        4. Si pasan menos de k, se completa con candidatos que cumplen los filtros duros y parte de los olfativos,
           marcados como "coincidencia parcial" y también en orden de SASRec.
        """
        tengo = [int(i) for i in tengo]
        excluir = set(tengo)
        if tengo:
            ranking = [r["idx"] for r in self.recomendar(tengo, n_candidatos)]
            prob = {r["idx"]: r["probabilidad"] for r in self.recomendar(tengo, n_candidatos)}
        else:
            ranking = [int(i) for i in self.base.popularidad.index if int(i) not in excluir][:n_candidatos]
            prob = {}
        marcas_tengo = {self.items.at[i, "marca"].lower() for i in tengo}
        acordes, ocasiones, notas = set(acordes), set(ocasiones), {n.lower() for n in notas}
        criterios = int(bool(acordes)) + int(bool(ocasiones)) + int(bool(notas))
        completos, parciales = [], []
        descartados = {"género": 0, "presupuesto": 0, "marca que ya tienes": 0, "criterios olfativos": 0}
        for puesto, i in enumerate(ranking, start=1):
            it = self.items.loc[i]
            if genero and it["genero"] not in (genero, "Unisex"):
                descartados["género"] += 1
                continue
            if precio_max is not None and not (it["precio"] == it["precio"] and it["precio"] <= precio_max):
                descartados["presupuesto"] += 1
                continue
            if explorar and str(it["marca"]).lower() in marcas_tengo:
                descartados["marca que ya tienes"] += 1
                continue
            a, n = set(self.acordes(i)), self.notas(i)
            oc = self.fichas.at[i, "ocasion"] if i in self.fichas.index else None
            ok = {"acordes": sorted(a & acordes), "notas": sorted(n & notas),
                  "ocasion": isinstance(oc, str) and oc in ocasiones}
            cumple = (bool(not acordes or ok["acordes"]) + bool(not notas or ok["notas"])
                      + bool(not ocasiones or ok["ocasion"]))
            fila = {"idx": i, "puesto_modelo": puesto, "prob_modelo": prob.get(i), "coincide": ok,
                    "tiene_ficha": i in self.fichas.index, "parcial": cumple < 3}
            if cumple == 3:
                completos.append(fila)
            else:
                descartados["criterios olfativos"] += 1
                if criterios and cumple >= 2 and fila["tiene_ficha"]:
                    parciales.append(fila)
        lista = (completos + parciales)[:k]
        for n, f in enumerate(lista):
            f["puesto"] = n + 1
            f["motivos"] = self._motivos(f, bool(tengo), acordes, notas, ocasiones, len(ranking))
        return {"recomendaciones": lista, "candidatos": len(ranking), "cumplen_todo": len(completos),
                "descartados": descartados, "usa_sasrec": bool(tengo)}

    def _motivos(self, f, usa_sasrec, acordes, notas, ocasiones, n_cand):
        m = []
        if usa_sasrec:
            m.append(f"SASRec lo pone en el puesto {f['puesto_modelo']} de sus {n_cand} candidatos para lo que tienes "
                     f"(probabilidad {f['prob_modelo']:.1%})")
        else:
            m.append(f"Sin historial: candidato por popularidad (puesto {f['puesto_modelo']})")
        c = f["coincide"]
        if acordes:
            m.append(f"Acordes que pediste: {', '.join(c['acordes'])}" if c["acordes"]
                     else "No tiene los acordes que pediste" if f["tiene_ficha"] else "Sin ficha olfativa")
        if notas:
            m.append(f"Notas que pediste: {', '.join(c['notas'])}" if c["notas"] else "No tiene las notas que pediste")
        if ocasiones:
            m.append("Su ocasión estimada (por IA) calza con la que buscas" if c["ocasion"] else "Su ocasión estimada es otra")
        if f["parcial"]:
            m.append("Coincidencia parcial: se agregó porque pocos candidatos cumplían todo")
        return m

    def ocasiones(self):
        return self.fichas["ocasion"].dropna().value_counts().index.tolist() if len(self.fichas) else []

    def todos_los_acordes(self):
        c = Counter(a for t in self.fichas.get("acordes", pd.Series(dtype=str)) for a in lista_acordes(t))
        return [a for a, _ in c.most_common()]

    # ---------- segmentos y contexto ----------
    def segmento(self, historial, objetivo=None):
        s = self.segmentos.set_index("segmento")["SASRec"]
        largo = [k for k in s.index if ("corto" in k) == (len(historial) <= self.corte_largo) and "Historial" in k][0]
        out = {"segmento_historial": largo, "NDCG@10_SASRec_en_ese_segmento": round(float(s[largo]), 4)}
        if objetivo is not None:
            pop = "Perfume oculto popular (top 20 %)" if objetivo in self.populares else "Perfume oculto de cola larga"
            out["segmento_perfume"] = pop
            out["NDCG@10_SASRec_en_segmento_perfume"] = round(float(s[pop]), 4)
        return out

    def contexto(self, historial, oculto=None, k=10):
        recs = self.recomendar(historial, k)
        aten = dict(self.atencion(historial))
        lb = self.lineas_base(historial, k)
        ids_recs = [r["idx"] for r in recs]
        ctx = {
            "historial": [dict(self.ficha(i), orden=n + 1, atencion=round(aten.get(i, 0.0), 3))
                          for n, i in enumerate(historial)],
            "nota_atencion": f"El modelo solo mira los últimos {self.modelo.largo} perfumes; los anteriores tienen atención 0.",
            "recomendaciones": [dict(r, **self.ficha(r["idx"], notas=False)) for r in recs],
            "perfil_olfativo": {"historial": self.perfil_olfativo(historial),
                                "recomendaciones": self.perfil_olfativo(ids_recs)},
            "lineas_base": {n: [self.nombre(i) for i in l] for n, l in lb.items() if n != "Reglas (lift)"},
            "coincidencias_con_lineas_base": {n: len(set(l) & set(ids_recs)) for n, l in lb.items()},
            "metricas_globales": {m: {c: round(float(v), 4) for c, v in self.metricas.loc[m, ["HR@10", "NDCG@10", "MRR@10", "Cobertura@10"]].items()}
                                  for m in self.metricas.index},
            "metricas_segmento": self.segmento(historial, oculto),
            "modelo": {"tipo": "SASRec", **self.config, "parametros": int(sum(p.numel() for p in self.modelo.parameters()))},
        }
        if oculto is not None:
            pos = ids_recs.index(oculto) + 1 if oculto in ids_recs else None
            ctx["perfume_oculto"] = dict(self.ficha(oculto, notas=False),
                                         acierto_top10=pos is not None, posicion_en_top10=pos)
        return ctx
