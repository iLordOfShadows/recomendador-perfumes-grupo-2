"""Líneas base de la Entrega 1 (popularidad, reglas por lift, ítem–ítem coseno), para usarlas en el dashboard."""
import numpy as np
import pandas as pd


class LineasBase:
    def __init__(self, secuencias_entren, n_items, reglas=None, ultimos=10, decaimiento=0.8):
        self.n_items = n_items
        todos = [i for s in secuencias_entren for i in s]
        self.popularidad = pd.Series(todos).value_counts()
        # Ítem–ítem: coseno entre columnas de la matriz usuarios × perfumes
        M = np.zeros((len(secuencias_entren), n_items), dtype=np.float32)
        for f, s in enumerate(secuencias_entren):
            if len(s):
                M[f, np.array(s) - 1] = 1
        normas = np.linalg.norm(M, axis=0) + 1e-9
        self.sim = (M.T @ M) / np.outer(normas, normas)
        np.fill_diagonal(self.sim, 0)
        self.ultimos, self.decaimiento = ultimos, decaimiento
        # Reglas 1 ⇒ 1: {antecedente: {consecuente: lift}}
        self.reglas = {}
        if reglas is not None:
            for a, c, l in zip(reglas["antecedente"], reglas["consecuente"], reglas["lift"]):
                self.reglas.setdefault(int(a), {})[int(c)] = max(l, self.reglas.get(int(a), {}).get(int(c), 0))

    def _rellenar_populares(self, lista, vistos, k):
        for i in self.popularidad.index:
            if len(lista) >= k:
                break
            if i not in vistos and i not in lista:
                lista.append(int(i))
        return lista

    def popular(self, historial, k=10):
        return self._rellenar_populares([], set(historial), k)

    def item_item(self, historial, k=10):
        recientes = list(historial)[-self.ultimos:][::-1]
        p = np.zeros(self.n_items, dtype=np.float32)
        for j, i in enumerate(recientes):
            p += (self.decaimiento ** j) * self.sim[i - 1]
        if len(historial):
            p[np.array(list(historial)) - 1] = -np.inf
        top = np.argpartition(-p, k)[:k]
        return [int(t) + 1 for t in top[np.argsort(-p[top])]]

    def reglas_lift(self, historial, k=10):
        vistos = set(historial)
        puntaje = {}
        for a in vistos:
            for c, l in self.reglas.get(a, {}).items():
                if c not in vistos:
                    puntaje[c] = max(l, puntaje.get(c, 0))
        lista = [c for c, _ in sorted(puntaje.items(), key=lambda x: -x[1])][:k]
        return self._rellenar_populares(lista, vistos, k)
