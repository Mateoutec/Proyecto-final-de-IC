# Dirección de diseño

Fuentes: `design-system/asistencia-biometrica/MASTER.md` (generado con la skill ui-ux-pro-max) y la
skill frontend-design (`.claude/skills/frontend-design`). Este documento registra cómo se combinaron.

## Tema del producto

Un **reloj marcador** de laboratorio universitario. El kiosco es el reloj de pared que todos miran
al entrar; el panel es el libro de horas que revisa RR.HH. El vocabulario visual sale de ahí:
la hora como protagonista, la "tarjeta de marcación" con un sello de tinta, y tablas de horas
sobrias como una planilla.

## Plan (primera pasada)

- **Color** (de la paleta del design system "navy + verde seguro", ampliada con estados):
  - Tinta marcador `#0B1626` (fondo oscuro del kiosco), Azul reloj `#1E3A5F` (primario),
    Papel `#F3F5F8` (fondo claro del panel), Verde sello `#047857` (ENTRADA),
    Cobre ponchado `#B45309` (SALIDA), Rojo rechazo `#B91C1C`.
- **Tipografía** (familia Fira del design system): Fira Sans Condensed con cifras tabulares para
  la hora grande, el sello y los títulos; Fira Sans para el resto; Fira Code solo donde importa
  distinguir 0/O (el campo de código de estudiante y valores técnicos como el puerto serie).
- **Layout**: kiosco en dos columnas (visor de cámara 3/5, reloj + estado 2/5; se apila en
  vertical). Panel con riel lateral azul reloj, encabezado de página y tablas densas.
- **Principios**: "instrumento, no decoración": cada color significa un estado; el movimiento solo
  aparece cuando algo cambia (el sello al marcar); un único elemento memorable: la tarjeta de
  marcación con el sello de hora.

## Revisión contra lo genérico (y qué se cambió)

- El design system propuso el patrón "Trust & Authority + Conversion" (landing con badges y CTA de
  ventas). No aplica a una app interna: se descartó y se conservaron solo estilo, color y tipografía.
- Fira Code como fuente de encabezados (sugerencia del design system) leía como "dashboard de
  desarrollador" y caía en el tic de monoespaciada para etiquetas pequeñas. Primero se limitó a la
  hora y al sello, pero en la revisión de capturas su cero tachado se leía "Ø4" a distancia: la hora
  pasó a Fira Sans Condensed tabular y Fira Code quedó solo para códigos.
- El resumen del día iba a ser una fila de tarjetas idénticas con sombra (kit SaaS). Se cambió por
  una sola franja tipo planilla con divisores y cifras grandes, más la lista de presentes.
- Nada de etiquetas en mayúsculas sostenidas ni "eyebrows": ENTRADA/SALIDA van en mayúsculas porque
  son los valores reales del registro (así se exportan), no adorno.
- Fondo oscuro: azul tinta deliberado (`#0B1626`), no un negro teñido genérico.

## Reglas de accesibilidad aplicadas

- Contraste AA en ambos temas; foco visible (anillo de 3 px) en todo control.
- Los estados nunca dependen solo del color: ícono + texto + color en kiosco y en insignias.
- `prefers-reduced-motion` desactiva el sello animado y los barridos.
- Objetivos táctiles de 44 px como mínimo en el kiosco.
