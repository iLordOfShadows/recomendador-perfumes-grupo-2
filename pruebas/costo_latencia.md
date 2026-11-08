# Costo y latencia del analista

- Modelo: `gemini-3.1-flash-lite` (plan gratuito de Google AI Studio) · 10 usuarios de la base elegidos al azar (semilla 42) · 2026-11-08
- Por usuario: 1 análisis automático + 1 pregunta de seguimiento que obliga a volver a consultar a SASRec.
- Precio de referencia del plan pagado: US$ 0,25 por millón de tokens de entrada y US$ 1,50 por millón de salida.
  **Costo real con la llave gratuita: US$ 0.** Llamadas fallidas: 0.

| tipo                 |   llamadas |   tokens_entrada |   tokens_salida |   costo_equiv_usd |   latencia_mediana_s |   latencia_media_s |   latencia_p90_s |
|:---------------------|-----------:|-----------------:|----------------:|------------------:|---------------------:|-------------------:|-----------------:|
| análisis automático  |         10 |           5847.3 |           462.6 |            0.0022 |                2.055 |             10.432 |           13.456 |
| chat con re-consulta |         10 |          18279.4 |           319.9 |            0.005  |                3.2   |             19.871 |           26.82  |

- **Costo equivalente por sesión** (análisis + 1 pregunta): US$ 0.0072 → **US$ 7.21 por 1.000 sesiones**.
- **Latencia:** la mediana es lo representativo (2.1 s el análisis y
  3.2 s el chat con herramientas). El promedio sube por **un usuario (4171)
  con 80 s y 158 s**, probablemente por esperas del plan gratuito (límite de solicitudes por minuto): sus tokens son normales.
- El chat con re-consulta usa unas 3 veces más tokens de entrada que el análisis, porque cada vuelta reenvía el contexto
  y el resultado de la herramienta.
