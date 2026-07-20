# Lecturedeck style guide

This guide records reusable visual vocabulary supplied by the viewer. Deck
content remains independent of presentation style, and a unit's optional
`deck.css` is reserved for treatments that genuinely belong to that unit.

## Color mode and presentation style

Color mode and presentation style are separate choices:

- **Dark** and **light** modes change the palette for ambient conditions and
  readability. The viewer control stores this preference locally.
- **Presentation styles** use composable classes that work in both color modes.
  Decks may opt in per slide, while viewer presets apply the same vocabulary
  across the presentation.

Open **Appearance** (or press `T`) to choose both axes independently. The
accessible radio groups persist in the browser and never rewrite deck data.
The presentation-style choices are:

- **Deck default** — render only the classes authored on each slide.
- **Accent gradient** — add `style-gradient` to the whole presentation.
- **Gradient and title rule** — add both `style-gradient` and
  `style-title-rule` to the whole presentation.

Global presets layer over authored classes rather than removing them. PDF
export deliberately uses **Deck default** so a saved browser preference cannot
make the same export command produce different output.

## Accents

Set `accent` on a slide or section to choose its semantic highlight color. The
built-in names are `red`, `gold`, `green`, `aqua`, `blue`, and `purple`.
Sections pass their accent to following slides until another section changes
it. Use accents to mark structure or emphasis, not merely to decorate every
object.

```json
{
  "id": "new-idea",
  "type": "section",
  "title": "A new idea",
  "accent": "aqua"
}
```

## Browser identity

Set `meta.favicon` once per deck so concurrent presentations remain easy to
distinguish in tabs and browser sidebars. The viewer supplies three compact
presets: `complex` (`e` with an `iθ` superscript), `calculus` (an integral with
`f′`), and `plasma` (orange-red concentric sun rings). A unit may instead use
its own image under `webdeck/assets/`.

```json
{
  "meta": {
    "title": "A recognizable deck",
    "favicon": "calculus"
  }
}
```

For a custom icon, use a path such as `"favicon": "assets/favicon.svg"`.
Favor a square, high-contrast design that stays legible at 16 pixels.

## Saved style options

Add one or more names to a slide's `className`.

### Accent gradient

`style-gradient` adds a restrained accent glow over a palette-aware gradient.
It works in dark and light modes because it uses viewer color variables.

```json
{
  "id": "connected-argument",
  "title": "A connected argument",
  "className": "style-gradient"
}
```

### Title rule

`style-title-rule` draws an accent-colored gradient rule beneath the title. On
section slides the rule is centered with the title.

```json
{
  "id": "plane-to-space",
  "type": "section",
  "title": "From plane to space",
  "className": "style-gradient style-title-rule",
  "accent": "gold"
}
```

## Unit-owned CSS

Use `webdeck/deck.css` for a unit-specific block, an exceptional sizing fix, or
an experimental treatment that is not yet a stable viewer option. Prefer a
slide `className` over broad selectors so the effect stays intentional. Do not
copy the entire viewer stylesheet into a course.

Promote a treatment into `lecturedeck` only when it is reusable, works in both
color modes, preserves overview and fullscreen behavior, and can be named
without referring to a particular course.
