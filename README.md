# IGCSE 0580 Topics Recap Map

Standalone, offline-ready revision sheet covering seven Cambridge IGCSE 0580 topics:

1. Irrational numbers
2. Compound interest
3. Probability
4. Functions
5. Vectors
6. Motion-time graphs
7. Differentiation (Extended only)

## How to open

Just double-click **`index.html`** — no server, no build step, no dependencies. Works in any modern browser offline.

## Folder structure

```
igcse-0580-recap/
├── index.html       ← open this
├── css/
│   └── style.css    ← all styling (light + dark mode)
└── js/
    └── app.js       ← topic filter + dark mode toggle
```

## Features

- **Topic filter** — click any button in the nav to isolate a single topic, or "All topics" to see everything.
- **Dark mode** — toggle with the ◐ button top-right. Preference is saved in browser storage.
- **Keyboard shortcuts**:
  - `1` – `7` → jump to that topic
  - `a` or `0` → show all topics
  - `d` → toggle dark mode
- **Print-friendly** — when you print, nav and toggle hide, all topics show regardless of filter, each card avoids page breaks.

## Editing the content

All topic content is inside `index.html` as plain HTML inside `<article class="topic-card">` blocks. Edit the text directly; CSS classes are already wired up.
