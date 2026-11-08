# Un recomendador que entiende el orden: perfumes

**Del Transformer al dashboard, con una IA que lo analiza.**
Grupo 2 · Lucas Torres Baeza · María Jesús Salinas · Aprendizaje no supervisado (UDD) · Docente: Danilo Gómez Correa

Este proyecto recomienda **el próximo perfume** que una persona va a buscar, según los que ya reseñó y el orden en que
lo hizo. Para eso usa **SASRec**, un Transformer secuencial entrenado en PyTorch. Un dashboard en Streamlit muestra las
recomendaciones y un **analista IA** (Gemini, plan gratuito) las explica sin modificarlas.

🔗 **Dashboard:** _(pegar aquí el enlace de Streamlit Cloud)_

## Resultados (prueba, leave-last-out, ranking sobre los 2.125 perfumes)

| Modelo | HR@10 | NDCG@10 | MRR@10 | Cobertura@10 |
|---|---|---|---|---|
| Popularidad | 0,094 | 0,051 | 0,038 | 0,8 % |
| Reglas de asociación (lift, umbrales elegidos en validación) | 0,133 | 0,075 | 0,058 | 21,6 % |
| Ítem–ítem coseno | 0,114 | 0,063 | 0,047 | 99,3 % |
| **SASRec** | **0,174** | **0,098** | **0,076** | 40,8 % |

SASRec mejora en **31 %** el NDCG@10 de la mejor línea base. En los perfumes de cola larga, en cambio, rinde peor que
ítem–ítem. **El notebook, el informe, `data/` y el modelo salen de una única corrida** (semilla 42), registrada en
`data/resumen_corrida.json`.

**Analista IA, probado con Gemini real:** pasa 6 de 6 pruebas de honestidad tras revisión manual. El costo real es
US$ 0 con la llave gratuita y el costo equivalente pagado es US$ 0,007 por sesión. La latencia mediana es de 2,1 s para el
análisis y de 3,2 s para el chat con re-consulta al modelo. El detalle está en `pruebas/` y en la pestaña *Evaluación del
analista*.

## Base

*Amazon Reviews 2023* (McAuley Lab, UCSD), categorías *Beauty and Personal Care* y *All Beauty*, solo perfumes. Cada
interacción es una reseña (usuario, perfume, marca de tiempo).

| | |
|---|---|
| Después del 5-core | 39.032 interacciones · 5.398 usuarios · 2.125 perfumes |
| Mínimo de interacciones | El profesor autorizó la excepción al mínimo de 50.000 interacciones, para conservar una base de solo perfumes |
| Cita | Hou, Y., Li, J., He, Z., Yan, A., Chen, X. y McAuley, J. (2024). *Bridging Language and Items for Retrieval and Recommendation*. arXiv:2403.03952 |
| Fichas olfativas | Dataset público de Parfumo redistribuido por TidyTuesday (rfordatascience, 2024-12-10; origen: Kaggle, Olga G. Miufana). **No hicimos scraping de Parfumo.** Usamos solo esas filas (se excluyen 174 perfumes 2025–2026 agregados a mano desde la web), cruzadas con Amazon por marca y nombre: el 45 % de los perfumes tiene ficha. La columna "ocasión" no viene de Parfumo: la estimó una IA (Claude Code) a partir de las notas de cada perfume, por lo que es aproximada. Uso académico, no comercial |

## Estructura

```
├── app.py                         Dashboard (Streamlit), carga modelos/sasrec.pt en CPU
├── notebooks/Entrega1_Grupo_2.ipynb   Notebook ejecutado de punta a punta (semilla 42)
├── informe/Informe_Entrega1_Grupo_2.pdf
├── data/                          Todo exportado por el notebook en la MISMA corrida, salvo fichas_olfativas.csv
│   ├── secuencias.parquet         Secuencias por usuario (índice 0 = relleno), con fechas; usuarios anonimizados
│   ├── mapa_items.csv             idx → perfume (título, marca, género, precio, valoración)
│   ├── metricas.csv               Métricas de prueba, cobertura y costo de los 4 modelos
│   ├── segmentos.csv              NDCG@10 por segmento
│   ├── reglas.csv                 Reglas 1 ⇒ 1 (umbrales elegidos en validación)
│   ├── resumen_corrida.json       Todas las cifras de la corrida que cita el informe
│   └── fichas_olfativas.csv       Acordes y notas (cruce con el dataset público de Parfumo, src/fichas.py)
├── modelos/sasrec.pt              Pesos + configuración de SASRec (0,76 MB)
├── src/
│   ├── modelo.py                  Arquitectura SASRec (idéntica al notebook), carga y recomendación en CPU
│   ├── lineas_base.py             Popularidad, reglas por lift, ítem–ítem (para comparar en el dashboard)
│   ├── sistema.py                 Une modelo + datos; contexto estructurado del analista; asesor; perfil olfativo
│   ├── analista.py                Analista IA: llamadas a la API, herramientas, tokens, costo y latencia
│   ├── analista_prompt.md         Prompt de sistema VERSIONADO (v1.0 → v1.4, con historial de cambios)
│   └── fichas.py                  Cruce con las fichas olfativas
└── pruebas/
    ├── pruebas_honestidad.py      5 pruebas de honestidad + 1 de re-consulta al modelo
    ├── resultados_honestidad.md   Respuestas completas de Gemini + revisión manual
    ├── medir_costo.py             Costo y latencia con 10 usuarios reales
    ├── costo_latencia.md          Resumen (medianas, p90, costo por sesión)
    └── costo_latencia.csv         Una fila por llamada
```

