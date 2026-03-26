# Design System Strategy: The Lucid Archive

## 1. Overview & Creative North Star
The Creative North Star for this system is **"The Lucid Archive."** 

This is not a utility-first spreadsheet; it is a high-end editorial experience for material management. We are moving away from the "software as a tool" aesthetic toward "software as a gallery." The goal is to make the management of physical rods and materials feel as light and transparent as the air between them.

By utilizing **intentional asymmetry** and **tonal depth**, we break the rigid, boxed-in feel of traditional ERPs. We favor breathing room over density. Every interaction should feel like turning the page of a heavy-stock architectural magazine—quiet, authoritative, and sophisticated.

---

## 2. Colors & Surface Philosophy
The palette is rooted in a sophisticated, muted spectrum that prioritizes legibility and atmospheric calm.

### The "No-Line" Rule
**Strict Mandate:** 1px solid borders for sectioning are prohibited. Boundaries must be defined solely through background color shifts. For example, a `surface-container-low` (#f1f4f6) section should sit directly on a `surface` (#f8f9fa) background. The transition of tone is the divider.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—stacked sheets of frosted glass or fine vellum.
*   **Base:** `surface` (#f8f9fa)
*   **Nesting:** Place a `surface-container-lowest` (#ffffff) card inside a `surface-container` (#eaeff1) wrapper to create natural, soft definition.
*   **The Glass Rule:** For floating elements (modals, dropdowns), use `surface` at 70% opacity with a `backdrop-blur` of 20px to 40px. This creates the "Lucid" effect, allowing content to bleed through without sacrificing readability.

### Signature Textures
Main CTAs should not be flat. Use a subtle linear gradient from `primary` (#526442) to `primary-dim` (#475737) to provide a "pressed silk" finish that feels premium and tactile.

---

## 3. Typography: The Editorial Voice
Our typography scale juxtaposes the tradition of the serif with the precision of the sans-serif.

*   **The Voice (Noto Serif):** Used for `display` and `headline` levels. This introduces a human, high-end feel to material data. It signals that this ledger is an heirloom of information.
*   **The Engine (Manrope):** Used for `title`, `body`, and `label` levels. It is a clean, geometric sans-serif that ensures data remains the hero. High x-heights ensure clarity even at `label-sm` (0.6875rem).

**Hierarchy Principle:** Use `on-surface-variant` (#586064) for labels to create a sophisticated "receded" look, allowing the `on-surface` (#2b3437) values to pop with authority.

---

## 4. Elevation & Depth
In "The Lucid Archive," depth is felt, not seen. 

*   **Tonal Layering:** Avoid shadows for static elements. Stack `surface-container-high` on `surface-container-low` to create hierarchy.
*   **Ambient Shadows:** When a "floating" effect is required (e.g., a primary action menu), use a "Ghost Shadow": `box-shadow: 0 12px 40px rgba(43, 52, 55, 0.06);`. The shadow color is a tinted version of `on-surface`, never pure black.
*   **The Ghost Border:** If a border is required for accessibility, it must be the `outline-variant` (#abb3b7) at **15% opacity**. This provides a whisper of a boundary without cluttering the "Airy" layout.

---

## 5. Components

### Buttons
*   **Primary:** A soft sage (`primary` #526442) with `on-primary` (#eaffd3) text. Roundedness: `md` (0.375rem).
*   **Secondary:** `surface-container-highest` (#dbe4e7) with `on-secondary-container` (#45545c). No border.
*   **Tertiary:** Text-only in `primary`. Use for low-emphasis navigation.

### Input Fields
*   **Style:** Minimalist underlines or subtle background shifts (`surface-container-low`). 
*   **Focus:** Transition to a `ghost-border` of `primary` (#526442) at 40% opacity. 
*   **Error State:** Use `error` (#9f403d) for the label text, but keep the input background a soft `error-container` (#fe8983) at 10% opacity.

### Cards & Lists
*   **Constraint:** Zero dividers. 
*   **Execution:** Separate list items using `spacing-3` (1rem) and use `surface-container-lowest` as a hover state to highlight rows.
*   **Material Visualization:** For rod ledger entries, use `headline-sm` for quantities and `label-md` for units, creating a clear "Big Number" data viz pattern.

### Specialized Component: The Material Glass Rail
*   A side navigation bar using 80% transparent `surface-container-lowest` with a heavy backdrop blur. This keeps the material list visible "behind" the navigation, emphasizing the theme of total transparency.

---

## 6. Do’s and Don’ts

### Do:
*   **Use Asymmetric Padding:** Use `spacing-16` (5.5rem) for top margins and `spacing-8` (2.75rem) for side margins to create an editorial, off-balance layout.
*   **Embrace "Empty" Space:** If a screen has only three data points, let them sit in the center with massive whitespace. Do not "fill" the screen.
*   **Color as Signal:** Use `tertiary` (Champagne Gold #745c00) *only* for status highlights or rare "premium" material types.

### Don’t:
*   **No Heavy Shadows:** Never use a shadow with more than 10% opacity. It ruins the "Airy" aesthetic.
*   **No Pure Black:** The darkest color in the system is `inverse-surface` (#0c0f10). Never use #000000.
*   **No Sharp Corners:** While we are minimal, we are not clinical. Always use at least the `DEFAULT` (0.25rem) radius to soften the digital edge.
*   **No Standard Grids:** Avoid the "Dashboard Widget" look. Group data in organic clusters rather than rigid, equal-width boxes.