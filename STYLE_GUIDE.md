# Lecturedeck style guide

This guide records reusable visual vocabulary supplied by the viewer. Deck
content remains independent of presentation style, and a unit's optional
`deck.css` is reserved for treatments that genuinely belong to that unit.

## Color mode and presentation style

Color mode and presentation style are separate choices:

- **Dark** and **light** modes change the palette for ambient conditions and
  readability. The viewer control stores this preference locally.
- **Presentation styles** are opt-in classes on individual slides. They may be
  composed and work in both color modes.

The current viewer uses a dark/light toggle. An accessible selector that keeps
color mode distinct from style presets is a requirement for `1.0.0`.

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