## Asesor guiado: "Encuentra tu perfume" (innovación)

La primera pestaña del dashboard le pregunta a la persona **qué perfumes tiene**, en el orden en que los compró, y
**qué busca**: para quién, presupuesto, ocasión, acordes, notas y si quiere probar marcas nuevas. Con eso recomienda un
perfume principal y 4 alternativas, cada una con sus motivos.

1. **SASRec propone** sus 200 mejores candidatos para lo que la persona tiene. Sin perfumes declarados (arranque en
   frío), los candidatos son los más populares.
2. **El código filtra** esos candidatos por género (acepta unisex), presupuesto, marcas nuevas y los acordes, notas y
   ocasión pedidos. El LLM no participa en esta lista.
3. **Se conserva el orden de SASRec** entre los que pasan; no hay puntaje mixto. Si pasan menos de 5, se completa con
   coincidencias parciales, marcadas como tales.

El analista IA puede explicar la lista, pero no puede cambiarla. La pestaña *Recomendación* muestra SASRec puro, que es
lo que se evalúa.

## Analista IA

- **No toca la lista.** Las recomendaciones del panel vienen solo de SASRec. El analista escribe texto y no puede
  agregar, quitar ni reordenar perfumes (regla 1 del prompt, verificada en las pruebas).
- **Contexto estructurado.** Recibe un JSON con el historial (con atención y ficha olfativa), el top 10 con puntajes, el
  perfil olfativo, las líneas base, las métricas globales y las del segmento. Si se trata de un usuario de la base,
  también recibe el perfume oculto.
- **Análisis automático** al cargar cada historial, y **chat de seguimiento**. El chat puede volver a consultar al modelo
  con la herramienta `recomendar_con_historial` ("¿y si además compra X?") y a los datos con `buscar_perfume`,
  `ficha_perfume` y `comparar_lineas_base`.
- **Prompt versionado** en `src/analista_prompt.md`. La versión en uso se muestra en la app y queda en el registro de
  cada llamada. Los cambios v1.2 a v1.4 responden al feedback de la Entrega 1 y a las pruebas reales con Gemini.
- **Modelo de lenguaje.** Por defecto, `gemini-3.1-flash-lite` con la llave gratuita de Google AI Studio. Como
  alternativa pagada se puede elegir Claude (`claude-haiku-5-5`). El proveedor se cambia desde la barra lateral y la
  lógica del analista es la misma para ambos.
- **Costo y latencia.** Cada llamada registra tokens de entrada y salida, latencia, costo real y **costo equivalente**
  según el precio del plan pagado (US$ 0,25 y US$ 1,50 por millón de tokens de entrada y salida para Gemini 3.1
  Flash-Lite). Con la llave gratuita el costo real es 0.
- **Llave.** Va en `st.secrets` (`GEMINI_API_KEY`) y nunca se sube a GitHub (`.streamlit/secrets.toml` está en
  `.gitignore`). En el plan gratuito, Google puede usar las consultas para mejorar sus modelos. Aquí solo se envían
  datos públicos de Amazon y fichas de perfumes, sin datos personales.

## Cómo correrlo

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # y pegar la llave gratuita de Gemini
streamlit run app.py
```

- **Pruebas de honestidad:** `GEMINI_API_KEY=... python -m pruebas.pruebas_honestidad`
- **Costo y latencia:** `GEMINI_API_KEY=... python -m pruebas.medir_costo 10`
- **Reglas, segmentos y métricas:** se regeneran solo corriendo el notebook de punta a punta.
- **Regenerar las fichas:** `python -m src.fichas ruta/al/Excel.xlsx`

**Publicar en Streamlit Cloud:** *New app* → este repositorio → `app.py`. Luego, en *Settings → Secrets*, pegar
`GEMINI_API_KEY = "..."`. El modelo corre en CPU, porque `requirements.txt` instala la versión CPU de PyTorch.
