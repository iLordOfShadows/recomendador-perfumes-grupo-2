"""Analista IA: explica las recomendaciones de SASRec con un LLM.

- Contexto estructurado (JSON) construido por Sistema.contexto().
- No toca la lista: las recomendaciones que muestra el panel vienen del modelo; el analista solo escribe texto.
- Herramientas que vuelven a consultar al modelo (escenarios "¿y si…?") y a los datos.
- Registra tokens, costo y latencia de cada llamada.
- Dos proveedores intercambiables: Google Gemini (plan gratuito, por defecto) y Anthropic Claude (pagado).
"""
import json
import os
import re
import time

PROMPT_RUTA = os.path.join(os.path.dirname(__file__), "analista_prompt.md")

# Modelos disponibles y precio de referencia en US$ por millón de tokens (plan pagado).
# Con la llave gratuita de Google AI Studio el costo real es 0; se muestra igual el "costo equivalente" pagado.
MODELOS = {
    "gemini-3.1-flash-lite": {"proveedor": "gemini", "entrada": 0.25, "salida": 1.50, "gratis": True},
    "claude-haiku-5-5": {"proveedor": "anthropic", "entrada": 0.10, "salida": 0.50, "gratis": False},
    "claude-sonnet-5-5": {"proveedor": "anthropic", "entrada": 2.00, "salida": 10.00, "gratis": False},
}
MODELO_DEFECTO = os.environ.get("MODELO_GEMINI", "gemini-3.1-flash-lite")
if MODELO_DEFECTO not in MODELOS:          # otro modelo Gemini disponible en la cuenta (mismo precio de referencia)
    MODELOS[MODELO_DEFECTO] = dict(MODELOS["gemini-3.1-flash-lite"])

# Si Gemini responde "alta demanda" (503) o "límite" (429), se reintenta con espera creciente y luego se prueba con
# modelos de respaldo. El modelo que respondió queda en el registro de cada llamada.
REINTENTOS = (2, 5, 10)                    # segundos de espera entre intentos
RESPALDO_GEMINI = [m.strip() for m in os.environ.get("MODELOS_RESPALDO", "gemini-2.5-flash-lite,gemini-2.5-flash").split(",")
                   if m.strip()]


def es_transitorio(e):
    t = str(e)
    return any(c in t for c in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "overloaded"))


HERRAMIENTAS = [
    {
        "name": "recomendar_con_historial",
        "description": "Vuelve a consultar a SASRec con el historial actual modificado (agregando perfumes al final y/o "
                       "quitando perfumes). Devuelve el nuevo top-k. Es un escenario hipotético: no cambia la "
                       "recomendación principal del panel.",
        "schema": {
            "type": "object",
            "properties": {
                "agregar": {"type": "array", "items": {"type": "integer"},
                            "description": "idx de perfumes que se agregan al final del historial (compras más recientes)"},
                "quitar": {"type": "array", "items": {"type": "integer"}, "description": "idx de perfumes que se quitan"},
                "k": {"type": "integer", "description": "largo de la lista (1 a 20); por defecto 10"},
            },
        },
    },
    {
        "name": "buscar_perfume",
        "description": "Busca perfumes del catálogo por texto (nombre o marca). Devuelve idx, marca y título.",
        "schema": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]},
    },
    {
        "name": "ficha_perfume",
        "description": "Atributos de un perfume del catálogo: marca, género, precio, valoración, popularidad y ficha "
                       "olfativa (acordes y notas) si existe.",
        "schema": {"type": "object", "properties": {"idx": {"type": "integer"}}, "required": ["idx"]},
    },
    {
        "name": "comparar_lineas_base",
        "description": "Recomendaciones de popularidad, reglas de asociación e ítem–ítem para el historial actual.",
        "schema": {"type": "object", "properties": {}},
    },
]


def leer_prompt():
    texto = open(PROMPT_RUTA, encoding="utf-8").read()
    version = re.search(r"versión\s+([\d.]+)", texto)
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S).strip()
    return texto, version.group(1) if version else "?"


def costo(modelo, tin, tout):
    p = MODELOS.get(modelo, MODELOS[MODELO_DEFECTO])
    return (tin * p["entrada"] + tout * p["salida"]) / 1e6


def crear_cliente(modelo, llave):
    """Cliente del proveedor que corresponde al modelo."""
    if MODELOS[modelo]["proveedor"] == "gemini":
        from google import genai
        return genai.Client(api_key=llave)
    import anthropic
    return anthropic.Anthropic(api_key=llave)


# ---------------------------------------------------------------------------- proveedores
# Cada uno guarda la conversación en su propio formato y devuelve una respuesta normalizada:
# {"texto", "llamadas": [{"id", "nombre", "entrada"}], "tokens_entrada", "tokens_salida"}

