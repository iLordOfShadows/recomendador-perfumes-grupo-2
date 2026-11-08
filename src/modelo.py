"""SASRec (misma arquitectura del notebook de la Entrega 1) y funciones para recomendar en CPU."""
import math

import numpy as np
import torch
import torch.nn as nn


class BloqueSASRec(nn.Module):
    def __init__(self, d, cabezas, dropout):
        super().__init__()
        self.atencion = nn.MultiheadAttention(d, cabezas, dropout=dropout, batch_first=True)
        self.norma1 = nn.LayerNorm(d)
        self.ffn = nn.Sequential(nn.Linear(d, d), nn.ReLU(), nn.Dropout(dropout), nn.Linear(d, d))
        self.norma2 = nn.LayerNorm(d)
        self.drop = nn.Dropout(dropout)
        self.pesos = None

    def forward(self, x, mascara, guardar_pesos=False):
        a, w = self.atencion(x, x, x, attn_mask=mascara, need_weights=guardar_pesos, average_attn_weights=True)
        if guardar_pesos:
            self.pesos = w.detach()
        x = self.norma1(x + self.drop(a))
        x = self.norma2(x + self.drop(self.ffn(x)))
        return x


class SASRec(nn.Module):
    def __init__(self, n_items, d=64, bloques=2, cabezas=2, dropout=0.2, largo=14):
        super().__init__()
        self.largo = largo
        self.emb_item = nn.Embedding(n_items + 1, d, padding_idx=0)
        self.emb_pos = nn.Embedding(largo, d)
        self.drop = nn.Dropout(dropout)
        self.cabezas = cabezas
        self.bloques = nn.ModuleList([BloqueSASRec(d, cabezas, dropout) for _ in range(bloques)])
        self.norma = nn.LayerNorm(d)
        self.register_buffer("causal", torch.triu(torch.ones(largo, largo, dtype=torch.bool), diagonal=1))

    def representar(self, seq, guardar_pesos=False):
        n = seq.size(1)
        pos = torch.arange(n, device=seq.device).unsqueeze(0)
        x = self.drop(self.emb_item(seq) + self.emb_pos(pos))
        relleno = seq == 0
        mascara = self.causal[:n, :n].unsqueeze(0) | relleno.unsqueeze(1)
        mascara = mascara & ~torch.eye(n, dtype=torch.bool, device=seq.device)
        mascara = mascara.repeat_interleave(self.cabezas, dim=0)
        for b in self.bloques:
            x = b(x, mascara, guardar_pesos)
            x = x * (~relleno).unsqueeze(-1)
        return self.norma(x)


def rellenar(seq, n):
    seq = list(seq)[-n:]
    return [0] * (n - len(seq)) + seq


def cargar_modelo(ruta="modelos/sasrec.pt"):
    ck = torch.load(ruta, map_location="cpu")
    modelo = SASRec(ck["n_items"], largo=ck["largo_max"], **ck["config"])
    modelo.load_state_dict(ck["estado"])
    modelo.eval()
    return modelo, ck


@torch.no_grad()
def puntajes(modelo, historiales):
    """Puntaje de todo el catálogo (columna 0 = relleno) para lo que viene después de cada historial."""
    x = torch.tensor([rellenar(h, modelo.largo) for h in historiales])
    h = modelo.representar(x)[:, -1, :]
    return h @ modelo.emb_item.weight.T


@torch.no_grad()
def recomendar(modelo, historial, k=10, excluir=()):
    """Top-k de SASRec: lista de (idx, puntaje, probabilidad softmax). Excluye lo ya visto y el relleno."""
    p = puntajes(modelo, [historial])[0]
    p[0] = -float("inf")
    vistos = list(set(historial) | set(excluir))
    if vistos:
        p[vistos] = -float("inf")
    prob = torch.softmax(p, dim=0)
    top = torch.topk(p, k)
    return [(int(i), float(s), float(prob[i])) for s, i in zip(top.values, top.indices)]


@torch.no_grad()
def atencion(modelo, historial):
    """Peso de atención (último bloque, última posición) sobre cada perfume del historial (los últimos `largo`)."""
    x = torch.tensor([rellenar(historial, modelo.largo)])
    modelo.representar(x, guardar_pesos=True)
    w = modelo.bloques[-1].pesos[0, -1].numpy()
    n = min(len(historial), modelo.largo)
    return list(historial)[-n:], w[-n:]


def embeddings(modelo):
    return modelo.emb_item.weight.detach().numpy()[1:]
