# Un recomendador que entiende el orden: perfumes

Grupo 2 · Lucas Torres Baeza · María Jesús Salinas · Aprendizaje no supervisado (UDD) · Docente: Danilo Gómez Correa

Este proyecto recomienda **el próximo perfume** que una persona va a buscar, según los que ya reseñó y el orden en que
lo hizo. Para eso usa **SASRec**, un Transformer secuencial entrenado en PyTorch, y lo compara con tres líneas base.

> **Estado:** Entrega 1, versión corregida tras el feedback. El dashboard y el analista IA (Entrega 2) se suben a este
> repositorio cuando estén listos; este README solo describe lo que ya está aquí.

## Resultados (prueba, leave-last-out, ranking sobre los 2.125 perfumes)

| Modelo | HR@10 | NDCG@10 | MRR@10 | Cobertura@10 |
|---|---|---|---|---|
| Popularidad | 0,094 | 0,051 | 0,038 | 0,8 % |
| Reglas de asociación (lift, umbrales elegidos en validación) | 0,133 | 0,075 | 0,058 | 21,6 % |
| Ítem–ítem coseno | 0,114 | 0,063 | 0,047 | 99,3 % |
| **SASRec** | **0,174** | **0,098** | **0,076** | 40,8 % |

SASRec mejora en **31 %** el NDCG@10 de la mejor línea base. En los perfumes de cola larga, en cambio, rinde peor que
ítem–ítem.

**Todas las cifras, el modelo y los archivos de `data/` salen de una única corrida del notebook** (semilla 42, GPU T4).
Esa corrida queda registrada en `data/resumen_corrida.json`, y el informe se generó leyendo ese archivo.

## Base

*Amazon Reviews 2023* (McAuley Lab, UCSD), categorías *Beauty and Personal Care* y *All Beauty*, solo perfumes. Cada
interacción es una reseña: usuario, perfume y marca de tiempo. Tras el 5-core quedan 39.032 interacciones, 5.398 usuarios
y 2.125 perfumes. El profesor autorizó la excepción al mínimo de 50.000 interacciones para conservar una base solo de
perfumes.

Cita: Hou, Y., Li, J., He, Z., Yan, A., Chen, X. y McAuley, J. (2024). *Bridging Language and Items for Retrieval and
Recommendation*. arXiv:2403.03952.

## Contenido del repositorio

```
├── notebooks/Entrega1_Grupo_2.ipynb   Notebook ejecutado de punta a punta (semilla 42)
├── informe/Informe_Entrega1_Grupo_2.pdf
├── data/
│   ├── secuencias.parquet         Secuencias por usuario (índice 0 = relleno) con fechas; usuarios anonimizados
│   ├── mapa_items.csv             idx → perfume (título, marca, género, precio, valoración)
│   ├── metricas.csv               Métricas de prueba, cobertura y costo de los 4 modelos
│   ├── segmentos.csv              NDCG@10 por segmento (historial corto/largo, perfume popular/cola larga)
│   ├── reglas.csv                 Reglas 1 ⇒ 1 de la línea base de reglas de asociación
│   └── resumen_corrida.json       Todas las cifras de la corrida que cita el informe
├── modelos/sasrec.pt              Pesos y configuración de SASRec (0,76 MB)
└── requirements.txt
```

## Decisiones declaradas

- **Reglas de asociación:** el soporte y la confianza se eligen con NDCG@10 de validación (grilla de 5 × 5). Ganó
  soporte ≥ 3 canastas y confianza ≥ 0,20.
- **Género:** se revisa *Unisex* primero y, si la ruta de categorías no informa, se usa el título.
- **Atención:** se muestran los pesos del último bloque, en la última posición, promediados entre las cabezas.
- **Largo máximo:** 14 perfumes (percentil 95). Al 3,7 % de los usuarios se le descarta el inicio de su historial.