class _Gemini:
    def __init__(self, cliente, modelo, sistema, max_tokens):
        from google.genai import types
        self.t, self.cliente, self.modelo = types, cliente, modelo
        self.config = types.GenerateContentConfig(
            system_instruction=sistema, max_output_tokens=max_tokens, temperature=0.3,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=h["name"], description=h["description"], parameters_json_schema=h["schema"])
                for h in HERRAMIENTAS])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        self.contenido = []

    def agregar_usuario(self, texto):
        self.contenido.append(self.t.Content(role="user", parts=[self.t.Part.from_text(text=texto)]))

    def agregar_asistente(self, texto):
        self.contenido.append(self.t.Content(role="model", parts=[self.t.Part.from_text(text=texto)]))

    def agregar_resultados(self, resultados):
        partes = [self.t.Part(function_response=self.t.FunctionResponse(id=ll["id"], name=ll["nombre"],
                                                                        response={"resultado": salida}))
                  for ll, salida in resultados]
        self.contenido.append(self.t.Content(role="user", parts=partes))

    def _generar(self):
        modelos = [self.modelo] + [m for m in RESPALDO_GEMINI if m != self.modelo]
        ultimo = None
        for n, modelo in enumerate(modelos):
            esperas = REINTENTOS if n == 0 else (3,)
            for espera in (0,) + esperas:
                time.sleep(espera)
                try:
                    r = self.cliente.models.generate_content(model=modelo, contents=self.contenido, config=self.config)
                    self.modelo_usado = modelo
                    return r
                except Exception as e:          # noqa: BLE001 — se reintenta solo si el error es temporal
                    if n == 0 or ultimo is None:
                        ultimo = e              # se informa el error del modelo principal, no el de un respaldo
                    if not es_transitorio(e):
                        break
        raise ultimo

    def llamar(self):
        r = self._generar()
        cand = r.candidates[0].content if r.candidates and r.candidates[0].content else None
        if cand is not None:
            self.contenido.append(cand)          # conserva las firmas de razonamiento que exige Gemini 3
        partes = cand.parts if cand is not None and cand.parts else []
        texto = "".join(p.text for p in partes if getattr(p, "text", None) and not getattr(p, "thought", False))
        llamadas = [{"id": p.function_call.id, "nombre": p.function_call.name, "entrada": dict(p.function_call.args or {})}
                    for p in partes if getattr(p, "function_call", None)]
        u = r.usage_metadata
        salida = (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        return {"texto": texto.strip(), "llamadas": llamadas, "tokens_entrada": u.prompt_token_count or 0,
                "tokens_salida": salida}


class _Anthropic:
    def __init__(self, cliente, modelo, sistema, max_tokens):
        self.cliente, self.modelo, self.sistema, self.max_tokens = cliente, modelo, sistema, max_tokens
        self.herramientas = [{"name": h["name"], "description": h["description"], "input_schema": h["schema"]}
                             for h in HERRAMIENTAS]
        self.mensajes = []

    def agregar_usuario(self, texto):
        self.mensajes.append({"role": "user", "content": texto})

    def agregar_asistente(self, texto):
        self.mensajes.append({"role": "assistant", "content": texto})

    def agregar_resultados(self, resultados):
        self.mensajes.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": ll["id"], "content": json.dumps(salida, ensure_ascii=False, default=str)}
            for ll, salida in resultados]})

    def llamar(self):
        r = self.cliente.messages.create(model=self.modelo, max_tokens=self.max_tokens, system=self.sistema,
                                         messages=self.mensajes, tools=self.herramientas)
        contenido = []
        for b in r.content:                  # se guardan solo los campos que la API espera de vuelta
            b = b.model_dump() if hasattr(b, "model_dump") else b
            if b["type"] == "text":
                contenido.append({"type": "text", "text": b["text"]})
            elif b["type"] == "tool_use":
                contenido.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["input"]})
        self.mensajes.append({"role": "assistant", "content": contenido})
        return {"texto": "".join(b.get("text", "") for b in contenido if b["type"] == "text").strip(),
                "llamadas": [{"id": b["id"], "nombre": b["name"], "entrada": b["input"]}
                             for b in contenido if b["type"] == "tool_use"],
                "tokens_entrada": r.usage.input_tokens, "tokens_salida": r.usage.output_tokens}


