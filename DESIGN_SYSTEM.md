# DYTRONICS — Design System

Source of truth for anything visual on the DYTRONICS site. If you're adding a
page, a component, or touching styling, check here before hand-picking a
color, font, or spacing value. `tokens.css` holds the actual CSS — this file
explains what the tokens mean and how to use them so the site doesn't drift
the way `account.html` and `admin.html` did (see "History" at the bottom).

## 1. Tokens

Every page links `tokens.css` in `<head>`, after any font `<link>` tags and
before its own `<style>` block. Never redeclare `:root` in a page — if a
color/spacing value is missing, add it to `tokens.css`, not locally.

```css
--ink:        #12213a   /* primary text */
--ink-soft:   #44536b   /* secondary text, meta, captions */
--paper:      #f4f6f9   /* page background */
--paper-deep: #e6ebf2   /* recessed background (modal media, empty states) */
--card:       #ffffff   /* card / panel surface */
--green:      #1e3a5f   /* brand accent — links, active states, dark UI chrome */
--green-deep: #13283f   /* darkest brand tone — footer, admin topbar, filled buttons */
--gold:       #e2820f   /* CTA / highlight only — solid buttons, badges, hover */
--line:       rgba(33,23,18,0.12)  /* borders, dividers */
--radius:     2px       /* the site is sharp-cornered by design — don't add border-radius elsewhere without a reason */
--err:        #a53b3b   /* error states, destructive actions */
--good:       #1e3a5f   /* success states (shares --green — no separate "success green") */
```

**Rule:** no hex codes in page-level `<style>` blocks. If you're about to
write `#1e3a5f` or similar, use `var(--green)` instead — that's what broke
last time (two pages quietly forked onto a different palette entirely).

## 2. Typography

| Use | Font | Notes |
|---|---|---|
| Body text, labels, UI chrome | `'Inter', sans-serif` | default; 400/500/600 weights only |
| Headings, product/item names, money amounts, wordmark | `'Fraunces', serif` | often `font-style: italic` for a editorial feel on hero/heading text — see `.hero-title`, `.category-head h3` |
| Tracking numbers, monospace labels | `'JetBrains Mono', monospace` | used sparingly — order tracking, receipt codes |

Load Fraunces + Inter via the Google Fonts `<link>` pair already in
`index.html`'s `<head>`; copy that exact block into any new page rather than
re-picking weights.

## 3. Spacing & Layout

- Section horizontal padding: `5vw` (desktop), collapses via existing media
  queries — don't invent a new breakpoint pattern.
- Card/panel border: `1px solid var(--line)`, no shadow by default; the only
  shadow is a subtle hover lift on product cards (`.card:hover`).
- Sharp corners (`--radius: 2px`) everywhere except deliberately-rounded
  small elements (badges, pills) — those are the exception, not the rule.

## 4. Components (established patterns — reuse, don't reinvent)

- **Buttons** — `.btn` (outline) and `.btn-solid` (filled, `var(--gold)`)
  from `index.html`. Solid/gold is reserved for the primary action on a
  screen (checkout, save). Don't make secondary actions gold.
- **Status badges** — one shared color mapping across the whole site:
  `pending_payment` → muted grey/blue, `paid` → `--green`, `shipped` →
  `--gold`, `delivered` → `--green-deep`, `cancelled` → `--err`. `index.html`
  and `admin.html` both implement this — keep it in sync if you change one.
- **Modals / drawers** — backdrop `rgba(20,17,13,0.55–0.72)`, panel on
  `var(--card)`, slide-in from the right for drawers (cart, track-order),
  centered for the product detail modal.
- **Empty / error states** — italic `var(--ink-soft)` text for empty,
  `var(--err)` for error, both inline where the content would be — not a
  separate toast system.

## 5. Copy rules

- No em-dashes in customer- or admin-facing text. Use a period, comma, or
  semicolon instead. (Code comments are exempt — this is about copy a person
  reads, not developer notes.)
- Tone: direct, short sentences, no filler ("Genuine parts & repairs.
  Same-day dispatch." — not "We pride ourselves on...").
- Currency: `₦` prefix, `toLocaleString('en-NG')` formatting, no decimals for
  whole naira amounts.

## 6. Adding a new page

1. Copy the `<head>` block from `index.html` (fonts, `tokens.css` link,
   favicon links) — don't rebuild it from memory.
2. Page-specific `<style>` goes after the `tokens.css` link, using only
   `var(--token)` for color.
3. Reuse component classes above where the pattern already exists (a new
   "account-like" page should reuse `.field`, `.btn`, `.status-msg` from
   `account.html`, not redefine its own).
4. Before shipping, grep the new file for stray em-dashes and hex colors —
   both are signs something drifted from this doc.

## History

`account.html` and `admin.html` were originally built by adapting files from
the SATTYYVVAA (womenswear) project and were never fully re-themed —
that's how a `TTYYVVA` wordmark and a brown/olive palette ended up on a
DYTRONICS page, and how the admin product form had "Dresses / Tops /
Bottoms" as its category fallback. Fixed as of this pass (Sept 2026); this
doc exists so the next adaptation gets re-themed properly instead of copied
wholesale.
