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
| Reglas de asociación (lift) | 0,094 | 0,046 | 0,032 | 37,9 % |
| Ítem–ítem coseno | 0,114 | 0,063 | 0,047 | 99,3 % |
| **SASRec** | **0,174** | **0,098** | **0,076** | 40,8 % |

SASRec mejora en **57 %** el NDCG@10 de la mejor línea base. En los perfumes de cola larga, en cambio, rinde peor que
ítem–ítem. El detalle está en el notebook y en el informe.

## Base

*Amazon Reviews 2023* (McAuley Lab, UCSD), categorías *Beauty and Personal Care* y *All Beauty*, solo perfumes. Cada
interacción es una reseña (usuario, perfume, marca de tiempo).

| | |
|---|---|
| Después del 5-core | 39.032 interacciones · 5.398 usuarios · 2.125 perfumes |
| Mínimo de interacciones | El profesor autorizó la excepción al mínimo de 50.000 interacciones, para conservar una base de solo perfumes |
| Cita | Hou, Y., Li, J., He, Z., Yan, A., Chen, X. y McAuley, J. (2024). *Bridging Language and Items for Retrieval and Recommendation*. arXiv:2403.03952 |
| Fichas olfativas | Base de fichas de Parfumo del grupo (notas, acordes, ocasión), cruzada con los perfumes de Amazon por marca y nombre: el 45 % de los perfumes tiene ficha |

## Estructura

```
├── app.py                         Dashboard (Streamlit), carga modelos/sasrec.pt en CPU
├── notebooks/Entrega1_Grupo_2.ipynb   Notebook ejecutado (semilla 42): datos, protocolo, líneas base, SASRec, comparación
├── informe/Informe_Entrega1_Grupo_2.pdf
├── data/
│   ├── secuencias.parquet         Secuencias por usuario (índice 0 = relleno), con fechas
│   ├── mapa_items.csv             idx → perfume (título, marca, género, precio, valoración)
│   ├── metricas.csv               Métricas de prueba, cobertura y costo de los 4 modelos
│   ├── segmentos.csv              NDCG@10 por segmento
│   ├── reglas.csv                 Reglas 1 ⇒ 1 (línea base de reglas de asociación)
│   └── fichas_olfativas.csv       Acordes y notas (cruce con Parfumo)
├── modelos/sasrec.pt              Pesos + configuración de SASRec (0,76 MB)
├── src/
│   ├── modelo.py                  Arquitectura SASRec, carga y recomendación
│   ├── lineas_base.py             Popularidad, reglas por lift, ítem–ítem
│   ├── sistema.py                 Une modelo + datos; contexto estructurado del analista; perfil olfativo
│   ├── analista.py                Analista IA: llamadas a la API, herramientas, tokens, costo y latencia
│   ├── analista_prompt.md         Prompt de sistema VERSIONADO del analista
│   ├── preparar_datos.py          Genera reglas.csv y segmentos.csv (y verifica que se reproducen las métricas)
│   └── fichas.py                  Cruce con las fichas de Parfumo
└── pruebas/
    ├── pruebas_honestidad.py      5 pruebas de honestidad + 1 de consulta al modelo
    └── resultados_honestidad.md   Resultados (respuestas completas, tokens, costo, latencia)
```

## Asesor guiado: "Encuentra tu perfume" (innovación)

La primera pestaña del dashboard le pregunta a la persona **qué perfumes tiene**, en el orden en que los compró, y
**qué busca**: para quién, presupuesto, ocasión, acordes y si quiere probar marcas nuevas. Con eso recomienda un
perfume principal y 4 alternativas, cada una con sus motivos.

- **Puntaje** = (1 − w) · cercanía SASRec + w · afinidad, con w = 0,5 por defecto (ajustable).
  - *Cercanía SASRec* = 1 − log(puesto)/log(N), donde *puesto* es la posición del perfume en el ranking completo del
    modelo, dado lo que la persona tiene.
  - *Afinidad* combina los acordes pedidos presentes en la ficha y si coincide la ocasión.
- **Filtros duros:** género, presupuesto y marcas nuevas.
- **Sin perfumes declarados** (arranque en frío) se usa la popularidad en lugar de SASRec.
- **El analista IA puede explicar la lista**, pero no puede cambiarla. La pestaña *Recomendación* sigue mostrando
  SASRec puro, para evaluar el modelo.

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
  cada llamada.
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
- **Regenerar reglas y segmentos:** `python -m src.preparar_datos`
- **Regenerar las fichas:** `python -m src.fichas ruta/al/Excel.xlsx`

**Publicar en Streamlit Cloud:** *New app* → este repositorio → `app.py`. Luego, en *Settings → Secrets*, pegar
`GEMINI_API_KEY = "..."`. El modelo corre en CPU, porque `requirements.txt` instala la versión CPU de PyTorch.