# ---------------------------------------------------------------------------- analista
class Analista:
    def __init__(self, sistema, cliente, modelo=MODELO_DEFECTO, max_tokens=1200):
        self.s = sistema
        self.cliente = cliente
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.sistema_prompt, self.version = leer_prompt()
        self.registro = []                   # una fila por llamada a la API
        self.historial = []
        self.oculto = None

    def nueva_sesion(self, historial, oculto=None, extra=None):
        self.historial, self.oculto = list(historial), oculto
        self.contexto = self.s.contexto(self.historial, oculto) if self.historial else {}
        if extra:
            self.contexto.update(extra)
        clase = _Gemini if MODELOS[self.modelo]["proveedor"] == "gemini" else _Anthropic
        self.conv = clase(self.cliente, self.modelo, self.sistema_prompt, self.max_tokens)
        self.conv.agregar_usuario("CONTEXTO\n```json\n" + json.dumps(self.contexto, ensure_ascii=False, default=str) + "\n```")
        self.conv.agregar_asistente("Recibí el contexto. ¿Qué necesitas?")

    def analisis_automatico(self):
        return self.preguntar("ANALISIS_AUTOMATICO")

    def explicar_asesor(self):
        return self.preguntar("EXPLICAR_ASESOR")

    # ---------- herramientas ----------
    def _ejecutar(self, nombre, entrada):
        try:
            if nombre == "recomendar_con_historial":
                quitar = {int(i) for i in (entrada.get("quitar") or [])}
                agregar = [int(i) for i in (entrada.get("agregar") or []) if 1 <= int(i) <= self.s.n_items]
                ya_estaban = [i for i in agregar if i in self.historial]
                # Un perfume que ya estaba se mueve al final (pasa a ser el más reciente), no se duplica
                nuevo = [i for i in self.historial if i not in quitar and i not in agregar] + agregar
                k = max(1, min(20, int(entrada.get("k") or 10)))
                if not nuevo:
                    return {"error": "El historial quedó vacío; SASRec necesita al menos un perfume."}
                recs = self.s.recomendar(nuevo, k)
                salida = {"escenario": "hipotético", "historial_usado": [self.s.nombre(i) for i in nuevo],
                          "recomendaciones": [dict(r, nombre=self.s.nombre(r["idx"])) for r in recs]}
                if ya_estaban:
                    salida["aviso"] = ("Estos perfumes YA estaban en el historial; no se agregaron de nuevo, solo se movieron "
                                       "al final como compra más reciente: " + ", ".join(self.s.nombre(i) for i in ya_estaban))
                return salida
            if nombre == "buscar_perfume":
                return {"resultados": self.s.buscar(str(entrada.get("texto", "")))}
            if nombre == "ficha_perfume":
                i = int(entrada["idx"])
                return self.s.ficha(i) if i in self.s.items.index else {"error": f"No existe el idx {i} en el catálogo."}
            if nombre == "comparar_lineas_base":
                return {n: [self.s.nombre(i) for i in l] for n, l in self.s.lineas_base(self.historial).items()}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"Entrada inválida para {nombre}: {e}"}
        return {"error": f"Herramienta desconocida: {nombre}"}

    # ---------- llamada con bucle de herramientas ----------
    def preguntar(self, texto, max_vueltas=4):
        lista = self.conv.contenido if hasattr(self.conv, "contenido") else self.conv.mensajes
        n_antes = len(lista)
        try:
            return self._preguntar(texto, max_vueltas)
        except Exception:
            del lista[n_antes:]                # si la API falla, la conversación queda como estaba
            raise

    def _preguntar(self, texto, max_vueltas):
        self.conv.agregar_usuario(texto)
        usadas = []
        inicio = time.perf_counter()
        tin = tout = 0
        for _ in range(max_vueltas):
            t0 = time.perf_counter()
            r = self.conv.llamar()
            lat = time.perf_counter() - t0
            tin += r["tokens_entrada"]
            tout += r["tokens_salida"]
            self.registro.append({"tipo": "análisis" if texto == "ANALISIS_AUTOMATICO" else "chat",
                                  "modelo": getattr(self.conv, "modelo_usado", self.modelo),
                                  "tokens_entrada": r["tokens_entrada"], "tokens_salida": r["tokens_salida"],
                                  "costo_usd": 0.0 if MODELOS[self.modelo]["gratis"] else costo(self.modelo, r["tokens_entrada"], r["tokens_salida"]),
                                  "costo_equivalente_pagado_usd": costo(self.modelo, r["tokens_entrada"], r["tokens_salida"]),
                                  "latencia_s": round(lat, 2), "prompt": self.version})
            if not r["llamadas"]:
                return self._resumen(r["texto"], usadas, tin, tout, inicio)
            resultados = []
            for ll in r["llamadas"]:
                salida = self._ejecutar(ll["nombre"], ll["entrada"] or {})
                usadas.append({"herramienta": ll["nombre"], "entrada": ll["entrada"], "salida": salida})
                resultados.append((ll, salida))
            self.conv.agregar_resultados(resultados)
        return self._resumen("(Se alcanzó el máximo de consultas a herramientas en esta pregunta.)", usadas, tin, tout, inicio)

    def _resumen(self, texto, usadas, tin, tout, inicio):
        eq = costo(self.modelo, tin, tout)
        return {"texto": texto or "(El modelo no devolvió texto.)", "herramientas": usadas, "tokens_entrada": tin,
                "tokens_salida": tout, "costo_usd": 0.0 if MODELOS[self.modelo]["gratis"] else eq,
                "costo_equivalente_usd": eq, "latencia_s": round(time.perf_counter() - inicio, 2),
                "modelo_respondio": getattr(self.conv, "modelo_usado", self.modelo)}
